





/*
  ============================================================
  Arduino Mega — PlatformIO
  ============================================================
  - Non-blocking (zero delay())
  - Watchdog failsafe via avr/wdt
  - Serial1 <-> ESP32  pin 18(TX1) / 19(RX1)
  - Buttons (INPUT_PULLUP -> GND)
      pin 22 = SPEED1  (2400ms interval, needs >=1000 credit)
      pin 24 = SPEED2  (2000ms interval, needs >=1000 credit)
      pin 26 = SPEED3  (1400ms interval, needs >=2000 credit)
      pin 28 = RESET
  - Coin detector  pin 2 (INT0)
      1-2 pulses =  500
      3-5 pulses = 1000
      6   pulses = 2000
  - 10 PWM outputs: pins 3,5,6,7,8,9,10,11,12,44
  - Random release sequence (Fisher-Yates)
  - ESP32 commands: SET:PWM_ON, SET:SPD1/2/3, SET:PAYMENT, D
  ============================================================
*/

#include <Arduino.h>
#include <avr/wdt.h>




// -- LED PINS
// 74HC595 shift register driving the 7-segment digit (reuses old mux pins)
#define SEG_DATA   A0   // DS    (serial data)
#define SEG_LATCH  A1   // ST_CP (storage/latch clock)
#define SEG_CLOCK  A2   // SH_CP (shift clock)
const int LED1 = A3;   // STATE_RESET
const int LED2 = A4;   // STATE_RELEASING + last STATE_SPEED_1
const int LED3 = A5;   // STATE_RELEASING + last STATE_SPEED_2
const int LED4 = A6;   // STATE_RELEASING + last STATE_SPEED_3

// ── PWM Output Pins ───────────────────────────────────────
const uint8_t PWM_PINS[10] = { 3, 5, 6, 7, 8, 9, 10, 11, 12, 44 };
#define PWM_COUNT 10
uint8_t PWM_ON  = 100;  // active duty cycle  (0-255), changeable via ESP32
uint8_t PWM_OFF =   0;  // released duty cycle

// ── Button Pins ───────────────────────────────────────────
#define BTN_SPEED1  22
#define BTN_SPEED2  24
#define BTN_SPEED3  26
#define BTN_RESET   28

// ── Coin Detector ─────────────────────────────────────────
#define COIN_PIN        2
#define COIN_PULSE_GAP  300UL   // ms silence = burst complete
#define COIN_SUM_MAX    100000UL // hard cap — stops a stuck coin line creating infinite credit

// ── Timing ───────────────────────────────────────────────
#define RESET_TIMEOUT_MS  60000UL

uint32_t speed1IntervalMs = 2200UL;
uint32_t speed2IntervalMs = 1500UL;
uint32_t speed3IntervalMs =  900UL;

// ── States ───────────────────────────────────────────────
enum SystemState : uint8_t {
  STATE_IDLE,
  STATE_RESET,
  STATE_SPEED_1,
  STATE_SPEED_2,
  STATE_SPEED_3,
  STATE_RELEASING,
  STATE_DONE
};

// ── Globals ──────────────────────────────────────────────
SystemState currentState = STATE_IDLE;
SystemState lastState    = STATE_IDLE;
SystemState ledSpeedState = STATE_IDLE;  // ← ADD THIS

uint8_t  sequence[10];
bool     seeded = false;

bool     FirstRelease = false;

uint8_t  releaseIndex    = 0;
uint32_t lastReleaseMs   = 0;
uint32_t releaseInterval = 1400UL;
uint32_t resetEnteredMs  = 0;
uint32_t ReleaseTimer    = 0;
uint32_t WaitTime        = 5000UL;
volatile uint8_t  coinPulseCount  = 0;
volatile uint32_t lastPulseMs     = 0;
uint32_t          lastButtonMs    = 0;   // timestamp of last button press
#define BUTTON_NOISE_GUARD  80UL         // ignore coin pulses within 80ms of any button press
uint32_t          coinSum        = 0;

bool PAYMENT_REQUIRED = true;

// ── Button debounce ──────────────────────────────────────
struct Button {
  uint8_t  pin;
  bool     lastRaw;
  bool     stable;
  uint32_t lastChangeMs;
  bool     pressed;
};

static const uint8_t DEBOUNCE_MS = 10;   // reduced from 20ms for better button sensitivity

