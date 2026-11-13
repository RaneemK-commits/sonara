"""Bedside device state machine (deterministic; no agent/LLM).

IDLE ──talk──► LISTENING ──utterance──► PROCESSING
  ▲                                          │ rejected → "didn't understand" → back
  │                                          ▼ accepted
  │                               speak phrase aloud (in-room translation)
  │                                          │ notify-able intent
  │                                          ▼
  └──cancel / NO / timeout──── AWAIT_CONFIRM ──confirm / YES──► create request (QUEUED)

Request status changes (from the server) are spoken back and shown on the room display.
"""
from __future__ import annotations

import queue
import threading
import time
from datetime import datetime, timezone

from .config import Config
from .metrics import METRICS
from .store import RequestStore, TransitionError

IDLE, LISTENING, PROCESSING, AWAIT_CONFIRM = "IDLE", "LISTENING", "PROCESSING", "AWAIT_CONFIRM"

# Modulino Buttons LEDs, each "off" | "on" | "blink" (see docs/DESIGN.md, roles/device/STATUS.md)
CANCEL_LED = {"QUEUED": "on", "DISPLAYED": "on", "NOT_DISPLAYED": "blink"}  # blink = not reached anyone


def led_state(state: str, request_status: str | None) -> tuple[str, str, str]:
    """(talk, confirm, cancel) LEDs for a controller state and the latest request's status."""
    return ("on" if state == LISTENING else "off",
            "blink" if state == AWAIT_CONFIRM else "off",
            CANCEL_LED.get(request_status, "off"))


STATUS_PROMPTS = {"DISPLAYED": "displayed", "NOT_DISPLAYED": "not_displayed",
                  "ACKNOWLEDGED": "acknowledged", "COMPLETED": "completed",
                  "CANCELLED": "cancelled"}


