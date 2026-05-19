#include <SPI.h>
#include <Ethernet.h>
#include <EthernetUdp.h>
#include <ModbusMaster.h>
#include <ArduinoJson.h>

// ================= DEVICE =================
#define DEVICE_ID "Automotive"

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
byte mac[] = {0xDE,0xAD,0xBE,0xEF,0xFE,0xED};

IPAddress ip(192,168,0,229);
IPAddress gateway(192,168,0,254);
IPAddress subnet(255,255,255,0);
IPAddress dns(8,8,8,8);

IPAddress remoteIP(192,168,0,41);
unsigned int remotePort = 10011;

EthernetUDP Udp;
ModbusMaster node;

// ======================================================
// TOTAL METERS
// ======================================================
#define TOTAL_METERS 13

// ======================================================
// METER TYPES
// 0 = Schneider
// 1 = Elmeasure
// ======================================================
#define SCHNEIDER 0
#define ELMEASURE 1

// ======================================================
// REGISTER ADDRESSES
// ======================================================

// Schneider kWh Register
// Datasheet: 2700
uint16_t SCH_KWH_REG = 2699;

// Elmeasure kWh Register
// Datasheet: 40167
// Modbus libraries usually use offset without 40001
// 40167 -> 166
uint16_t ELM_KWH_REG = 158;

// ======================================================
// CONFIGURE YOUR METERS
// id, type
// ======================================================

struct MeterConfig {
  uint8_t slaveId;
  uint8_t type;
};

MeterConfig meters[TOTAL_METERS] = {
  
  {21, ELMEASURE},
  {2, SCHNEIDER},
  {4, SCHNEIDER},
  {7, SCHNEIDER},
  {8, SCHNEIDER},
  {9, SCHNEIDER},
  {10, SCHNEIDER},
  {13, SCHNEIDER},
  {15, SCHNEIDER},
  {16, SCHNEIDER},
  {17, SCHNEIDER},
  {19, SCHNEIDER},
  {20, SCHNEIDER}
}; 

// ================= RS485 CONTROL =================
void preTransmission() {
  digitalWrite(MAX485_RE_DE, HIGH);
}

void postTransmission() {
  digitalWrite(MAX485_RE_DE, LOW);
}

// ================= FLOAT DECODING =================
float decodeNormal(uint16_t r1, uint16_t r2) {

  uint32_t val = ((uint32_t)r1 << 16) | r2;

  float f;
  memcpy(&f, &val, 4);

  return f;
}

float decodeSwapped(uint16_t r1, uint16_t r2) {

  uint32_t val = ((uint32_t)r2 << 16) | r1;

  float f;
  memcpy(&f, &val, 4);

  return f;
}

// ================= READ KWH =================
bool readKwh(uint8_t slave,
             uint16_t reg,
             bool swapped,
             float &value) {

  node.begin(slave, Serial2);

  while (Serial2.available()) {
    Serial2.read();
  }

  uint8_t res = node.readHoldingRegisters(reg, 2);

  if (res == node.ku8MBSuccess) {

    uint16_t r1 = node.getResponseBuffer(0);
    uint16_t r2 = node.getResponseBuffer(1);

    float v = swapped
              ? decodeSwapped(r1, r2)
              : decodeNormal(r1, r2);

    value = round(v * 100) / 100.0;

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

  Serial2.begin(9600, SERIAL_8E1, RX2_PIN, TX2_PIN);

  node.preTransmission(preTransmission);
  node.postTransmission(postTransmission);

  // W5500 RESET
  pinMode(W5500_RST, OUTPUT);

  digitalWrite(W5500_RST, LOW);
  delay(200);

  digitalWrite(W5500_RST, HIGH);
  delay(200);

  // SPI
  SPI.begin(
    W5500_SCK,
    W5500_MISO,
    W5500_MOSI,
    W5500_CS
  );

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

  StaticJsonDocument<2048> doc;

  doc["device"] = DEVICE_ID;

  JsonArray meterArray = doc.createNestedArray("meters");

  // ======================================================
  // READ ALL METERS
  // ======================================================

  for (int i = 0; i < TOTAL_METERS; i++) {

    uint8_t slave = meters[i].slaveId;
    uint8_t type = meters[i].type;

    float kwh = 0;
    bool status = false;

    // ======================================================
    // SCHNEIDER
    // ======================================================

    if (type == SCHNEIDER) {

      status = readKwh(
                 slave,
                 SCH_KWH_REG,
                 false,
                 kwh
               );
    }

    // ======================================================
    // ELMEASURE
    // ======================================================

    else if (type == ELMEASURE) {

      status = readKwh(
                 slave,
                 ELM_KWH_REG,
                 true,
                 kwh
               );
    }

    // ======================================================
    // SERIAL DEBUG
    // ======================================================

    Serial.print("Meter ID: ");
    Serial.print(slave);

    Serial.print(" | Status: ");

    if (status) {

      Serial.print("OK");

      Serial.print(" | KWH: ");
      Serial.println(kwh);
    }
    else {

      Serial.println("OFFLINE");
    }

    // ======================================================
    // JSON
    // ======================================================

    JsonObject meter = meterArray.createNestedObject();

    meter["id"] = slave;
    meter["status"] =
      status
      ? "OK"
      : "OFFLINE";

    if (status) {

      meter["kwh"] = kwh;
    }

    delay(100);
  }

  // ======================================================
  // SERIALIZE JSON
  // ======================================================

  char buffer[2048];

  size_t len = serializeJson(doc, buffer);

  Serial.println("\n========== JSON ==========");
  Serial.println(buffer);

  // ======================================================
  // UDP SEND
  // ======================================================

  Udp.beginPacket(remoteIP, remotePort);

  Udp.write((uint8_t*)buffer, len);

  Udp.endPacket();

  Serial.println("UDP Sent");

  Serial.println();

  delay(5000);
}