Button buttons[4] = {
  { BTN_SPEED1, HIGH, HIGH, 0, false },
  { BTN_SPEED2, HIGH, HIGH, 0, false },
  { BTN_SPEED3, HIGH, HIGH, 0, false },
  { BTN_RESET,  HIGH, HIGH, 0, false },
};

// ── Serial TX ring buffer ────────────────────────────────
// Buffer must hold full diagnostic (~380 bytes) comfortably
static const uint16_t TX_BUF_SIZE = 512;
char     txBuf[TX_BUF_SIZE];
uint16_t txHead = 0;
uint16_t txTail = 0;

inline bool txEmpty() { return txHead == txTail; }
inline bool txFull()  { return ((txTail + 1) % TX_BUF_SIZE) == txHead; }

void txEnqueue(char c) {
  if (!txFull()) {
    txBuf[txTail] = c;
    txTail = (uint16_t)((txTail + 1) % TX_BUF_SIZE);
  }
}
void txEnqueueStr(const char* s) { while (*s) txEnqueue(*s++); }

// ── Forward declarations ──────────────────────────────────
void generateSequence();
void handleButtons();
void handleState();
void handleReleaseSequencer();
void handleResetTimeout();
void handleCoinDetector();
void setAllPWM(uint8_t value);
void handleESP32_RX();
void handleESP32_TX();
void onReceiveFromESP32(const char* msg);
void onSendToESP32();
void runDiagnostic();
int  freeRam();
void allLedsOff();
void updateLeds();

// ── 7-segment via 74HC595 ─────────────────────────────────
// ACTUAL wiring (verified by interactive bit-by-bit mapping 2026-06-18):
// QH (bit 0) -> d   (bottom)
// QG (bit 1) -> b   (top right)
// QF (bit 2) -> c   (bottom right)
// QE (bit 3) -> e   (bottom left)
// QD (bit 4) -> a   (top)
// QC (bit 5) -> f   (top left)
// QB (bit 6) -> g   (middle)
// QA (bit 7) -> NOT CONNECTED
#define SEG_A 0b00010000  // QD bit4
#define SEG_B 0b00000010  // QG bit1
#define SEG_C 0b00000100  // QF bit2
#define SEG_D 0b00000001  // QH bit0
#define SEG_E 0b00001000  // QE bit3
#define SEG_F 0b00100000  // QC bit5
#define SEG_G 0b01000000  // QB bit6

// Common-cathode: a set bit lights its segment.
static const uint8_t SEG_DIGITS[10] = {
  SEG_A | SEG_B | SEG_C | SEG_D | SEG_E | SEG_F,         // 0
  SEG_B | SEG_C,                                         // 1
  SEG_A | SEG_B | SEG_D | SEG_E | SEG_G,                 // 2
  SEG_A | SEG_B | SEG_C | SEG_D | SEG_G,                 // 3
  SEG_B | SEG_C | SEG_F | SEG_G,                         // 4
  SEG_A | SEG_C | SEG_D | SEG_F | SEG_G,                 // 5
  SEG_A | SEG_C | SEG_D | SEG_E | SEG_F | SEG_G,         // 6
  SEG_A | SEG_B | SEG_C,                                 // 7
  SEG_A | SEG_B | SEG_C | SEG_D | SEG_E | SEG_F | SEG_G, // 8
  SEG_A | SEG_B | SEG_C | SEG_D | SEG_F | SEG_G,         // 9
};

void LedDisplay();

// ═════════════════════════════════════════════════════════
//  COIN ISR
// ═════════════════════════════════════════════════════════
void coinISR() {
  // Ignore pulses within BUTTON_NOISE_GUARD ms of any button press
  // This kills false triggers caused by GND noise when buttons close
  if ((millis() - lastButtonMs) < BUTTON_NOISE_GUARD) return;
  coinPulseCount++;
  lastPulseMs = millis();
}

