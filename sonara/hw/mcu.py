"""Bridge to the UNO Q's STM32 MCU (buttons + LEDs), with laptop stand-ins.

Button events call `on_button(name)` with name in {"talk", "confirm", "cancel"}.
LED state: listening (bool), pending ("off" | "on" | "blink"), acknowledged (bool).
"""
from __future__ import annotations

import sys
import threading
from typing import Callable

ButtonCb = Callable[[str], None]


class NullMCU:
    def start(self, on_button: ButtonCb) -> None:
        self.on_button = on_button

    def set_leds(self, listening: bool, pending: str, acknowledged: bool) -> None:
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

    def set_leds(self, listening: bool, pending: str, acknowledged: bool) -> None:
        print(f"[leds] listen={'●' if listening else '○'} pending={pending} "
              f"ack={'●' if acknowledged else '○'}")


class UnoQBridgeMCU(NullMCU):
    """Arduino UNO Q: talks to mcu/sonara_mcu sketch over the Arduino Router Bridge (RPC).

    VERIFY ON BOARD: the Python Bridge module ships with Arduino App Lab (`arduino.app_utils`).
    The sketch calls Bridge.notify("button", "<name>") and provides "set_leds".
    """

    def start(self, on_button: ButtonCb) -> None:
        from arduino.app_utils import Bridge  # type: ignore  # available on the UNO Q

        self.Bridge = Bridge
        self.on_button = on_button
        Bridge.provide("button", lambda name: on_button(str(name)))

    def set_leds(self, listening: bool, pending: str, acknowledged: bool) -> None:
        code = {"off": 0, "on": 1, "blink": 2}[pending]
        try:
            self.Bridge.call("set_leds", int(listening), code, int(acknowledged))
        except Exception as e:
            print(f"[mcu] set_leds failed: {e}")


def make_mcu(kind: str):
    return {"keyboard": KeyboardMCU, "unoq": UnoQBridgeMCU, "none": NullMCU}[kind]()
