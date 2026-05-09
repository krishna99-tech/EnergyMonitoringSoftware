/**
 * INTEGRATED: URM15 + Eurotherm 3216 + UDP Dashboard
 * 45-MINUTE CYCLE STATE MACHINE
 *
 * Cycle phases:
 *   READING  — sensor active, decision made, Eurotherm updated
 *   LOCKED   — 45-minute hold, sensor off, no changes
 *
 * No-job counter:
 *   Any job detected        → counter = 0
 *   1st consecutive no-job → counter = 1, keep previous setpoint
 *   2nd consecutive no-job → counter = 2, apply TEMP_DEFAULT
 *   Counter is capped at 2 — no higher state exists
 */

// ─── LIBRARIES ──────────────────────────────────────────────────────────────
#include <WiFi.h>
#include <WiFiUdp.h>
#include <WiFiManager.h>
#include <ModbusMaster.h>
#include <Preferences.h>

// ─── PIN CONFIG ──────────────────────────────────────────────────────────────
#define RS485_TX_PIN        33
#define RS485_RX_PIN        32
#define RS485_DE_RE_PIN      4

#define RELAY1_PIN           2
#define RELAY2_PIN          16
#define PUSH_BUTTON_PIN     35
#define BUTTON_LONGPRESS_MS 5000

// ─── BAUD RATES ──────────────────────────────────────────────────────────────
#define URM15_BAUD        9600
#define EUROTHERM_BAUD    9600

// ─── SLAVE IDs ───────────────────────────────────────────────────────────────
#define URM15_SLAVE_ID       3
#define EUROTHERM_SLAVE_ID   1

// ─── URM15 REGISTERS ─────────────────────────────────────────────────────────
#define URM15_REG_DISTANCE   5
#define URM15_REG_CONTROL    8
#define TEMP_CPT_ENABLE_BIT  (0x01 << 1)
#define MEASURE_MODE_BIT     (0x01 << 2)
#define MEASURE_TRIG_BIT     (0x01 << 3)

// ─── EUROTHERM ───────────────────────────────────────────────────────────────
#define EUROTHERM_REG_REMOTE_SP  27   // Rm.SP — 1-based register address

// ─── MAX485 TIMING ───────────────────────────────────────────────────────────
#define DE_PRE_DELAY_US          100
#define DE_HOLD_AFTER_FLUSH_MS    10
#define DE_TO_RX_SETTLE_MS         5
#define EUROTHERM_TURNAROUND_MS   20
#define RX_TIMEOUT_MS            500  // was 2000 — 9600 baud frame is ~66ms

// ─── CYCLE TIMING ────────────────────────────────────────────────────────────
uint16_t LOCK_DURATION_MINUTES = 45;           // Locked phase duration in minutes
unsigned long lockDurationMs = 45UL * 60UL * 1000UL;
#define READING_WINDOW_MS   (10UL * 1000UL)          // 10 s for sensor to stabilise

// ─── WIFI ────────────────────────────────────────────────────────────────────
const char* WIFI_SSID     = "abba chaa";
const char* WIFI_PASSWORD = "0246813579";

// ─── UDP ─────────────────────────────────────────────────────────────────────
const char* UDP_TARGET_IP = "10.232.99.197";
const uint16_t UDP_PORT   = 5005;

// ─── RUNTIME PARAMETERS (loaded from Preferences) ────────────────────────────
uint16_t TEMP_DEFAULT  = 120;
uint16_t TEMP_LEVEL1   = 180;
uint16_t TEMP_LEVEL2   = 200;

float DISTANCE_MIN_1   = 30.0;
float DISTANCE_MAX_1   = 50.0;
float DISTANCE_MIN_2   = 51.0;
float DISTANCE_MAX_2   = 90.0;

char JOB1_NAME[32] = "JOB 1";
char JOB2_NAME[32] = "JOB 2";
char JOB3_NAME[32] = "OTHER";

// ─── HYSTERESIS ──────────────────────────────────────────────────────────────
// A mode is confirmed only after this many consecutive matching reads
// within the READING_WINDOW_MS. Guards against a single glitch read.
#define CONFIRM_READS_REQUIRED  3

// ─── STATE MACHINE ───────────────────────────────────────────────────────────
enum CyclePhase {
    PHASE_READING,   // sensor active, awaiting confirmed reading
    PHASE_LOCKED     // 45-minute hold, sensor idle
};