// ═════════════════════════════════════════════════════════
//  SETUP
// ═════════════════════════════════════════════════════════
void setup() {
  wdt_enable(WDTO_2S);

  Serial1.begin(115200);  // pin 18 TX1 -> ESP32 RX | pin 19 RX1 -> ESP32 TX

  for (uint8_t i = 0; i < PWM_COUNT; i++) {
    pinMode(PWM_PINS[i], OUTPUT);
    analogWrite(PWM_PINS[i], PWM_OFF);
  }

  // 74HC595 control pins
  pinMode(SEG_DATA,  OUTPUT);
  pinMode(SEG_CLOCK, OUTPUT);
  pinMode(SEG_LATCH, OUTPUT);
  pinMode(LED1, OUTPUT);
  pinMode(LED2, OUTPUT);
  pinMode(LED3, OUTPUT);
  pinMode(LED4, OUTPUT);
  allLedsOff();

  for (auto& b : buttons) {
    pinMode(b.pin, INPUT_PULLUP);
    b.lastRaw = digitalRead(b.pin);
    b.stable  = b.lastRaw;
  }

  pinMode(COIN_PIN, INPUT_PULLUP);
  attachInterrupt(digitalPinToInterrupt(COIN_PIN), coinISR, FALLING);

  for (uint8_t i = 0; i < 10; i++) sequence[i] = i;
}

// ═════════════════════════════════════════════════════════
//  LOOP
// ═════════════════════════════════════════════════════════
void loop() {
  wdt_reset();

  handleButtons();
  handleState();
  handleReleaseSequencer();
  handleResetTimeout();
  handleCoinDetector();
  handleESP32_RX();
  handleESP32_TX();
  updateLeds();
  LedDisplay();
}

// ═════════════════════════════════════════════════════════
//  BUTTON DEBOUNCE & EDGE DETECTION
// ═════════════════════════════════════════════════════════
void handleButtons() {
  uint32_t now = millis();

  for (auto& b : buttons) {
    b.pressed = false;
    bool raw  = digitalRead(b.pin);

    if (raw != b.lastRaw) {
      b.lastRaw      = raw;
      b.lastChangeMs = now;
    }

    if ((now - b.lastChangeMs) >= DEBOUNCE_MS) {
      if (b.stable == HIGH && raw == LOW) {
        b.pressed    = true;
        lastButtonMs = millis();   // record for coin noise guard
        if (!seeded) {
          randomSeed(micros());
          seeded = true;
          generateSequence();
        }
      }
      b.stable = raw;
    }
  }

  // RESET blocked during STATE_RELEASING — sequence must finish
  // Speed buttons only valid in STATE_RESET and only if credit is sufficient
  if (buttons[3].pressed) {
    if (currentState != STATE_RELEASING) currentState = STATE_RESET;
  } else if (buttons[2].pressed) {
    if (currentState == STATE_RESET && (!PAYMENT_REQUIRED || coinSum >= 2000)) {
      currentState = STATE_SPEED_3;
    } else if (currentState == STATE_RESET && PAYMENT_REQUIRED) {
      char buf[32];
      snprintf(buf, sizeof(buf), "ERR:NEED2000:HAVE%lu\n", coinSum);
      txEnqueueStr(buf);
    }
  } else if (buttons[1].pressed) {
    if (currentState == STATE_RESET && (!PAYMENT_REQUIRED || coinSum >= 1000)) {
      currentState = STATE_SPEED_2;
    } else if (currentState == STATE_RESET && PAYMENT_REQUIRED) {
      char buf[32];
      snprintf(buf, sizeof(buf), "ERR:NEED1000:HAVE%lu\n", coinSum);
      txEnqueueStr(buf);
    }
  } else if (buttons[0].pressed) {
    if (currentState == STATE_RESET && (!PAYMENT_REQUIRED || coinSum >= 1000)) {
      currentState = STATE_SPEED_1;
    } else if (currentState == STATE_RESET && PAYMENT_REQUIRED) {
      char buf[32];
      snprintf(buf, sizeof(buf), "ERR:NEED1000:HAVE%lu\n", coinSum);
      txEnqueueStr(buf);
    }
  }
}

