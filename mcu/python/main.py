"""Deliberately empty: this App Lab app only exists to keep mcu/sketch running.

Sonara (`python -m sonara --mcu unoq`, outside App Lab) provides the "button" route and sends
"set_leds". Providing "button" here too would conflict with it, so this file must not.
"""
from arduino.app_utils import App

App.run()
