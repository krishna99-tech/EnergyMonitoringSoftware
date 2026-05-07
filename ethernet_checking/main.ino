#include <SPI.h>
#include <Ethernet.h>
#include <EthernetUdp.h>

// ----------- W5500 Pins -----------
#define W5500_MISO 12
#define W5500_MOSI 13
#define W5500_SCK  14
#define W5500_CS   15
#define W5500_RST  25

// ----------- MAC Address -----------
byte mac[] = { 0xDE, 0xAD, 0xBE, 0xEF, 0xFE, 0xED };

// ----------- Static IP -----------
IPAddress ip(192, 168, 0, 177);
IPAddress gateway(192, 168, 0, 1);
IPAddress subnet(255, 255, 255, 0);
IPAddress dns(8, 8, 8, 8);

// ----------- UDP Target -----------
IPAddress remoteIP(192, 168, 0, 179); // 🔴 Change to your PC/server IP
unsigned int remotePort = 6503;

EthernetUDP Udp;

void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.println("Starting W5500 Ethernet...");

  // Reset W5500
  pinMode(W5500_RST, OUTPUT);
  digitalWrite(W5500_RST, LOW);
  delay(200);
  digitalWrite(W5500_RST, HIGH);
  delay(200);

  // SPI Init
  SPI.begin(W5500_SCK, W5500_MISO, W5500_MOSI, W5500_CS);

  Ethernet.init(W5500_CS);
  Ethernet.begin(mac, ip, dns, gateway, subnet);

  delay(1000);

  Serial.print("Assigned IP: ");
  Serial.println(Ethernet.localIP());

  // Start UDP
  Udp.begin(8888); // local port

  // Seed random generator
  randomSeed(analogRead(34)); // any floating pin
}

void loop() {
  // Generate random number
  int randNumber = random(0, 1000);

  Serial.print("Sending: ");
  Serial.println(randNumber);

  // Send via UDP
  Udp.beginPacket(remoteIP, remotePort);
  Udp.print("Random: ");
  Udp.print(randNumber);
  Udp.endPacket();

  delay(2000); // send every 2 sec
}