// ═════════════════════════════════════════════════════════
//  STATE MACHINE
// ═════════════════════════════════════════════════════════
void handleState() {
  if (currentState == lastState) return;

  switch (currentState) {

    case STATE_RESET:
      generateSequence();
      setAllPWM(PWM_ON);
      resetEnteredMs = millis();
      releaseIndex   = 0;
      lastState      = STATE_RESET;
      onSendToESP32();
      break;

    case STATE_SPEED_1:
      ledSpeedState = STATE_SPEED_1;
      releaseInterval = speed1IntervalMs;
      releaseIndex    = 0;
      lastReleaseMs   = millis();
      FirstRelease    = true;
      ReleaseTimer    = 0;
      lastState       = STATE_SPEED_1;
      onSendToESP32();
      currentState    = STATE_RELEASING;
      return;

    case STATE_SPEED_2:
      ledSpeedState = STATE_SPEED_2;
      releaseInterval = speed2IntervalMs;
      releaseIndex    = 0;
      lastReleaseMs   = millis();
      FirstRelease    = true;
      ReleaseTimer    = 0;
      lastState       = STATE_SPEED_2;
      onSendToESP32();
      currentState    = STATE_RELEASING;
      return;

    case STATE_SPEED_3:
      ledSpeedState = STATE_SPEED_3;
      releaseInterval = speed3IntervalMs;
      releaseIndex    = 0;
      lastReleaseMs   = millis();
      FirstRelease    = true;
      ReleaseTimer    = 0;
      lastState       = STATE_SPEED_3;
      onSendToESP32();
      currentState    = STATE_RELEASING;
      return;

    case STATE_RELEASING:
      break;

    case STATE_DONE:
      setAllPWM(PWM_OFF);
      coinSum = 0;
      onSendToESP32();
      break;

    case STATE_IDLE:
      ledSpeedState = STATE_IDLE;   // clear so LEDs don't show a stale speed
      onSendToESP32();             // notify ESP32 the machine went idle
      break;

    default:
      break;
  }

  lastState = currentState;
}

// ═════════════════════════════════════════════════════════
//  RELEASE SEQUENCER
// ═════════════════════════════════════════════════════════
void handleReleaseSequencer() {
  if (currentState != STATE_RELEASING) return;

  if (releaseIndex >= PWM_COUNT) {
    currentState = STATE_DONE;
    return;
  }

  uint32_t now = millis();
  if (FirstRelease){
    if ((now - lastReleaseMs) < WaitTime) {
      ReleaseTimer = WaitTime - (now - lastReleaseMs);
      return;
    }
  }
  FirstRelease = false;
  if ((now - lastReleaseMs) < releaseInterval) return;

  lastReleaseMs = now;
  analogWrite(PWM_PINS[sequence[releaseIndex]], PWM_OFF);
  releaseIndex++;
}

// ═════════════════════════════════════════════════════════
//  RESET TIMEOUT
// ═════════════════════════════════════════════════════════
void handleResetTimeout() {
  if (currentState != STATE_RESET) return;

  if ((millis() - resetEnteredMs) >= RESET_TIMEOUT_MS) {
    setAllPWM(PWM_OFF);
    coinSum = 0;            // abandoned game — don't carry credit into next round
    currentState = STATE_IDLE;
  }
}

// ═════════════════════════════════════════════════════════
//  COIN DETECTOR (pulse-count ranges — tolerant of coin metal/size variants)
//  1-2 pulses -> +500
//  3-5 pulses -> +1000
//  6   pulses -> +2000
// ═════════════════════════════════════════════════════════
void handleCoinDetector() {
  if (coinPulseCount == 0) return;

  // Snapshot volatile multi-byte lastPulseMs atomically — a non-atomic 4-byte
  // read on 8-bit AVR can tear if the coin ISR fires mid-read.
  noInterrupts();
  uint32_t lastPulseSnap = lastPulseMs;
  interrupts();

  if ((millis() - lastPulseSnap) < COIN_PULSE_GAP) return;

  noInterrupts();
  uint8_t pulses = coinPulseCount;
  coinPulseCount = 0;
  interrupts();

  // Coin value by pulse-count RANGE — same-value coins of different metal/size
  // can emit different pulse counts, so we accept bands rather than exact counts:
  //   1-2 pulses ->  500
  //   3-5 pulses -> 1000
  //   6   pulses -> 2000
  //   anything else (0, 7+) -> ignored
  uint16_t value = 0;
  if      (pulses >= 1 && pulses <= 2) value =  500;
  else if (pulses >= 3 && pulses <= 5) value = 1000;
  else if (pulses == 6)                value = 2000;

  if (value > 0) {
    coinSum += value;
    if (coinSum > COIN_SUM_MAX) coinSum = COIN_SUM_MAX;  // clamp on fault
    char buf[32];
    snprintf(buf, sizeof(buf), "COIN:+%u:SUM%lu\n", value, coinSum);
    txEnqueueStr(buf);
  }
}