CyclePhase cyclePhase    = PHASE_READING;  // start by reading on boot
uint8_t    noJobCounter  = 0;              // 0, 1, or 2 — capped at 2
uint8_t    currentMode   = 0;             // 0 = no job, 1 = JOB1, 2 = JOB2
uint16_t   lastSetpoint  = 0;             // tracks what Eurotherm was last commanded
                                          // 0 = never written (forces write on boot)

int relay1State = 1;  // 1 = OFF (active-LOW relay)
int relay2State = 1;

unsigned long phaseStartMs = 0;   // millis() when current phase began

// ─── OBJECTS ─────────────────────────────────────────────────────────────────
HardwareSerial ModbusSerial(2);
ModbusMaster   urm15;
Preferences    prefs;
WiFiUDP        udp;

// Active bus tracker — avoids redundant Serial2 re-inits
enum ActiveBus { BUS_NONE, BUS_URM15, BUS_EUROTHERM };
ActiveBus activeBus = BUS_NONE;

// ─────────────────────────────────────────────────────────────────────────────
// DEBUG
// ─────────────────────────────────────────────────────────────────────────────
void printDivider(const char* title) {
    Serial.println();
    Serial.println("==================================================");
    Serial.println(title);
    Serial.println("==================================================");
}

const char* phaseName(CyclePhase p) {
    return (p == PHASE_READING) ? "READING" : "LOCKED";
}

// ─────────────────────────────────────────────────────────────────────────────
// RS485 CALLBACKS
// ─────────────────────────────────────────────────────────────────────────────
void preTransmission()  { digitalWrite(RS485_DE_RE_PIN, HIGH); }
void postTransmission() { digitalWrite(RS485_DE_RE_PIN, LOW);  }

// ─────────────────────────────────────────────────────────────────────────────
// BUS SWITCHING — only re-inits Serial2 when the active device actually changes
// ─────────────────────────────────────────────────────────────────────────────
void switchBusTo(ActiveBus target) {
    if (activeBus == target) return;

    ModbusSerial.end();
    delay(20);

    uint32_t baud = (target == BUS_URM15) ? URM15_BAUD : EUROTHERM_BAUD;
    ModbusSerial.begin(baud, SERIAL_8N1, RS485_RX_PIN, RS485_TX_PIN);
    delay(20);

    activeBus = target;
    Serial.printf("[BUS] Switched to %s @ %u baud\n",
                  target == BUS_URM15 ? "URM15" : "EUROTHERM", baud);
}

// ─────────────────────────────────────────────────────────────────────────────
// WIFI
// ─────────────────────────────────────────────────────────────────────────────
bool isConfigButtonHeld() {
    unsigned long start = millis();
    while (millis() - start < BUTTON_LONGPRESS_MS) {
        if (digitalRead(PUSH_BUTTON_PIN) != LOW) return false;
        delay(20);
    }
    return true;
}

