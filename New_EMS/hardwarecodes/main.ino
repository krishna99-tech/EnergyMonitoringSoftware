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

IPAddress ip(192,168,0,177);
IPAddress gateway(192,168,0,1);
IPAddress subnet(255,255,255,0);
IPAddress dns(8,8,8,8);

IPAddress remoteIP(192,168,0,179);
unsigned int remotePort = 6503;

EthernetUDP Udp;
ModbusMaster node;

// ================= METERS =================
#define SCH_ID 2
#define ELM_ID 1

// Schneider Registers
uint16_t SCH_REG[] = {
  3109, // Frequency
  3035, // Voltage
  3009, // Current
  3077, // PF
  3059, // KW
  3076  // KVA
};

// Elmeasure KWH Register
uint16_t ELM_KWH_REG = 156;   // Change if needed

const char* names[] = {
  "freq",
  "volt",
  "curr",
  "pf",
  "kw",
  "kva"
};

// ================= RS485 CTRL =================
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

// ================= READ SCHNEIDER =================
bool readMeter(uint8_t slave,
               uint16_t regs[],
               bool swapped,
               float values[]) {

  int successCount = 0;

  node.begin(slave, Serial2);

  for (int i = 0; i < 6; i++) {

    while (Serial2.available()) {
      Serial2.read();
    }

    uint8_t res = node.readHoldingRegisters(regs[i], 2);

    if (res == node.ku8MBSuccess) {

      uint16_t r1 = node.getResponseBuffer(0);
      uint16_t r2 = node.getResponseBuffer(1);

      float v = swapped
                ? decodeSwapped(r1, r2)
                : decodeNormal(r1, r2);

      values[i] = round(v * 100) / 100.0;

      successCount++;
    }
    else {

      values[i] = -1;

      Serial.print("Failed Register: ");
      Serial.println(regs[i]);
    }

    delay(50);
  }

  return (successCount >= 2);
}

// ================= READ SINGLE FLOAT =================
bool readSingleFloat(uint8_t slave,
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

  Serial.print("Failed KWH Register: ");
  Serial.println(reg);

  return false;
}

// ================= SETUP =================
void setup() {

  Serial.begin(115200);

  // RS485 Direction
  pinMode(MAX485_RE_DE, OUTPUT);
  digitalWrite(MAX485_RE_DE, LOW);

  // RS485 Serial
  Serial2.begin(9600, SERIAL_8E1, RX2_PIN, TX2_PIN);

  node.preTransmission(preTransmission);
  node.postTransmission(postTransmission);

  // W5500 Reset
  pinMode(W5500_RST, OUTPUT);

  digitalWrite(W5500_RST, LOW);
  delay(200);

  digitalWrite(W5500_RST, HIGH);
  delay(200);

  // SPI Start
  SPI.begin(W5500_SCK,
            W5500_MISO,
            W5500_MOSI,
            W5500_CS);

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

  float schVal[6];
  float elmKwh = 0;

  // ================= SCHNEIDER =================
  Serial.println("\n========== SCHNEIDER ==========");

  bool schStatus = readMeter(
                     SCH_ID,
                     SCH_REG,
                     false,
                     schVal
                   );

  if (schStatus) {

    for (int i = 0; i < 6; i++) {

      Serial.print(names[i]);
      Serial.print(" : ");
      Serial.println(schVal[i]);
    }
  }
  else {

    Serial.println("Schneider Offline");
  }

  delay(500);

  // ================= ELMEASURE =================
  Serial.println("\n========== ELMEASURE ==========");

  bool elmStatus = readSingleFloat(
                     ELM_ID,
                     ELM_KWH_REG,
                     true,
                     elmKwh
                   );

  if (elmStatus) {

    Serial.print("KWH : ");
    Serial.println(elmKwh);
  }
  else {

    Serial.println("Elmeasure Offline");
  }

  // ================= JSON =================
  StaticJsonDocument<512> doc;

  doc["device"] = DEVICE_ID;

  JsonArray meters = doc.createNestedArray("meters");

  // ================= SCH JSON =================
  JsonObject sch = meters.createNestedObject();

  sch["id"] = SCH_ID;
  sch["status"] = schStatus ? "OK" : "OFFLINE";

  if (schStatus) {

    for (int i = 0; i < 6; i++) {

      sch[names[i]] = schVal[i];
    }
  }

  // ================= ELM JSON =================
  JsonObject elm = meters.createNestedObject();

  elm["id"] = ELM_ID;
  elm["status"] = elmStatus ? "OK" : "OFFLINE";

  if (elmStatus) {

    elm["kwh"] = elmKwh;
  }

  // ================= SERIALIZE =================
  char buffer[512];

  serializeJson(doc, buffer);

  Serial.println("\n========== JSON ==========");
  Serial.println(buffer);

  // ================= UDP SEND =================
  Udp.beginPacket(remoteIP, remotePort);

  Udp.write((uint8_t*)buffer, strlen(buffer));

  Udp.endPacket();

  Serial.println("UDP Sent");

  delay(3000);
}