// ═════════════════════════════════════════════════════════
//  HELPER
// ═════════════════════════════════════════════════════════
void setAllPWM(uint8_t value) {
  for (uint8_t i = 0; i < PWM_COUNT; i++) {
    analogWrite(PWM_PINS[i], value);
  }
}

// ═════════════════════════════════════════════════════════
//  ESP32 RX
// ═════════════════════════════════════════════════════════
void handleESP32_RX() {
  static char     rxBuf[128];
  static uint8_t  rxLen = 0;
  while (Serial1.available()) {
    char c = Serial1.read();
    if (c == '\n' || c == '\r') {
      if (rxLen > 0) {
        rxBuf[rxLen] = '\0';
        onReceiveFromESP32(rxBuf);
        rxLen = 0;
      }
    } else if (rxLen < sizeof(rxBuf) - 1) {
      rxBuf[rxLen++] = c;
    } else {
      rxLen = 0;   // overflow — drop the line
    }
  }
}

// ═════════════════════════════════════════════════════════
//  ESP32 TX
// ═════════════════════════════════════════════════════════
void handleESP32_TX() {
  while (!txEmpty() && Serial1.availableForWrite() > 0) {
    Serial1.write(txBuf[txHead]);
    txHead = (uint16_t)((txHead + 1) % TX_BUF_SIZE);
  }
}

// ═════════════════════════════════════════════════════════
//  RECEIVE FROM ESP32
//  Commands:
//    D                  -> diagnostic snapshot
//    SET:PWM_ON:<0-255> -> change active PWM duty
//    SET:SPD1:<ms>      -> change speed 1 interval
//    SET:SPD2:<ms>      -> change speed 2 interval
//    SET:SPD3:<ms>      -> change speed 3 interval
//    SET:PAYMENT:<0|1>  -> payment mode on/off
//  Responses:
//    ACK:<key>:<val>    -> applied
//    ERR:<reason>       -> rejected
// ═════════════════════════════════════════════════════════
void onReceiveFromESP32(const char* msg) {
  if (strcmp(msg, "D") == 0) {
    runDiagnostic();
    return;
  }

  if (strncmp(msg, "SET:", 4) == 0) {
    char ackBuf[32];
    const char* key       = msg + 4;
    const char* valStr    = strchr(key, ':');

    if (valStr == NULL) {
      txEnqueueStr("ERR:malformed\n");
      return;
    }

    uint8_t keyLen = (uint8_t)(valStr - key);   // length of key before the ':'
    valStr++;                                    // skip the ':'
    long val = strtol(valStr, NULL, 10);

    // Helper macro: true if key matches name exactly (length + content)
    #define KEY_IS(name) (keyLen == (sizeof(name) - 1) && strncmp(key, name, keyLen) == 0)

    if (KEY_IS("PWM_ON")) {
      if (val < 0 || val > 255) { txEnqueueStr("ERR:PWM_ON:0-255\n"); return; }
      PWM_ON = (uint8_t)val;
      snprintf(ackBuf, sizeof(ackBuf), "ACK:PWM_ON:%u\n", PWM_ON);
      txEnqueueStr(ackBuf);
      return;
    }

    if (KEY_IS("SPD1")) {
      if (val < 50 || val > 60000) { txEnqueueStr("ERR:SPD1:50-60000\n"); return; }
      speed1IntervalMs = (uint32_t)val;
      snprintf(ackBuf, sizeof(ackBuf), "ACK:SPD1:%lu\n", speed1IntervalMs);
      txEnqueueStr(ackBuf);
      return;
    }

    if (KEY_IS("SPD2")) {
      if (val < 50 || val > 60000) { txEnqueueStr("ERR:SPD2:50-60000\n"); return; }
      speed2IntervalMs = (uint32_t)val;
      snprintf(ackBuf, sizeof(ackBuf), "ACK:SPD2:%lu\n", speed2IntervalMs);
      txEnqueueStr(ackBuf);
      return;
    }

    if (KEY_IS("SPD3")) {
      if (val < 50 || val > 60000) { txEnqueueStr("ERR:SPD3:50-60000\n"); return; }
      speed3IntervalMs = (uint32_t)val;
      snprintf(ackBuf, sizeof(ackBuf), "ACK:SPD3:%lu\n", speed3IntervalMs);
      txEnqueueStr(ackBuf);
      return;
    }

    if (KEY_IS("PAYMENT")) {
      if (val != 0 && val != 1) { txEnqueueStr("ERR:PAYMENT:0or1\n"); return; }
      PAYMENT_REQUIRED = (bool)val;
      snprintf(ackBuf, sizeof(ackBuf), "ACK:PAYMENT:%u\n", (uint8_t)PAYMENT_REQUIRED);
      txEnqueueStr(ackBuf);
      return;
    }

    #undef KEY_IS

    txEnqueueStr("ERR:unknownkey\n");
    return;
  }

  txEnqueueStr("ERR:unknowncmd\n");
}

