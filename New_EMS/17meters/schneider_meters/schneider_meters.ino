#include <SPI.h>
#include <Ethernet.h>
#include <EthernetUdp.h>
#include <ModbusMaster.h>
#include <ArduinoJson.h>

// ================= DEVICE =================
#define DEVICE_ID "Architecture"

// ================= W5500 =================
#define W5500_MISO 12
#define W5500_MOSI 13
#define W5500_SCK  14
#define W5500_CS   15
#define W5500_RST  25

// ================= RS485 =================
#define MAX485_RE_DE 4
#define RX2_PIN 32
#define TX2_PIN 33

// ================= NETWORK =================
byte mac[] = {0xDE, 0xAD, 0xBE, 0xEF, 0xFE, 0xED};

IPAddress ip(192, 168, 0, 229);
IPAddress gateway(192, 168, 0, 254);
IPAddress subnet(255, 255, 255, 0);
IPAddress dns(8, 8, 8, 8);

IPAddress remoteIP(192, 168, 0, 41);
unsigned int remotePort = 10011;

EthernetUDP Udp;
ModbusMaster node;

// ================= METERS =================
#define TOTAL_METERS 13

// Schneider iEM3xxx series kWh register
// Datasheet address: 3204 (Wh delivered, 32-bit float, 2 registers)
// Zero-based offset for ModbusMaster: 3203
uint16_t SCH_KWH_REG = 2699;

uint8_t slaveIds[TOTAL_METERS] = {
  1, 2, 4, 7, 8, 9, 10, 13, 15, 16, 17, 19, 20
};

// ================= RS485 CONTROL =================
void preTransmission() {
  digitalWrite(MAX485_RE_DE, HIGH);
}

void postTransmission() {
  digitalWrite(MAX485_RE_DE, LOW);
}

// ================= FLOAT DECODING =================
// Schneider uses big-endian word order (normal)
float decodeNormal(uint16_t r1, uint16_t r2) {
  uint32_t val = ((uint32_t)r1 << 16) | r2;
  float f;
  memcpy(&f, &val, 4);
  return f;
}

// ================= READ KWH =================
bool readKwh(uint8_t slave, float &value) {

  node.begin(slave, Serial2);

  // Flush any stale bytes before transmitting
  while (Serial2.available()) {
    Serial2.read();
  }

  uint8_t res = node.readHoldingRegisters(SCH_KWH_REG, 2);

  if (res == node.ku8MBSuccess) {
    uint16_t r1 = node.getResponseBuffer(0);
    uint16_t r2 = node.getResponseBuffer(1);
    value = round(decodeNormal(r1, r2) * 100) / 100.0;
    return true;
  }

  value = -1;
  Serial.print("Failed Meter ID: ");
  Serial.println(slave);
  return false;
}

// ================= SETUP =================
void setup() {

  Serial.begin(115200);

  // RS485
  pinMode(MAX485_RE_DE, OUTPUT);
  digitalWrite(MAX485_RE_DE, LOW);

  // Schneider default baud: 9600, 8E1
  Serial2.begin(9600, SERIAL_8E1, RX2_PIN, TX2_PIN);

  node.preTransmission(preTransmission);
  node.postTransmission(postTransmission);

  // W5500 hardware reset
  pinMode(W5500_RST, OUTPUT);
  digitalWrite(W5500_RST, LOW);
  delay(200);
  digitalWrite(W5500_RST, HIGH);
  delay(200);

  // SPI + Ethernet
  SPI.begin(W5500_SCK, W5500_MISO, W5500_MOSI, W5500_CS);
  Ethernet.init(W5500_CS);
  Ethernet.begin(mac, ip, dns, gateway, subnet);

  Serial.println();
  Serial.print("ESP32 IP: ");
  Serial.println(Ethernet.localIP());

  Udp.begin(8888);
  Serial.println("UDP Started");
}

// ================= LOOP =================
void loop() {

  unsigned long startTime = millis();

  StaticJsonDocument<2048> doc;
  doc["device"] = DEVICE_ID;
  JsonArray meterArray = doc.createNestedArray("meters");

  // ======================================================
  // READ ALL SCHNEIDER METERS
  // ======================================================
  for (int i = 0; i < TOTAL_METERS; i++) {

    uint8_t slave = slaveIds[i];
    float kwh = 0;

    bool status = readKwh(slave, kwh);

    // Serial debug
    Serial.print("Meter ID: ");
    Serial.print(slave);
    Serial.print(" | Status: ");

    if (status) {
      Serial.print("OK | KWH: ");
      Serial.println(kwh);
    } else {
      Serial.println("OFFLINE");
    }

    // Build JSON object for this meter
    JsonObject meter = meterArray.createNestedObject();
    meter["id"]     = slave;
    meter["status"] = status ? "OK" : "OFFLINE";
    if (status) {
      meter["kwh"] = kwh;
    }

    delay(100);
  }

  // ======================================================
  // SERIALIZE & SEND UDP
  // ======================================================
  char buffer[2048];
  size_t len = serializeJson(doc, buffer);

  Serial.println("\n========== JSON ==========");
  Serial.println(buffer);

  Udp.beginPacket(remoteIP, remotePort);
  Udp.write((uint8_t*)buffer, len);
  Udp.endPacket();

  Serial.println("UDP Sent\n");

  // ======================================================
  // WAIT UNTIL EXACTLY 60 SECONDS HAVE PASSED
  // ======================================================
  unsigned long elapsed = millis() - startTime;
  if (elapsed < 60000) {
    delay(60000 - elapsed);
  }
}