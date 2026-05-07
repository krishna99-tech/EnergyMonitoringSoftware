#include <SPI.h>
#include <Ethernet.h>
#include <EthernetUdp.h>
#include <ModbusMaster.h>
#include <ArduinoJson.h>

// ================= DEVICE =================
#define DEVICE_ID "ESP32_01"

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

uint16_t SCH_REG[] = {3109,3035,3009,3083,3059,3076};
uint16_t ELM_REG[] = {156,132,148,112,100,124};

const char* names[] = {"freq","volt","curr","pf","kw","kva"};

// ================= RS485 CTRL =================
void preTransmission(){ digitalWrite(MAX485_RE_DE, HIGH); }
void postTransmission(){ digitalWrite(MAX485_RE_DE, LOW); }

// ================= FLOAT =================
float decodeNormal(uint16_t r1, uint16_t r2){
  uint32_t val = ((uint32_t)r1 << 16) | r2;
  float f; memcpy(&f, &val, 4);
  return f;
}

float decodeSwapped(uint16_t r1, uint16_t r2){
  uint32_t val = ((uint32_t)r2 << 16) | r1;
  float f; memcpy(&f, &val, 4);
  return f;
}

// ================= READ METER =================
bool readMeter(uint8_t slave, uint16_t regs[], bool swapped, float values[]) {

  int successCount = 0;
  node.begin(slave, Serial2);

  for (int i = 0; i < 6; i++) {

    while (Serial2.available()) Serial2.read();

    uint8_t res = node.readHoldingRegisters(regs[i], 2);

    if (res == node.ku8MBSuccess) {

      uint16_t r1 = node.getResponseBuffer(0);
      uint16_t r2 = node.getResponseBuffer(1);

      float v = swapped ? decodeSwapped(r1, r2)
                        : decodeNormal(r1, r2);

      values[i] = round(v * 100) / 100.0;
      successCount++;
    }
    else {
      values[i] = -1;
    }

    delay(50);
  }

  return (successCount >= 2); // communication-based
}

// ================= SETUP =================
void setup() {

  Serial.begin(115200);

  pinMode(MAX485_RE_DE, OUTPUT);
  digitalWrite(MAX485_RE_DE, LOW);

  Serial2.begin(9600, SERIAL_8E1, RX2_PIN, TX2_PIN);

  node.preTransmission(preTransmission);
  node.postTransmission(postTransmission);

  pinMode(W5500_RST, OUTPUT);
  digitalWrite(W5500_RST, LOW);
  delay(200);
  digitalWrite(W5500_RST, HIGH);
  delay(200);

  SPI.begin(W5500_SCK, W5500_MISO, W5500_MOSI, W5500_CS);
  Ethernet.init(W5500_CS);
  Ethernet.begin(mac, ip, dns, gateway, subnet);

  Serial.print("ESP32 IP: ");
  Serial.println(Ethernet.localIP());

  Udp.begin(8888);
}

// ================= LOOP =================
void loop() {

  float schVal[6];
  float elmVal[6];

  Serial.println("\n--- Reading Schneider ---");
  bool schStatus = readMeter(SCH_ID, SCH_REG, false, schVal);

  delay(500);

  Serial.println("--- Reading Elmeasure ---");
  bool elmStatus = readMeter(ELM_ID, ELM_REG, true, elmVal);

  // ================= JSON =================
  StaticJsonDocument<512> doc;

  doc["device"] = DEVICE_ID;
  JsonArray meters = doc.createNestedArray("meters");

  // ========= Schneider =========
  JsonObject m1 = meters.createNestedObject();
  m1["id"] = SCH_ID;
  m1["status"] = schStatus ? "OK" : "OFFLINE";

  if (schStatus) {
    for (int i = 0; i < 6; i++) {
      m1[names[i]] = schVal[i];
    }
  }

  // ========= Elmeasure =========
  JsonObject m2 = meters.createNestedObject();
  m2["id"] = ELM_ID;
  m2["status"] = elmStatus ? "OK" : "OFFLINE";

  if (elmStatus) {
    for (int i = 0; i < 6; i++) {
      m2[names[i]] = elmVal[i];
    }
  }

  // Serialize
  char buffer[512];
  serializeJson(doc, buffer);

  Serial.println("\nSending JSON:");
  Serial.println(buffer);

  // UDP send
  Udp.beginPacket(remoteIP, remotePort);
  Udp.write((uint8_t*)buffer, strlen(buffer));
  Udp.endPacket();

  delay(3000);
}