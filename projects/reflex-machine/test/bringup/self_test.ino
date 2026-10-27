/*
 * Reflex Machine - bring-up self-test
 *
 * Upload this INSTEAD of the game firmware the first time the manufactured board is powered up.
 * It never runs the game logic - it only exercises each subsystem in isolation, in a fixed order,
 * printing what it's doing to the USB Serial Monitor (115200 baud) so a human can check each step
 * against test/bringup/CHECKLIST.md before trusting the board with the real firmware.
 *
 * Pin numbers match gen/netlist.py exactly (checked by test/pinmap.py) - do not hand-edit them here,
 * fix netlist.py and the game firmware together if a pin ever needs to change.
 */

const uint8_t MAG_PINS[10] = {3, 5, 6, 7, 8, 9, 10, 11, 12, 44};
const uint8_t BTN_PINS[4]  = {22, 24, 26, 28};   // S1, S2, S3, RST
const char*   BTN_NAMES[4] = {"S1", "S2", "S3", "RST"};
const uint8_t COIN_PIN     = 2;
const uint8_t LED_PINS[4]  = {A3, A4, A5, A6};
const uint8_t SEG_DATA     = A0;
const uint8_t SEG_LATCH    = A1;
const uint8_t SEG_CLOCK    = A2;

// Same bit map as the real firmware (common-cathode, bit set = segment lit).
const uint8_t DIGIT[10] = {
  0b11101101, 0b00100001, 0b11001100, 0b01101100, 0b00100011,
  0b01101010, 0b11101010, 0b00100101, 0b11101011, 0b01101011,
};

void segWrite(uint8_t pattern) {
  digitalWrite(SEG_LATCH, LOW);
  shiftOut(SEG_DATA, SEG_CLOCK, MSBFIRST, pattern);
  digitalWrite(SEG_LATCH, HIGH);
}

void setup() {
  Serial.begin(115200);
  while (!Serial) {}
  Serial.println(F("=== Reflex Machine bring-up self-test ==="));
  Serial.println(F("Compare each step against test/bringup/CHECKLIST.md"));

  for (uint8_t i = 0; i < 10; i++) { pinMode(MAG_PINS[i], OUTPUT); analogWrite(MAG_PINS[i], 0); }
  for (uint8_t i = 0; i < 4; i++)  { pinMode(BTN_PINS[i], INPUT_PULLUP); }
  pinMode(COIN_PIN, INPUT_PULLUP);
  for (uint8_t i = 0; i < 4; i++)  { pinMode(LED_PINS[i], OUTPUT); digitalWrite(LED_PINS[i], LOW); }
  pinMode(SEG_DATA, OUTPUT);
  pinMode(SEG_LATCH, OUTPUT);
  pinMode(SEG_CLOCK, OUTPUT);
  segWrite(0);

  delay(1000);
}

void testStatusLeds() {
  Serial.println(F("\n[1/5] Status LEDs A3-A6: each should light for 500ms, one at a time."));
  for (uint8_t i = 0; i < 4; i++) {
    Serial.print(F("  LED")); Serial.println(i + 1);
    digitalWrite(LED_PINS[i], HIGH);
    delay(500);
    digitalWrite(LED_PINS[i], LOW);
  }
}

void testSevenSeg() {
  Serial.println(F("\n[2/5] 7-segment: should count 0-9, ~400ms per digit."));
  for (uint8_t d = 0; d < 10; d++) {
    Serial.print(F("  digit ")); Serial.println(d);
    segWrite(DIGIT[d]);
    delay(400);
  }
  segWrite(0);
}

// LOW DUTY, SHORT PULSE ONLY - this is a wiring check, not a load test. Do not extend PULSE_MS
// without checking the magnet's real current draw first (see HANDOVER.md open question).
void testMagnets() {
  const uint16_t PULSE_MS = 150;
  Serial.println(F("\n[3/5] Magnets 1-10: each should click/energize briefly, one at a time."));
  Serial.println(F("  WATCH FOR HEAT - stop immediately (power off) if anything gets warm fast."));
  for (uint8_t i = 0; i < 10; i++) {
    Serial.print(F("  MAG")); Serial.println(i + 1);
    analogWrite(MAG_PINS[i], 255);
    delay(PULSE_MS);
    analogWrite(MAG_PINS[i], 0);
    delay(400);   // cool-down gap between magnets
  }
}

void testButtons() {
  Serial.println(F("\n[4/5] Buttons: press each one within 10s. Reports LOW (pressed) once per button."));
  bool seen[4] = {false, false, false, false};
  uint32_t start = millis();
  while (millis() - start < 10000) {
    bool allSeen = true;
    for (uint8_t i = 0; i < 4; i++) {
      if (!seen[i] && digitalRead(BTN_PINS[i]) == LOW) {
        seen[i] = true;
        Serial.print(F("  ")); Serial.print(BTN_NAMES[i]); Serial.println(F(" pressed - OK"));
      }
      allSeen &= seen[i];
    }
    if (allSeen) break;
  }
  for (uint8_t i = 0; i < 4; i++) {
    if (!seen[i]) { Serial.print(F("  ")); Serial.print(BTN_NAMES[i]); Serial.println(F(" - NOT SEEN (check wiring)")); }
  }
}

void testCoin() {
  Serial.println(F("\n[5/5] Coin input: insert one coin/token within 10s."));
  uint32_t start = millis();
  bool seen = false;
  while (millis() - start < 10000) {
    if (digitalRead(COIN_PIN) == LOW) { seen = true; break; }
  }
  Serial.println(seen ? F("  Coin pulse detected - OK") : F("  NOT SEEN (check optocoupler wiring)"));
}

void loop() {
  testStatusLeds();
  testSevenSeg();
  testMagnets();
  testButtons();
  testCoin();
  Serial.println(F("\n=== Self-test cycle complete. Repeats in 5s. Reset the board to stop. ==="));
  delay(5000);
}