// ═════════════════════════════════════════════════════════
//  SEND TO ESP32
//  Called on every state transition — fill in as needed
// ═════════════════════════════════════════════════════════
void onSendToESP32() {
  // ── YOUR CODE HERE ────────────────────────────────────
}

// ═════════════════════════════════════════════════════════
//  FREE RAM HELPER (AVR)
// ═════════════════════════════════════════════════════════
int freeRam() {
  extern int __heap_start, *__brkval;
  int v;
  return (int)&v - (__brkval == 0 ? (int)&__heap_start : (int)__brkval);
}

// ═════════════════════════════════════════════════════════
//  DIAGNOSTIC — on demand via ESP32 "D" command
//  Sends DIAG| lines to ESP32 via TX ring buffer
// ═════════════════════════════════════════════════════════
void runDiagnostic() {
  // Write diagnostic DIRECTLY to Serial1 — bypasses ring buffer entirely.
  // This guarantees the ESP32 receives a complete, uninterrupted block.
  // Serial1.print() on AVR uses the hardware UART TX buffer (64 bytes) and
  // blocks only briefly per line — total ~20ms at 115200 baud. Safe.
  uint32_t now = millis();
  char buf[48];

  // Atomic snapshot of volatile lastPulseMs (written in coin ISR)
  noInterrupts();
  uint32_t lastPulseSnap = lastPulseMs;
  interrupts();

  Serial1.println(F("DIAG|START"));

  snprintf(buf, sizeof(buf), "DIAG|uptime:%lus",      now / 1000UL);               Serial1.println(buf);
  snprintf(buf, sizeof(buf), "DIAG|ram:%d",            freeRam());                  Serial1.println(buf);
  snprintf(buf, sizeof(buf), "DIAG|state:%u",          (uint8_t)currentState);      Serial1.println(buf);
  snprintf(buf, sizeof(buf), "DIAG|lastState:%u",      (uint8_t)lastState);         Serial1.println(buf);
  snprintf(buf, sizeof(buf), "DIAG|seeded:%u",         (uint8_t)seeded);            Serial1.println(buf);
  snprintf(buf, sizeof(buf), "DIAG|releaseIdx:%u",     releaseIndex);               Serial1.println(buf);
  snprintf(buf, sizeof(buf), "DIAG|releaseIntvl:%lu",  releaseInterval);            Serial1.println(buf);
  snprintf(buf, sizeof(buf), "DIAG|coinSum:%lu",       coinSum);                    Serial1.println(buf);
  snprintf(buf, sizeof(buf), "DIAG|lastPulse:%lums",
    lastPulseSnap == 0 ? 0UL : now - lastPulseSnap);                               Serial1.println(buf);
  snprintf(buf, sizeof(buf), "DIAG|payment:%u",        (uint8_t)PAYMENT_REQUIRED);  Serial1.println(buf);
  snprintf(buf, sizeof(buf), "DIAG|pwmOn:%u",          PWM_ON);                     Serial1.println(buf);
  snprintf(buf, sizeof(buf), "DIAG|spd1:%lu",          speed1IntervalMs);           Serial1.println(buf);
  snprintf(buf, sizeof(buf), "DIAG|spd2:%lu",          speed2IntervalMs);           Serial1.println(buf);
  snprintf(buf, sizeof(buf), "DIAG|spd3:%lu",          speed3IntervalMs);           Serial1.println(buf);
  snprintf(buf, sizeof(buf), "DIAG|btn:%u%u%u%u",
    (uint8_t)(digitalRead(buttons[0].pin) == LOW),
    (uint8_t)(digitalRead(buttons[1].pin) == LOW),
    (uint8_t)(digitalRead(buttons[2].pin) == LOW),
    (uint8_t)(digitalRead(buttons[3].pin) == LOW));                                  Serial1.println(buf);
  snprintf(buf, sizeof(buf), "DIAG|coinPin:%u",
    (uint8_t)(digitalRead(COIN_PIN) == LOW));                                        Serial1.println(buf);

  if (currentState == STATE_RESET) {
    uint32_t elapsed   = now - resetEnteredMs;
    uint32_t remaining = (elapsed < RESET_TIMEOUT_MS) ? (RESET_TIMEOUT_MS - elapsed) : 0;
    snprintf(buf, sizeof(buf), "DIAG|resetTmo:%lus", remaining / 1000UL);
    Serial1.println(buf);
  }

  Serial1.println(F("DIAG|END"));
  Serial1.flush();   // wait until every byte is physically transmitted
}

