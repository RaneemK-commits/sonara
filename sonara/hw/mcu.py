"""Bridge to the UNO Q's STM32 MCU (buttons + LEDs), with laptop stand-ins.

Button events call `on_button(name)` with name in {"talk", "confirm", "cancel"}.
LEDs (one per Modulino button), each "off" | "on" | "blink":
  talk    on while listening
  confirm blinks while a phrase waits for confirmation
  cancel  on while a sent request can still be cancelled, blinks while it is NOT_DISPLAYED
"""
from __future__ import annotations

import sys
import threading
from typing import Callable

ButtonCb = Callable[[str], None]
LED_CODE = {"off": 0, "on": 1, "blink": 2}   # same codes as mcu/sonara_mcu/sonara_mcu.ino


class NullMCU:
    def start(self, on_button: ButtonCb) -> None:
        self.on_button = on_button

    def set_leds(self, talk: str, confirm: str, cancel: str) -> None:
        pass


class KeyboardMCU(NullMCU):
    """Laptop dev: type t / c / x + Enter in the terminal for Talk / Confirm / Cancel."""

    KEYS = {"t": "talk", "c": "confirm", "x": "cancel"}

    def start(self, on_button: ButtonCb) -> None:
        self.on_button = on_button
        if not sys.stdin or not sys.stdin.isatty():
            return
        print("[mcu] keyboard buttons: t=Talk  c=Confirm  x=Cancel (then Enter)")
        threading.Thread(target=self._loop, daemon=True, name="kbd").start()

    def _loop(self) -> None:
        for line in sys.stdin:
            name = self.KEYS.get(line.strip().lower())
            if name:
                self.on_button(name)

    def set_leds(self, talk: str, confirm: str, cancel: str) -> None:
        print(f"[leds] talk={talk} confirm={confirm} cancel={cancel}")


class UnoQBridgeMCU(NullMCU):
    """Arduino UNO Q: talks to mcu/sonara_mcu over the Arduino Router (msgpack-RPC on a unix socket).

    Uses the standalone `arduino-router-bridge` package (`pip install arduino-router-bridge`, import
    `arduino.router_bridge`), so Sonara runs as a normal service and needs no App Lab container.
    Needs read/write on /var/run/arduino-router.sock: `sudo usermod -aG arduino-router $USER`, re-login.
    Seen on the board: the sketch's Bridge.notify("button", name) reaches a provided Python handler
    (checked inside an App Lab container with arduino.app_utils). Handlers must not call the Bridge
    themselves (nested calls raise); the controller only queues the event, so that holds here.
    VERIFY: this plain-venv path once the socket group is set.
    """

    def start(self, on_button: ButtonCb) -> None:
        from arduino.router_bridge import Bridge  # type: ignore

        self.on_button = on_button
        self.bridge = Bridge()
        self.bridge.provide("button", lambda name: on_button(str(name)))
        if not self.bridge.connect(timeout=10):
            print("[mcu] Bridge not connected yet; it keeps retrying in the background")

    def set_leds(self, talk: str, confirm: str, cancel: str) -> None:
        try:
            self.bridge.notify("set_leds", LED_CODE[talk], LED_CODE[confirm], LED_CODE[cancel])
        except Exception as e:
            print(f"[mcu] set_leds failed: {e}")


def make_mcu(kind: str):
    return {"keyboard": KeyboardMCU, "unoq": UnoQBridgeMCU, "none": NullMCU}[kind]()
