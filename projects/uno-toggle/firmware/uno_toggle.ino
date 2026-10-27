/*
  Uno Toggle - two buttons, two LEDs.

  Press BTN1 -> LED1 toggles on/off.  Press BTN2 -> LED2 toggles on/off.

  Pin map MUST match gen/netlist.py (test/pinmap.py checks this automatically):
    BTN1 = D2   BTN2 = D3      buttons to GND, internal pull-ups => pressed reads LOW
    LED1 = D8   LED2 = D9      each via 330R to the LED anode, cathode to GND

  Debounce: the board has a 100nF across each switch, and this sketch additionally ignores any edge
  within DEBOUNCE_MS of the last accepted one. Belt and braces - mechanical switches are noisy.
*/

const uint8_t BTN1 = 2;
const uint8_t BTN2 = 3;
const uint8_t LED1 = 8;
const uint8_t LED2 = 9;

const unsigned long DEBOUNCE_MS = 25;

struct Toggle {
  uint8_t buttonPin;
  uint8_t ledPin;
  bool ledOn;
  int lastReading;
  unsigned long lastChangeMs;
};

Toggle toggles[2] = {
  { BTN1, LED1, false, HIGH, 0 },
  { BTN2, LED2, false, HIGH, 0 },
};

void setup() {
  Serial.begin(115200);
  for (Toggle &t : toggles) {
    pinMode(t.buttonPin, INPUT_PULLUP);
    pinMode(t.ledPin, OUTPUT);
    digitalWrite(t.ledPin, LOW);
    t.lastReading = digitalRead(t.buttonPin);
  }
  Serial.println(F("uno-toggle ready: press a button to toggle its LED"));
}

void loop() {
  unsigned long now = millis();

  for (Toggle &t : toggles) {
    int reading = digitalRead(t.buttonPin);

    // Falling edge = press (pull-up means idle is HIGH), and only if we've settled since the last one.
    if (reading != t.lastReading) {
      if (reading == LOW && (now - t.lastChangeMs) >= DEBOUNCE_MS) {
        t.ledOn = !t.ledOn;
        digitalWrite(t.ledPin, t.ledOn ? HIGH : LOW);
        Serial.print(F("BTN on D"));
        Serial.print(t.buttonPin);
        Serial.print(F(" -> LED on D"));
        Serial.print(t.ledPin);
        Serial.println(t.ledOn ? F(" ON") : F(" OFF"));
      }
      t.lastChangeMs = now;
      t.lastReading = reading;
    }
  }
}