class Controller:
    def __init__(self, cfg: Config, store: RequestStore, hub, speaker, mcu,
                 recognizer=None, capture=None):
        self.cfg, self.store, self.hub, self.speaker, self.mcu = cfg, store, hub, speaker, mcu
        self.recognizer, self.capture = recognizer, capture
        audio = cfg.section("audio")
        self.always_on = audio.get("listen_mode") == "always_on" and capture is not None
        self.ptt_wait = audio.get("push_to_talk_wait_s", 4.0)
        self.confirm_timeout = cfg.section("flow").get("confirm_timeout_s", 15)
        self.state = IDLE
        self.pending = None           # Intent awaiting confirmation
        self.pending_deadline = 0.0
        self.last = {"text": "", "intent": None, "score": None, "understood": None}
        self._event_id = 0
        self._feedback: str | None = None
        self._feedback_until = 0.0
        self._published_display = None
        self.request_id: str | None = self._recover_request_id()  # latest open request (survives reboot)
        self._leds: tuple[str, str, str] | None = None
        self._q: queue.Queue[tuple[str, str | None]] = queue.Queue(maxsize=32)
        self._stop = threading.Event()
        self.audio_lock = threading.RLock()
        self.enrollment_active = False
        self._thread = None

    def _recover_request_id(self) -> str | None:
        mine = [r for r in self.store.active() if r["bed_id"] == self.cfg.bed_id]
        return mine[-1]["request_id"] if mine else None

    # ---- inputs (any thread) ----------------------------------------------------------------
    def submit(self, action: str, arg: str | None = None) -> None:
        if action in ("talk", "select") and self.state in (LISTENING, PROCESSING):
            return  # A repeated press must not start a queued recording after this result.
        if action == "confirm":
            if self.state != AWAIT_CONFIRM or self.pending is None:
                return  # A press before recognition cannot confirm a future request.
            arg = str(self.pending_deadline)
        try:
            self._q.put_nowait((action, arg))
        except queue.Full:
            return

    def start(self) -> None:
        self.mcu.start(lambda name: self.submit(name))
        self._thread = threading.Thread(target=self._run, daemon=True, name="controller")
        self._thread.start()
        self._publish()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=12)

    # ---- room display state -----------------------------------------------------------------
    def _display(self, req: dict | None) -> dict:
        """One authoritative screen projection; browsers do not infer outcomes or timers."""
        phase = {LISTENING: "listening", PROCESSING: "processing"}
        if self.state in phase:
            view = phase[self.state]
        elif self._feedback and time.monotonic() < self._feedback_until:
            view = self._feedback
        elif self.pending:
            view = "confirm"
        elif req:
            status = req["status"]
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(
                req["updated_at"].replace("Z", "+00:00"))).total_seconds()
            view = {"QUEUED": "sending", "NOT_DISPLAYED": "failed"}.get(status)
            if view is None:
                view = ({"DISPLAYED": "notified", "ACKNOWLEDGED": "acked",
                         "CANCELLED": "cancelled"}.get(status, "ready") if age < 60 else "ready")
        else:
            view = "ready"
        intent = self.pending.id if self.pending else self.last.get("intent")
        return {"view": view, "intent": intent, "event_id": self._event_id}

    def _begin_attempt(self) -> None:
        self._event_id += 1
        self._feedback = None
        self.last = {"text": "", "intent": None, "score": None, "understood": None,
                     "event_id": self._event_id}

    def _reject(self, score=None) -> None:
        self._event_id += 1
        self.last = {"text": "", "intent": None, "score": score, "understood": False,
                     "event_id": self._event_id}
        self._feedback, self._feedback_until = "retry", time.monotonic() + 5
        self._set(AWAIT_CONFIRM if self.pending else IDLE)
        self.speaker.say_now("didnt_understand")

    def room_state(self) -> dict:
        req = self.store.get(self.request_id) if self.request_id else None
        return {"type": "room_state", "bed_id": self.cfg.bed_id, "state": self.state,
                "pending": self.pending.label if self.pending else None,
                "last": self.last, "request": req, "has_mic": self.capture is not None and not self.enrollment_active,
                "enrollment_active": self.enrollment_active,
                "display": self._display(req),
                "intents": [{"id": i.id, "label": i.label} for i in self.cfg.request_intents]}

    def _publish(self) -> None:
        snapshot = self.room_state()
        self._published_display = snapshot["display"]
        self.hub.publish(snapshot, role="room")
        req = self.store.get(self.request_id) if self.request_id else None
        leds = led_state(self.state, req["status"] if req else None)
        if leds != self._leds:           # only talk to the MCU when something changed
            self._leds = leds
            self.mcu.set_leds(*leds)

    def _set(self, state: str) -> None:
        self.state = state
        self._publish()

    # ---- main loop --------------------------------------------------------------------------
    def _run(self) -> None:
        while not self._stop.is_set():
            self._check_timeout()  # Deadlines also run when inputs keep arriving.
            try:
                action, arg = self._q.get(timeout=0.05 if self.always_on else 0.25)
            except queue.Empty:
                self._check_timeout()
                if (self.always_on and self.state in (IDLE, AWAIT_CONFIRM)
                        and not (self._feedback and time.monotonic() < self._feedback_until)):
                    if self.audio_lock.acquire(blocking=False):
                        try:
                            if not self.enrollment_active:
                                self.speaker.wait_idle()
                                audio = self.capture.record_utterance(wait_s=0.3)
                                if audio is not None:
                                    self._begin_attempt()
                                    self._handle_audio(audio)
                        except Exception as exc:
                            print(f"[audio] {exc}")
                            self._reject()
                        finally:
                            self.audio_lock.release()
                continue
            try:
                getattr(self, f"_on_{action}")(arg)
            except Exception as e:
                print(f"[controller] {action}: {e!r}")
                if action in ("talk", "select"):
                    self._reject()
                else:
                    self._set(AWAIT_CONFIRM if self.pending else IDLE)

    def _check_timeout(self) -> None:
        if self.pending and time.monotonic() > self.pending_deadline:
            self.pending = None              # never auto-send
            self._feedback, self._feedback_until = "cancelled", time.monotonic() + 5
            self.speaker.say("cancelled")
            self._set(IDLE)
        if self.room_state()["display"] != self._published_display:
            self._publish()  # Publish feedback expiry even with no further user input.

    # ---- actions ----------------------------------------------------------------------------
    def _on_talk(self, _=None) -> None:
        if not self.audio_lock.acquire(blocking=False):
            return
        try:
            if not self.enrollment_active:
                self._record_talk()
        finally:
            self.audio_lock.release()

    def _record_talk(self) -> None:
        if self.capture is None or self.recognizer is None:
            print("[controller] no microphone/recognizer — use the room screen tiles")
            self._reject()
            return
        if self.state in (LISTENING, PROCESSING):
            return
        self.speaker.wait_idle()
        self.capture.flush()
        self._begin_attempt()
        self._set(LISTENING)
        manual = self.cfg.section("audio").get("manual_duration_s", 0)
        audio = (self.capture.record_manual(manual) if manual else
                 self.capture.record_utterance(wait_s=self.ptt_wait))
        if audio is None:
            self._reject()
            return
        self._handle_audio(audio)

    def _handle_audio(self, audio) -> None:
        self._set(PROCESSING)
        t0 = time.perf_counter()
        pred = self.recognizer.recognize(audio, manual=bool(
            self.cfg.section("audio").get("manual_duration_s", 0)))
        METRICS.record("recognize_total", (time.perf_counter() - t0) * 1000)
        if pred is None or not pred.accepted:
            self._reject(pred.score if pred else None)
            return
        print(f"[recognized] {pred.intent} d={pred.distance:.3f} margin={pred.margin:.3f}")
        self._accept(pred.intent, pred.score)

    def _on_select(self, intent_id: str | None) -> None:
        """Manual fallback: patient/caregiver taps a phrase tile on the room display."""
        if self.enrollment_active:
            return
        if intent_id and self.cfg.intent(intent_id):
            self._begin_attempt()
            self._accept(intent_id, None)

    def _accept(self, intent_id: str, score) -> None:
        self._feedback = None
        intent = self.cfg.intent(intent_id)
        if intent is None:
            return
        if intent.control:
            if self.pending:
                return self._on_confirm() if intent.id == "YES" else self._on_cancel()
            self.speaker.say_now(intent.id)       # plain "Yes." / "No." aloud in the room
            self.last = {"text": intent.speak, "intent": intent.id, "score": score, "understood": True}
            return self._set(IDLE)
        self.last = {"text": intent.speak, "intent": intent.id, "score": score, "understood": True}
        self.speaker.say_now(intent.id)           # the translation, spoken aloud immediately
        if intent.notify:
            self.pending = intent
            self.pending_deadline = time.monotonic() + self.confirm_timeout
            self.speaker.say("ask_send")
            self._set(AWAIT_CONFIRM)
        else:
            self._set(IDLE)

    def _on_confirm(self, _=None) -> None:
        if _ is not None and _ != str(self.pending_deadline):
            return  # stale confirmation for a replaced interaction
        if not self.pending:
            return
        if time.monotonic() >= self.pending_deadline:
            self._check_timeout()
            return
        self._feedback = None
        intent, self.pending = self.pending, None
        req = self.store.create(self.cfg.bed_id, intent.id, intent.label)
        self.request_id = req["request_id"]
        METRICS.incr("requests_sent")
        self.hub.publish({"type": "request", "request": req})
        self.speaker.say("sending")
        self._set(IDLE)

    def _on_cancel(self, _=None) -> None:
        if self.pending:
            self.pending = None
            self._feedback, self._feedback_until = "cancelled", time.monotonic() + 5
            self.speaker.say_now("cancelled")
            return self._set(IDLE)
        # no pending phrase: cancel the latest still-open request instead
        req = self.store.get(self.request_id) if self.request_id else None
        if req and req["status"] in ("QUEUED", "DISPLAYED", "NOT_DISPLAYED"):
            try:
                req, _ = self.store.transition(req["request_id"], "CANCELLED", "patient")
            except TransitionError:
                return
            self.hub.publish({"type": "request", "request": req})
            self.speaker.say("cancelled")
            self._publish()

    # ---- status feedback from the caregiver side (server thread) ----------------------------
    def on_request_status(self, req: dict) -> None:
        if req["bed_id"] != self.cfg.bed_id:
            return
        if req["request_id"] == self.request_id and req["status"] in STATUS_PROMPTS:
            if req["status"] != "CANCELLED":       # cancellation already spoken locally
                self.speaker.say(STATUS_PROMPTS[req["status"]])
        self._publish()