// ═════════════════════════════════════════════════════════
//  RANDOM SEQUENCE GENERATOR (Fisher-Yates)
// ═════════════════════════════════════════════════════════
void generateSequence() {
  for (uint8_t i = 0; i < 10; i++) sequence[i] = i;
  for (uint8_t i = 9; i > 0; i--) {
    uint8_t j   = random(0, i + 1);
    uint8_t tmp = sequence[i];
    sequence[i] = sequence[j];
    sequence[j] = tmp;
  }
}

// Push one full byte (8 segment bits) into the 74HC595 and latch it.
// MSBFIRST + this exact pin order (DATA=A0, LATCH=A1, CLOCK=A2) matches the
// known-good standalone test sketch.
void segWrite(uint8_t pattern) {
  digitalWrite(SEG_LATCH, LOW);
  shiftOut(SEG_DATA, SEG_CLOCK, MSBFIRST, pattern);
  digitalWrite(SEG_LATCH, HIGH);
}

void LedDisplay() {
  static uint8_t lastPattern = 0xFF;  // force a write on first call

  // Countdown digit during the initial 5s wait before the release sequence.
  // Computed directly from elapsed time so it's independent of the sequencer's
  // update order. While waiting: WaitTime=5000ms -> shows 5,4,3,2,1.
  uint8_t pattern = 0x00;  // blank by default

  if (currentState == STATE_RELEASING && FirstRelease) {
    // Solid countdown digit during the initial 5s wait (5..1).
    uint32_t elapsed = millis() - lastReleaseMs;        // ms since wait started
    if (elapsed < WaitTime) {
      uint32_t remaining = WaitTime - elapsed;          // ms left
      uint32_t secondsLeft = (remaining + 999) / 1000;  // round up: 5..1
      if (secondsLeft < 1) secondsLeft = 1;
      uint8_t digit = (secondsLeft <= 9) ? (uint8_t)secondsLeft : 9;
      pattern = SEG_DIGITS[digit];
    }
  } else if (currentState == STATE_RESET) {
    // Slow-blinking "0" while waiting for a speed button (RESET cooldown).
    // 1400ms period: ~700ms ON, ~700ms OFF — clearly visible, not fast.
    bool on = (millis() % 1400UL) < 700UL;
    pattern = on ? SEG_DIGITS[0] : 0x00;
  }

  if (pattern != lastPattern) {  // only touch the register when it changes
    segWrite(pattern);
    lastPattern = pattern;
  }
}

 
// ─── Helper: turn all LEDs off ───────────────────────────────────────────────
void allLedsOff() {
  digitalWrite(LED1, LOW);
  digitalWrite(LED2, LOW);
  digitalWrite(LED3, LOW);
  digitalWrite(LED4, LOW);
}


// ─── Core logic: light the correct LED based on state combination ────────────
void updateLeds() {
  static int activeLed = -1;

  int desiredLed = -1;

  if (currentState == STATE_RESET) {
    desiredLed = LED1;
  } else if (currentState == STATE_RELEASING) {
    if      (ledSpeedState == STATE_SPEED_1) desiredLed = LED4;  // slowest -> LED4
    else if (ledSpeedState == STATE_SPEED_2) desiredLed = LED3;
    else if (ledSpeedState == STATE_SPEED_3) desiredLed = LED2;  // fastest -> LED2
  }

  if (desiredLed == activeLed) return;  // nothing changed, skip digitalWrite

  allLedsOff();
  if (desiredLed != -1) digitalWrite(desiredLed, HIGH);
  activeLed = desiredLed;
}