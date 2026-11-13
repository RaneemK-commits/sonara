// Sonara MCU sketch for the Arduino UNO Q's STM32 (Zephyr core), with a Modulino Buttons on Qwiic.
// Button presses → Linux via Bridge.notify("button", name).
// Linux sets the three button LEDs via Bridge "set_leds(talk, confirm, cancel)", codes 0 off, 1 on, 2 blink
// (same codes as LED_CODE in sonara/hw/mcu.py).
//
//   Button A = Talk     LED on while listening
//   Button B = Confirm  LED blinks while a phrase waits for confirmation
//   Button C = Cancel   LED on while a sent request can be cancelled; fast blink = NOT reached a caregiver
// Patterns differ (solid vs blink), so the meaning never depends on colour alone.
//
// VERIFY ON BOARD:
//  - Arduino_RouterBridge API names (Bridge.begin/provide/notify) against the UNO Q examples in App Lab.
//  - Arduino_Modulino API (Modulino.begin, ModulinoButtons.update/isPressed/setLeds) and whether the
//    UNO Q's Qwiic connector is on Wire or Wire1 (then Modulino.begin(Wire1)).
//  - Whether the MCU or Linux side owns the Qwiic bus at all (roles/device/BRINGUP.md §5).

#include <Arduino_RouterBridge.h>
#include <Modulino.h>

ModulinoButtons buttons;

const char* BTN_NAMES[3] = {"talk", "confirm", "cancel"};
int ledMode[3] = {0, 0, 0};          // 0 off, 1 on, 2 blink
bool wasPressed[3] = {false, false, false};
bool shown[3] = {false, false, false};  // LED levels last written to the Modulino

void set_leds(int talk, int confirm, int cancel) {
  ledMode[0] = talk;
  ledMode[1] = confirm;
  ledMode[2] = cancel;
}

bool ledOn(int mode, unsigned long now, unsigned long half_period_ms) {
  if (mode == 2) return (now / half_period_ms) % 2;
  return mode == 1;
}

void setup() {
  Modulino.begin();
  buttons.begin();
  Bridge.begin();
  Bridge.provide("set_leds", set_leds);
}

void loop() {
  unsigned long now = millis();
  if (buttons.update()) {                       // true when any button state changed
    for (int i = 0; i < 3; i++) {
      bool p = buttons.isPressed(i);
      if (p && !wasPressed[i]) Bridge.notify("button", BTN_NAMES[i]);   // press edge only; holds ignored
      wasPressed[i] = p;
    }
  }
  // confirm blinks slowly (waiting for you), cancel blinks fast (not reached anyone)
  bool a = ledOn(ledMode[0], now, 250), b = ledOn(ledMode[1], now, 400), c = ledOn(ledMode[2], now, 150);
  if (a != shown[0] || b != shown[1] || c != shown[2]) {   // only write to I2C on change
    buttons.setLeds(a, b, c);
    shown[0] = a; shown[1] = b; shown[2] = c;
  }
  delay(10);
}