void startWiFiConfigPortal() {
    Serial.println("[WiFiManager] Push button held: starting AP config portal.");

    WiFiManager wifiManager;

    char tdefBuf[8];
    char t1Buf[8];
    char t2Buf[8];
    char dmin1Buf[12];
    char dmax1Buf[12];
    char dmin2Buf[12];
    char dmax2Buf[12];
    char job1Buf[32];
    char job2Buf[32];
    char job3Buf[32];
    char lockMinBuf[6];

    snprintf(tdefBuf, sizeof(tdefBuf), "%u", TEMP_DEFAULT);
    snprintf(t1Buf, sizeof(t1Buf), "%u", TEMP_LEVEL1);
    snprintf(t2Buf, sizeof(t2Buf), "%u", TEMP_LEVEL2);
    snprintf(dmin1Buf, sizeof(dmin1Buf), "%.1f", DISTANCE_MIN_1);
    snprintf(dmax1Buf, sizeof(dmax1Buf), "%.1f", DISTANCE_MAX_1);
    snprintf(dmin2Buf, sizeof(dmin2Buf), "%.1f", DISTANCE_MIN_2);
    snprintf(dmax2Buf, sizeof(dmax2Buf), "%.1f", DISTANCE_MAX_2);
    strlcpy(job1Buf, JOB1_NAME, sizeof(job1Buf));
    strlcpy(job2Buf, JOB2_NAME, sizeof(job2Buf));
    strlcpy(job3Buf, JOB3_NAME, sizeof(job3Buf));
    snprintf(lockMinBuf, sizeof(lockMinBuf), "%u", LOCK_DURATION_MINUTES);

    WiFiManagerParameter tdefParam("tdef", "Temp default", tdefBuf, sizeof(tdefBuf));
    WiFiManagerParameter t1Param("t1", "Temp JOB1", t1Buf, sizeof(t1Buf));
    WiFiManagerParameter t2Param("t2", "Temp JOB2", t2Buf, sizeof(t2Buf));
    WiFiManagerParameter dmin1Param("dmin1", "Dist min JOB1", dmin1Buf, sizeof(dmin1Buf));
    WiFiManagerParameter dmax1Param("dmax1", "Dist max JOB1", dmax1Buf, sizeof(dmax1Buf));
    WiFiManagerParameter dmin2Param("dmin2", "Dist min JOB2", dmin2Buf, sizeof(dmin2Buf));
    WiFiManagerParameter dmax2Param("dmax2", "Dist max JOB2", dmax2Buf, sizeof(dmax2Buf));
    WiFiManagerParameter job1Param("job1", "Job1 name", job1Buf, sizeof(job1Buf));
    WiFiManagerParameter job2Param("job2", "Job2 name", job2Buf, sizeof(job2Buf));
    WiFiManagerParameter job3Param("job3", "Job3 name", job3Buf, sizeof(job3Buf));
    WiFiManagerParameter lockMinParam("lockmin", "Lock duration (min)", lockMinBuf, sizeof(lockMinBuf));

    wifiManager.addParameter(&tdefParam);
    wifiManager.addParameter(&t1Param);
    wifiManager.addParameter(&t2Param);
    wifiManager.addParameter(&dmin1Param);
    wifiManager.addParameter(&dmax1Param);
    wifiManager.addParameter(&dmin2Param);
    wifiManager.addParameter(&dmax2Param);
    wifiManager.addParameter(&job1Param);
    wifiManager.addParameter(&job2Param);
    wifiManager.addParameter(&job3Param);
    wifiManager.addParameter(&lockMinParam);

    wifiManager.setConfigPortalTimeout(300);

    if (!wifiManager.startConfigPortal("EMS_Config")) {
        Serial.println("[WiFiManager] Config portal timeout or failed.");
    } else {
        Serial.println("[WiFiManager] Config portal finished.");
    }

    uint16_t newTdef = atoi(tdefParam.getValue());
    if (newTdef > 0) TEMP_DEFAULT = newTdef;
    uint16_t newT1 = atoi(t1Param.getValue());
    if (newT1 > 0) TEMP_LEVEL1 = newT1;
    uint16_t newT2 = atoi(t2Param.getValue());
    if (newT2 > 0) TEMP_LEVEL2 = newT2;
    float newDmin1 = atof(dmin1Param.getValue());
    if (newDmin1 > 0.0f) DISTANCE_MIN_1 = newDmin1;
    float newDmax1 = atof(dmax1Param.getValue());
    if (newDmax1 > 0.0f) DISTANCE_MAX_1 = newDmax1;
    float newDmin2 = atof(dmin2Param.getValue());
    if (newDmin2 > 0.0f) DISTANCE_MIN_2 = newDmin2;
    float newDmax2 = atof(dmax2Param.getValue());
    if (newDmax2 > 0.0f) DISTANCE_MAX_2 = newDmax2;
    if (strlen(job1Param.getValue()) > 0) strlcpy(JOB1_NAME, job1Param.getValue(), sizeof(JOB1_NAME));
    if (strlen(job2Param.getValue()) > 0) strlcpy(JOB2_NAME, job2Param.getValue(), sizeof(JOB2_NAME));
    if (strlen(job3Param.getValue()) > 0) strlcpy(JOB3_NAME, job3Param.getValue(), sizeof(JOB3_NAME));

    uint16_t newLock = atoi(lockMinParam.getValue());
    if (newLock == 0) newLock = 45;
    LOCK_DURATION_MINUTES = newLock;
    lockDurationMs = (unsigned long)LOCK_DURATION_MINUTES * 60000UL;

    saveParams();
    Serial.printf("[WiFiManager] Saved new config: TDEF=%u T1=%u T2=%u DMIN1=%.1f DMAX1=%.1f DMIN2=%.1f DMAX2=%.1f LOCK=%u\n",
                  TEMP_DEFAULT, TEMP_LEVEL1, TEMP_LEVEL2,
                  DISTANCE_MIN_1, DISTANCE_MAX_1,
                  DISTANCE_MIN_2, DISTANCE_MAX_2,
                  LOCK_DURATION_MINUTES);
}

