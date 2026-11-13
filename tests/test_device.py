"""Device role: request store + end-to-end flow through server and controller, no audio hardware."""
import time

from fastapi.testclient import TestClient

from sonara.config import load_config
from sonara.controller import Controller, led_state
from sonara.hw.mcu import NullMCU
from sonara.server.app import create_app
from sonara.server.hub import Hub
import pytest

from sonara.store import RequestStore, TransitionError


class SilentSpeaker:
    def __init__(self):
        self.said = []

    def say(self, k):
        self.said.append(k)

    say_now = say

    def wait_idle(self, timeout=0):
        pass


def wait_for(pred, timeout=3.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if pred():
            return True
        time.sleep(0.02)
    return False


class RecordingMCU(NullMCU):
    def __init__(self):
        self.leds = []

    def set_leds(self, talk, confirm, cancel):
        self.leds.append((talk, confirm, cancel))


def make(store=None, mcu=None):
    cfg = load_config()
    cfg.raw["server"]["caregiver_token"] = "t"
    store, hub, spk = store or RequestStore(":memory:"), Hub(), SilentSpeaker()
    ctl = Controller(cfg, store, hub, spk, mcu or NullMCU())
    return cfg, store, spk, ctl, create_app(cfg, store, hub, ctl)


def test_select_confirm_ack_complete():
    cfg, store, spk, ctl, app = make()
    with TestClient(app) as c:
        with c.websocket_connect("/ws?role=caregiver&token=t") as cg:
            assert cg.receive_json()["type"] == "snapshot"
            c.post("/api/room/input", json={"action": "select", "intent": "WATER"})
            assert wait_for(lambda: ctl.state == "AWAIT_CONFIRM")
            assert spk.said[:2] == ["WATER", "ask_send"]      # spoken aloud before any sending
            assert store.active() == []                        # nothing sent before confirm
            c.post("/api/room/input", json={"action": "confirm"})
            msg = cg.receive_json()
            assert msg["type"] == "request" and msg["request"]["status"] == "QUEUED"
            rid = msg["request"]["request_id"]
            cg.send_json({"type": "receipt", "request_id": rid})
            assert wait_for(lambda: store.get(rid)["status"] == "DISPLAYED")
        assert c.post(f"/api/requests/{rid}/acknowledge").status_code == 401
        h = {"X-Sonara-Token": "t"}
        assert c.post(f"/api/requests/{rid}/acknowledge", headers=h).json()["status"] == "ACKNOWLEDGED"
        assert c.post(f"/api/requests/{rid}/complete", headers=h).json()["status"] == "COMPLETED"
        assert {"displayed", "acknowledged", "completed"} <= set(spk.said)


def test_cancel_sends_nothing():
    cfg, store, spk, ctl, app = make()
    with TestClient(app) as c:
        c.post("/api/room/input", json={"action": "select", "intent": "PAIN"})
        assert wait_for(lambda: ctl.state == "AWAIT_CONFIRM")
        c.post("/api/room/input", json={"action": "cancel"})
        assert wait_for(lambda: ctl.state == "IDLE")
        c.post("/api/room/input", json={"action": "confirm"})  # stale confirm must do nothing
        time.sleep(0.3)
        assert store.history() == []


def test_no_receipt_becomes_not_displayed():
    cfg, store, spk, ctl, app = make()
    cfg.raw["server"]["display_timeout_s"] = 0
    app = create_app(cfg, store, ctl.hub, ctl)
    with TestClient(app) as c:
        c.post("/api/room/input", json={"action": "select", "intent": "HELP"})
        assert wait_for(lambda: ctl.state == "AWAIT_CONFIRM")
        c.post("/api/room/input", json={"action": "confirm"})
        assert wait_for(lambda: store.history() and store.history()[0]["status"] == "NOT_DISPLAYED", 4)
        assert "not_displayed" in spk.said


def test_store_honest_transitions():
    s = RequestStore(":memory:")
    r = s.create("BED-01", "WATER", "Water")
    assert r["status"] == "QUEUED"
    with pytest.raises(TransitionError):
        s.transition(r["request_id"], "COMPLETED", "caregiver")  # must be acknowledged first
    s.transition(r["request_id"], "NOT_DISPLAYED", "system")
    s.transition(r["request_id"], "DISPLAYED", "caregiver_screen")
    _, changed = s.transition(r["request_id"], "DISPLAYED", "caregiver_screen")
    assert not changed  # idempotent receipts
    s.transition(r["request_id"], "ACKNOWLEDGED", "caregiver")
    s.transition(r["request_id"], "COMPLETED", "caregiver")
    assert [e["status"] for e in s.events(r["request_id"])] == [
        "QUEUED", "NOT_DISPLAYED", "DISPLAYED", "ACKNOWLEDGED", "COMPLETED"]
    assert s.active() == []


def test_led_state():
    assert led_state("LISTENING", None) == ("on", "off", "off")
    assert led_state("AWAIT_CONFIRM", None) == ("off", "blink", "off")
    assert led_state("IDLE", "QUEUED") == ("off", "off", "on")
    assert led_state("IDLE", "NOT_DISPLAYED") == ("off", "off", "blink")   # honest: not reached anyone
    assert led_state("IDLE", "ACKNOWLEDGED") == ("off", "off", "off")


def test_leds_follow_flow_and_cancel_open_request():
    mcu = RecordingMCU()
    cfg, store, spk, ctl, app = make(mcu=mcu)
    with TestClient(app) as c:
        c.post("/api/room/input", json={"action": "select", "intent": "WATER"})
        assert wait_for(lambda: mcu.leds and mcu.leds[-1] == ("off", "blink", "off"))
        c.post("/api/room/input", json={"action": "confirm"})
        assert wait_for(lambda: mcu.leds[-1] == ("off", "off", "on"))
        c.post("/api/room/input", json={"action": "cancel"})   # no pending phrase → cancels the request
        assert wait_for(lambda: store.history()[0]["status"] == "CANCELLED")
        assert wait_for(lambda: mcu.leds[-1] == ("off", "off", "off"))
    assert all(a != b for a, b in zip(mcu.leds, mcu.leds[1:]))  # MCU only told on change


def test_reboot_recovers_open_request(tmp_path):
    db_path = tmp_path / "requests.db"
    store = RequestStore(db_path)
    store.create("BED-99", "FOOD", "Food")                     # another bed: not ours
    mine = store.create("BED-01", "WATER", "Water")
    store.transition(mine["request_id"], "NOT_DISPLAYED", "system")
    store._db.close()
    store = RequestStore(db_path)  # Reopen durable state, not the original in-memory store.
    mcu = RecordingMCU()
    cfg, store, spk, ctl, app = make(store, mcu)               # fresh controller = after reboot
    assert ctl.request_id == mine["request_id"]
    assert ctl.room_state()["request"]["status"] == "NOT_DISPLAYED"
    with TestClient(app) as c:
        assert wait_for(lambda: mcu.leds and mcu.leds[-1] == ("off", "off", "blink"))
        c.post("/api/room/input", json={"action": "cancel"})
        assert wait_for(lambda: store.get(mine["request_id"])["status"] == "CANCELLED")


def test_receipt_after_not_displayed_reconnect():
    cfg, store, spk, ctl, app = make()
    cfg.raw["server"]["display_timeout_s"] = 0
    app = create_app(cfg, store, ctl.hub, ctl)
    with TestClient(app) as c:
        c.post("/api/room/input", json={"action": "select", "intent": "HELP"})
        assert wait_for(lambda: ctl.state == "AWAIT_CONFIRM")
        c.post("/api/room/input", json={"action": "confirm"})
        assert wait_for(lambda: store.history() and store.history()[0]["status"] == "NOT_DISPLAYED", 4)
        with c.websocket_connect("/ws?role=caregiver&token=t") as cg:   # caregiver screen comes back
            snap = cg.receive_json()
            rid = snap["active"][0]["request_id"]
            cg.send_json({"type": "receipt", "request_id": rid})
            assert wait_for(lambda: store.get(rid)["status"] == "DISPLAYED")
        assert "displayed" in spk.said


def test_repeated_rejection_is_explicit_and_survives_snapshot():
    cfg, store, spk, ctl, app = make()
    published = []
    ctl.hub.publish = lambda event, role=None: published.append(event)
    ctl._reject(0.2)
    first = ctl.room_state()
    ctl._feedback_until = time.monotonic() - 1
    ctl._check_timeout()
    assert ctl.room_state()["display"]["view"] == "ready"
    assert published[-1]["display"]["view"] == "ready"
    ctl._reject(0.2)
    second = ctl.room_state()
    assert second["display"]["view"] == "retry"
    assert second["display"]["event_id"] > first["display"]["event_id"]
    assert second["last"] != first["last"]  # Legacy clients also see a fresh result.
    assert published[-1]["display"] == second["display"]
    assert ctl.room_state()["display"] == second["display"]  # Reconnect snapshot.
    assert store.history() == []


def test_rejection_during_confirmation_restores_correct_phrase():
    cfg, store, spk, ctl, app = make()
    ctl._on_select("WATER")
    ctl._reject()
    assert ctl.room_state()["display"]["view"] == "retry"
    assert ctl.room_state()["display"]["intent"] == "WATER"
    ctl._feedback_until = time.monotonic() - 1
    ctl._check_timeout()
    assert ctl.room_state()["display"]["view"] == "confirm"
    assert ctl.room_state()["display"]["intent"] == "WATER"
    ctl.pending_deadline = time.monotonic() - 1
    ctl._on_confirm()  # Expired confirmation cannot race the queue timeout.
    assert store.history() == []
    assert ctl.room_state()["display"]["view"] == "cancelled"


def test_new_attempt_clears_retry_and_request_states_remain_honest():
    cfg, store, spk, ctl, app = make()
    ctl._reject()
    ctl._on_select("HELP")
    assert ctl.room_state()["display"]["view"] == "confirm"
    ctl._on_confirm()
    assert ctl.room_state()["display"]["view"] == "sending"
    for status, view in [("NOT_DISPLAYED", "failed"), ("DISPLAYED", "notified"),
                         ("ACKNOWLEDGED", "acked"), ("COMPLETED", "ready")]:
        req, _ = store.transition(ctl.request_id, status, "test")
        ctl.on_request_status(req)
        assert ctl.room_state()["display"]["view"] == view


def test_busy_input_cannot_queue_another_recording_or_confirm():
    cfg, store, spk, ctl, app = make()
    ctl._on_select("WATER")
    ctl._set("PROCESSING")
    ctl.submit("talk")
    ctl.submit("select", "HELP")
    ctl.submit("confirm")
    assert ctl._q.empty()
    ctl.submit("cancel")
    assert ctl._q.get_nowait()[0] == "cancel"
