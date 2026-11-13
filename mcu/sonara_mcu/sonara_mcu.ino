// Sonara MCU sketch for the Arduino UNO Q's STM32 (Zephyr core).
// Buttons → Linux side via Bridge.notify("button", name); Linux sets LEDs via "set_leds".
//
// VERIFY ON BOARD: Arduino_RouterBridge API names (Bridge.begin/provide/notify) against the
// UNO Q examples in Arduino App Lab, and pin choices against your wiring.
//
// Wiring (active-low buttons with INPUT_PULLUP):
//   D2 Talk, D3 Confirm, D4 Cancel
//   D5 Listening LED, D6 Pending LED (solid = waiting, blink = NOT reached caregiver), D7 Ack LED
// Distinct patterns, not colour alone: listening = solid, not-displayed = fast blink.

#include <Arduino_RouterBridge.h>

const int BTN_PINS[3] = {2, 3, 4};
const char* BTN_NAMES[3] = {"talk", "confirm", "cancel"};
const int LED_LISTEN = 5, LED_PENDING = 6, LED_ACK = 7;

int pendingMode = 0;            // 0 off, 1 on, 2 blink
bool lastState[3] = {HIGH, HIGH, HIGH};
unsigned long lastChange[3] = {0, 0, 0};

void set_leds(int listening, int pending, int ack) {
  digitalWrite(LED_LISTEN, listening ? HIGH : LOW);
  pendingMode = pending;
  digitalWrite(LED_ACK, ack ? HIGH : LOW);
}

void setup() {
  for (int i = 0; i < 3; i++) pinMode(BTN_PINS[i], INPUT_PULLUP);
  pinMode(LED_LISTEN, OUTPUT); pinMode(LED_PENDING, OUTPUT); pinMode(LED_ACK, OUTPUT);
  Bridge.begin();
  Bridge.provide("set_leds", set_leds);
}

void loop() {
  unsigned long now = millis();
  for (int i = 0; i < 3; i++) {
    bool s = digitalRead(BTN_PINS[i]);
    if (s != lastState[i] && now - lastChange[i] > 40) {   // 40 ms debounce
      lastChange[i] = now;
      lastState[i] = s;
      if (s == LOW) Bridge.notify("button", BTN_NAMES[i]);
    }
  }
  if (pendingMode == 2) digitalWrite(LED_PENDING, (now / 250) % 2);
  else digitalWrite(LED_PENDING, pendingMode == 1);
  delay(5);
}