void connectWiFi() {
    if (WiFi.status() == WL_CONNECTED) return;

    Serial.println("[WiFi] Connecting...");
    WiFi.disconnect(false);
    delay(100);
    WiFi.mode(WIFI_STA);

    if (WiFi.SSID().length() > 0) {
        Serial.println("[WiFi] Attempting stored WiFi credentials.");
        WiFi.begin();
    } else {
        Serial.println("[WiFi] No stored credentials, using built-in SSID.");
        WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    }

    // Blocking connect attempt: wait up to 20 s for WiFi to join.
    uint32_t start = millis();
    while (WiFi.status() != WL_CONNECTED && millis() - start < 20000UL) {
        delay(500);
        Serial.print(".");
    }
    Serial.println();

    if (WiFi.status() == WL_CONNECTED) {
        Serial.printf("[WiFi] Connected. IP: %s\n", WiFi.localIP().toString().c_str());
    } else {
        Serial.println("[WiFi] FAILED — UDP will be skipped this cycle.");
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// PREFERENCES
// ─────────────────────────────────────────────────────────────────────────────
void loadParams() {
    prefs.begin("cfg", true);
    TEMP_DEFAULT   = prefs.getUShort("tdef",  120);
    TEMP_LEVEL1    = prefs.getUShort("t1",    180);
    TEMP_LEVEL2    = prefs.getUShort("t2",    200);
    DISTANCE_MIN_1 = prefs.getFloat ("dmin1",  30.0);
    DISTANCE_MAX_1 = prefs.getFloat ("dmax1",  50.0);
    DISTANCE_MIN_2 = prefs.getFloat ("dmin2",  51.0);
    DISTANCE_MAX_2 = prefs.getFloat ("dmax2",  90.0);
    strlcpy(JOB1_NAME, prefs.getString("job1", "JOB 1").c_str(), sizeof(JOB1_NAME));
    strlcpy(JOB2_NAME, prefs.getString("job2", "JOB 2").c_str(), sizeof(JOB2_NAME));
    strlcpy(JOB3_NAME, prefs.getString("job3", "OTHER").c_str(), sizeof(JOB3_NAME));
    LOCK_DURATION_MINUTES = prefs.getUShort("lockmin", 45);
    if (LOCK_DURATION_MINUTES == 0) LOCK_DURATION_MINUTES = 45;
    lockDurationMs = (unsigned long)LOCK_DURATION_MINUTES * 60000UL;
    prefs.end();

    Serial.printf("[Prefs] TEMP_DEFAULT=%u T1=%u T2=%u\n",
                  TEMP_DEFAULT, TEMP_LEVEL1, TEMP_LEVEL2);
    Serial.printf("[Prefs] D1:[%.1f-%.1f] D2:[%.1f-%.1f]\n",
                  DISTANCE_MIN_1, DISTANCE_MAX_1, DISTANCE_MIN_2, DISTANCE_MAX_2);
    Serial.printf("[Prefs] LOCK_DURATION=%u minutes\n", LOCK_DURATION_MINUTES);
}

void saveParams() {
    prefs.begin("cfg", false);
    prefs.putUShort("tdef",  TEMP_DEFAULT);
    prefs.putUShort("t1",    TEMP_LEVEL1);
    prefs.putUShort("t2",    TEMP_LEVEL2);
    prefs.putFloat ("dmin1", DISTANCE_MIN_1);
    prefs.putFloat ("dmax1", DISTANCE_MAX_1);
    prefs.putFloat ("dmin2", DISTANCE_MIN_2);
    prefs.putFloat ("dmax2", DISTANCE_MAX_2);
    prefs.putString("job1",  JOB1_NAME);
    prefs.putString("job2",  JOB2_NAME);
    prefs.putString("job3",  JOB3_NAME);
    prefs.putUShort("lockmin", LOCK_DURATION_MINUTES);
    prefs.end();
    Serial.println("[Prefs] Parameters saved.");
}

// ─────────────────────────────────────────────────────────────────────────────
// URM15
// ─────────────────────────────────────────────────────────────────────────────
void initURM15() {
    switchBusTo(BUS_URM15);
    urm15.begin(URM15_SLAVE_ID, ModbusSerial);
    urm15.preTransmission(preTransmission);
    urm15.postTransmission(postTransmission);

    uint16_t ctrl = MEASURE_MODE_BIT | TEMP_CPT_ENABLE_BIT;
    uint8_t res = urm15.writeSingleRegister(URM15_REG_CONTROL, ctrl);
    Serial.printf("[URM15] Init result = %u (%s)\n",
                  res, res == ModbusMaster::ku8MBSuccess ? "OK" : "FAIL");
}

// Returns distance in cm, or -1.0 on failure.
float readUrm15Distance() {
    switchBusTo(BUS_URM15);
    urm15.begin(URM15_SLAVE_ID, ModbusSerial);
    urm15.preTransmission(preTransmission);
    urm15.postTransmission(postTransmission);

    uint16_t ctrl = MEASURE_MODE_BIT | TEMP_CPT_ENABLE_BIT | MEASURE_TRIG_BIT;
    uint8_t trigRes = urm15.writeSingleRegister(URM15_REG_CONTROL, ctrl);
    if (trigRes != ModbusMaster::ku8MBSuccess) {
        Serial.println("[URM15] Trigger write failed.");
        return -1.0f;
    }

    delay(80);  // sensor measurement time

    uint8_t readRes = urm15.readHoldingRegisters(URM15_REG_DISTANCE, 1);
    if (readRes != ModbusMaster::ku8MBSuccess) {
        Serial.println("[URM15] Distance read failed.");
        return -1.0f;
    }

    uint16_t raw = urm15.getResponseBuffer(0);
    if (raw == 65535) {
        Serial.println("[URM15] Invalid reading (65535).");
        return -1.0f;
    }

    float d = raw / 10.0f;
    Serial.printf("[URM15] Distance = %.1f cm\n", d);
    return d;
}

// Takes CONFIRM_READS_REQUIRED readings within the reading window.
// Returns the mode confirmed by majority, or 0 if no job confirmed.
// -1 return means sensor totally failed (all reads returned error).
int8_t confirmMode() {
    uint8_t votes[3] = {0, 0, 0};  // votes[0]=no-job, votes[1]=JOB1, votes[2]=JOB2
    uint8_t totalReads = 0;
    uint8_t failedReads = 0;

    for (uint8_t i = 0; i < CONFIRM_READS_REQUIRED; i++) {
        float d = readUrm15Distance();

        if (d < 0) {
            failedReads++;
        } else if (d >= DISTANCE_MIN_1 && d <= DISTANCE_MAX_1) {
            votes[1]++;
        } else if (d >= DISTANCE_MIN_2 && d <= DISTANCE_MAX_2) {
            votes[2]++;
        } else {
            votes[0]++;
        }

        totalReads++;
        delay(300);  // brief gap between reads
    }

    Serial.printf("[CONFIRM] votes — no-job:%u JOB1:%u JOB2:%u failed:%u\n",
                  votes[0], votes[1], votes[2], failedReads);

    // All reads failed → sensor error
    if (failedReads == CONFIRM_READS_REQUIRED) return -1;

    // Majority rules among valid reads
    if (votes[1] > votes[0] && votes[1] >= votes[2]) return 1;
    if (votes[2] > votes[0] && votes[2] >  votes[1]) return 2;
    return 0;  // no-job wins (or tie, which conservatively means no job)
}

// ─────────────────────────────────────────────────────────────────────────────
// CRC16
// ─────────────────────────────────────────────────────────────────────────────
uint16_t modbusCRC16(const uint8_t* buf, uint8_t len) {
    uint16_t crc = 0xFFFF;
    for (uint8_t i = 0; i < len; i++) {
        crc ^= buf[i];
        for (uint8_t b = 0; b < 8; b++) {
            crc = (crc & 1) ? (crc >> 1) ^ 0xA001 : crc >> 1;
        }
    }
    return crc;
}

// ─────────────────────────────────────────────────────────────────────────────
// EUROTHERM — raw frame TX
// ─────────────────────────────────────────────────────────────────────────────
void sendEurothermFrame(const uint8_t* frame, uint8_t len) {
    while (ModbusSerial.available()) ModbusSerial.read();  // flush RX

    digitalWrite(RS485_DE_RE_PIN, HIGH);
    delayMicroseconds(DE_PRE_DELAY_US);

    ModbusSerial.write(frame, len);
    ModbusSerial.flush();

    delay(DE_HOLD_AFTER_FLUSH_MS);
    digitalWrite(RS485_DE_RE_PIN, LOW);
    delay(DE_TO_RX_SETTLE_MS);

    while (ModbusSerial.available()) ModbusSerial.read();  // discard own echo
}

// ─────────────────────────────────────────────────────────────────────────────
// EUROTHERM — FC06 write with echo verification
// ─────────────────────────────────────────────────────────────────────────────
bool writeEurothermRegister(uint16_t reg, uint16_t value) {
    switchBusTo(BUS_EUROTHERM);

    uint16_t addr = reg - 1;  // convert 1-based to 0-based

    uint8_t frame[8];
    frame[0] = EUROTHERM_SLAVE_ID;
    frame[1] = 0x06;
    frame[2] = addr >> 8;
    frame[3] = addr & 0xFF;
    frame[4] = value >> 8;
    frame[5] = value & 0xFF;
    uint16_t crc = modbusCRC16(frame, 6);
    frame[6] = crc & 0xFF;
    frame[7] = crc >> 8;

    Serial.print("[EUR] TX: ");
    for (int i = 0; i < 8; i++) Serial.printf("%02X ", frame[i]);
    Serial.println();

    sendEurothermFrame(frame, 8);
    delay(EUROTHERM_TURNAROUND_MS);

    uint8_t resp[8];
    memset(resp, 0, sizeof(resp));
    uint32_t timeout = millis() + RX_TIMEOUT_MS;
    uint8_t idx = 0;

    while (millis() < timeout && idx < 8) {
        if (ModbusSerial.available()) resp[idx++] = ModbusSerial.read();
    }

    Serial.print("[EUR] RX: ");
    if (idx == 0) {
        Serial.println("(none — timeout)");
        return false;
    }
    for (int i = 0; i < idx; i++) Serial.printf("%02X ", resp[i]);
    Serial.printf("(%d bytes)\n", idx);

    if (idx < 8) {
        Serial.printf("[EUR] Short response: %d bytes\n", idx);
        return false;
    }

    uint16_t calcCRC = modbusCRC16(resp, 6);
    uint16_t rxCRC   = resp[6] | (resp[7] << 8);
    if (calcCRC != rxCRC) {
        Serial.printf("[EUR] CRC mismatch — calc=0x%04X rx=0x%04X\n", calcCRC, rxCRC);
        return false;
    }

    if (resp[0] != EUROTHERM_SLAVE_ID || resp[1] != 0x06) {
        if (resp[1] == 0x86) {
            Serial.printf("[EUR] Modbus exception 0x%02X\n", resp[2]);
        } else {
            Serial.printf("[EUR] Bad response: %02X %02X\n", resp[0], resp[1]);
        }
        return false;
    }

    uint16_t echoAddr  = (resp[2] << 8) | resp[3];
    uint16_t echoValue = (resp[4] << 8) | resp[5];
    if (echoAddr != addr || echoValue != value) {
        Serial.printf("[EUR] Echo mismatch\n");
        return false;
    }

    Serial.printf("[EUR] Write OK — reg=%u val=%u\n", reg, value);
    return true;
}

bool writeEurothermSetpoint(uint16_t sp) {
    bool ok = writeEurothermRegister(EUROTHERM_REG_REMOTE_SP, sp);
    if (!ok) {
        Serial.println("[EUR] Retry in 100ms...");
        delay(100);
        ok = writeEurothermRegister(EUROTHERM_REG_REMOTE_SP, sp);
    }
    return ok;
}

// ─────────────────────────────────────────────────────────────────────────────
// RELAY CONTROL
// ─────────────────────────────────────────────────────────────────────────────
void setRelays(uint8_t mode) {
    if (mode == 1) {
        digitalWrite(RELAY1_PIN, LOW);  relay1State = 0;
        digitalWrite(RELAY2_PIN, HIGH); relay2State = 1;
    } else if (mode == 2) {
        digitalWrite(RELAY1_PIN, HIGH); relay1State = 1;
        digitalWrite(RELAY2_PIN, LOW);  relay2State = 0;
    } else {
        digitalWrite(RELAY1_PIN, HIGH); relay1State = 1;
        digitalWrite(RELAY2_PIN, HIGH); relay2State = 1;
    }
    Serial.printf("[RELAY] Mode %u — R1:%s R2:%s\n",
                  mode,
                  relay1State == 0 ? "ON" : "OFF",
                  relay2State == 0 ? "ON" : "OFF");
}

// ─────────────────────────────────────────────────────────────────────────────
// SETPOINT APPLICATION
// Only writes to Eurotherm and actuates relay if the setpoint actually changes.
// Relay is actuated AFTER confirmed Eurotherm write.
// Returns true if the setpoint was successfully applied (or was already correct).
// ─────────────────────────────────────────────────────────────────────────────
bool applySetpoint(uint8_t mode, uint16_t sp) {
    if (sp == lastSetpoint && mode == currentMode) {
        Serial.printf("[SP] No change (mode=%u sp=%u) — skipping write.\n", mode, sp);
        return true;
    }

    Serial.printf("[SP] Applying mode=%u sp=%u (was mode=%u sp=%u)\n",
                  mode, sp, currentMode, lastSetpoint);

    // Write Eurotherm FIRST, confirm, then actuate relay
    bool ok = writeEurothermSetpoint(sp);
    if (!ok) {
        Serial.println("[SP] Eurotherm write FAILED — relay NOT changed.");
        return false;
    }

    lastSetpoint = sp;
    currentMode  = mode;
    setRelays(mode);
    return true;
}

// ─────────────────────────────────────────────────────────────────────────────
// UDP
// ─────────────────────────────────────────────────────────────────────────────
void sendUDPData(float distance, int8_t detectedMode, bool sensorOk) {
    if (WiFi.status() != WL_CONNECTED) {
        Serial.println("[UDP] Skipped — no WiFi.");
        return;
    }

    unsigned long remainingMs = 0;
    if (cyclePhase == PHASE_LOCKED) {
        unsigned long elapsed = millis() - phaseStartMs;
        remainingMs = (elapsed < lockDurationMs) ? (lockDurationMs - elapsed) : 0;
    }

    char msg[512];
    snprintf(msg, sizeof(msg),
        "Phase=%s,SensorOK=%d,Distance=%.1f,DetectedMode=%d,"
        "ActiveMode=%u,PID=%u,Relay1=%s,Relay2=%s,"
        "NoJobCount=%u,LockRemainMs=%lu,"
        "JOB1=%s,JOB2=%s,JOB3=%s,"
        "TDEF=%u,T1=%u,T2=%u,"
        "DMIN1=%.1f,DMAX1=%.1f,DMIN2=%.1f,DMAX2=%.1f",
        phaseName(cyclePhase),
        sensorOk ? 1 : 0,
        distance,
        detectedMode,
        currentMode,
        lastSetpoint,
        relay1State == 0 ? "ON" : "OFF",
        relay2State == 0 ? "ON" : "OFF",
        noJobCounter,
        remainingMs,
        JOB1_NAME, JOB2_NAME, JOB3_NAME,
        TEMP_DEFAULT, TEMP_LEVEL1, TEMP_LEVEL2,
        DISTANCE_MIN_1, DISTANCE_MAX_1,
        DISTANCE_MIN_2, DISTANCE_MAX_2
    );

    udp.beginPacket(UDP_TARGET_IP, UDP_PORT);
    udp.write((uint8_t*)msg, strlen(msg));
    udp.endPacket();

    Serial.printf("[UDP] Sent: %s\n", msg);
}

// ─────────────────────────────────────────────────────────────────────────────
// PHASE EXECUTION
// ─────────────────────────────────────────────────────────────────────────────

void executeReadingPhase() {
    printDivider("PHASE: READING");
    Serial.printf("[CYCLE] noJobCounter = %u\n", noJobCounter);

    initURM15();

    int8_t detectedMode = confirmMode();  // -1=sensor fail, 0=no job, 1=JOB1, 2=JOB2
    bool   sensorOk     = (detectedMode >= 0);
    float  lastDistance = -1.0f;

    // Take one final reading for the UDP report distance field
    if (sensorOk) {
        lastDistance = readUrm15Distance();
    }

    Serial.printf("[CYCLE] detectedMode = %d | sensorOk = %s\n",
                  detectedMode, sensorOk ? "YES" : "NO");

    if (!sensorOk) {
        // Sensor failure — do not change anything, do not increment counter.
        // Log and move on. The 45-minute lock still engages.
        Serial.println("[CYCLE] Sensor failure — state unchanged.");

    } else if (detectedMode == 1) {
        // JOB 1 detected
        noJobCounter = 0;
        applySetpoint(1, TEMP_LEVEL1);
        Serial.println("[CYCLE] JOB 1 detected.");

    } else if (detectedMode == 2) {
        // JOB 2 detected
        noJobCounter = 0;
        applySetpoint(2, TEMP_LEVEL2);
        Serial.println("[CYCLE] JOB 2 detected.");

    } else {
        // No job detected
        noJobCounter++;
        if (noJobCounter > 2) noJobCounter = 2;  // cap — no higher state exists

        Serial.printf("[CYCLE] No job. Counter now = %u\n", noJobCounter);

        if (noJobCounter == 1) {
            // First absence — keep previous setpoint, no Eurotherm write
            Serial.println("[CYCLE] First no-job — holding current setpoint.");

        } else {
            // noJobCounter == 2: second consecutive absence → go to default
            Serial.printf("[CYCLE] Second no-job — applying TEMP_DEFAULT (%u).\n",
                          TEMP_DEFAULT);
            applySetpoint(0, TEMP_DEFAULT);
        }
    }

    // WiFi + UDP at the very end, after all control decisions are made
    connectWiFi();
    sendUDPData(lastDistance, detectedMode, sensorOk);

    // Transition to LOCKED phase
    cyclePhase    = PHASE_LOCKED;
    phaseStartMs  = millis();
    Serial.printf("[CYCLE] Entering LOCKED phase for %u minutes.\n",
                  LOCK_DURATION_MINUTES);
}

void executeLockedPhase() {
    // During the lock, we block for the full lock duration.
    // Periodic heartbeats are sent every 30 seconds.
    const unsigned long HEARTBEAT_INTERVAL_MS = 30000;  // 30-second heartbeat
    unsigned long lockStart = millis();

    while (millis() - lockStart < lockDurationMs) {
        connectWiFi();
        sendUDPData(-1.0f, -1, false);  // heartbeat — no sensor data

        unsigned long elapsed   = millis() - lockStart;
        unsigned long remaining = (elapsed < lockDurationMs) ? (lockDurationMs - elapsed) : 0;
        Serial.printf("[LOCKED] Heartbeat. Lock remaining: %lu min %lu s\n",
                      remaining / 60000UL, (remaining % 60000UL) / 1000UL);

        if (remaining == 0) break;
        unsigned long delayMs = (remaining < HEARTBEAT_INTERVAL_MS) ? remaining : HEARTBEAT_INTERVAL_MS;
        delay(delayMs);
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// SETUP
// ─────────────────────────────────────────────────────────────────────────────
void setup() {
    Serial.begin(115200);
    delay(200);
    printDivider("URM15 + EUROTHERM 3216 — 45-MIN CYCLE CONTROLLER");

    // GPIO
    pinMode(RS485_DE_RE_PIN, OUTPUT);
    digitalWrite(RS485_DE_RE_PIN, LOW);

    pinMode(RELAY1_PIN, OUTPUT);
    digitalWrite(RELAY1_PIN, HIGH);
    relay1State = 1;

    pinMode(RELAY2_PIN, OUTPUT);
    digitalWrite(RELAY2_PIN, HIGH);
    relay2State = 1;

    pinMode(PUSH_BUTTON_PIN, INPUT_PULLUP);

    Serial.println("[SETUP] GPIO initialised.");

    // Load parameters
    loadParams();

    // Write safe default setpoint on boot — Eurotherm starts at TEMP_DEFAULT.
    // This replaces the old hardcoded test-write to 200°C.
    Serial.printf("[SETUP] Writing boot setpoint: TEMP_DEFAULT = %u\n", TEMP_DEFAULT);
    switchBusTo(BUS_EUROTHERM);
    bool bootOk = writeEurothermSetpoint(TEMP_DEFAULT);
    if (bootOk) {
        lastSetpoint = TEMP_DEFAULT;
        currentMode  = 0;
        Serial.println("[SETUP] Boot setpoint accepted by Eurotherm.");
    } else {
        Serial.println("[SETUP] WARNING: Eurotherm did not accept boot setpoint.");
        Serial.println("         Check wiring, baud, slave ID, Rm.SP enabled.");
    }

    // WiFi (after all hardware comms)
    if (digitalRead(PUSH_BUTTON_PIN) == LOW && isConfigButtonHeld()) {
        startWiFiConfigPortal();
    }
    connectWiFi();
    udp.begin(UDP_PORT);
    Serial.printf("[SETUP] UDP ready on port %u\n", UDP_PORT);

    // Start the first reading phase immediately
    cyclePhase   = PHASE_READING;
    phaseStartMs = millis();

    Serial.println("[SETUP] Setup complete. Entering first READING phase.");
}

// ─────────────────────────────────────────────────────────────────────────────
// LOOP
// ─────────────────────────────────────────────────────────────────────────────
void loop() {
    switch (cyclePhase) {

        case PHASE_READING:
            // Execute reading phase (blocking for READING_WINDOW_MS worth of reads)
            executeReadingPhase();
            // After this returns, cyclePhase is PHASE_LOCKED
            break;

        case PHASE_LOCKED: {
            unsigned long elapsed = millis() - phaseStartMs;
            if (elapsed >= lockDurationMs) {
                // Lock expired — begin next reading phase
                printDivider("LOCK EXPIRED — STARTING NEXT READING PHASE");
                cyclePhase   = PHASE_READING;
                phaseStartMs = millis();
                // Loop will immediately execute reading phase on next iteration
            } else {
                // Still locked — send heartbeats, nothing else
                executeLockedPhase();
            }
            break;
        }
    }
}