"""Device role: request store + end-to-end flow through server and controller, no audio hardware."""
import time

from fastapi.testclient import TestClient

from sonara.config import load_config
from sonara.controller import Controller
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


def make():
    cfg = load_config()
    cfg.raw["server"]["caregiver_token"] = "t"
    store, hub, spk = RequestStore(":memory:"), Hub(), SilentSpeaker()
    ctl = Controller(cfg, store, hub, spk, NullMCU())
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
