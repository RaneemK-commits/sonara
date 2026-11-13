import base64
import json
from types import SimpleNamespace

import pytest

from sonara.config import load_config
from sonara.store import RequestStore
from sonara.server.push import PushService, generate_key, validate_subscription


def subscription(endpoint="https://web.push.apple.com/test-subscription"):
    # Structurally valid fixture; no network operation uses these fake keys.
    encode = lambda raw: base64.urlsafe_b64encode(raw).rstrip(b"=").decode()
    return {"endpoint": endpoint, "keys": {"auth": encode(b"a" * 16),
            "p256dh": encode(b"\x04" + b"b" * 64)}}


def service(tmp_path, monkeypatch):
    pywebpush = pytest.importorskip("pywebpush")
    cfg = load_config()
    cfg.root = tmp_path
    cfg.raw["push"] = {"enabled": True, "subject": "mailto:test@example.org"}
    generate_key(tmp_path / "data/webpush-private.pem")
    sent = []
    monkeypatch.setattr(pywebpush, "webpush", lambda **kwargs: sent.append(kwargs))
    store = RequestStore(tmp_path / "requests.db")
    push = PushService(cfg, store)
    assert push.enabled and len(push.public_key) == 87
    return store, push, sent


@pytest.mark.parametrize("endpoint", ["http://web.push.apple.com/x", "https://127.0.0.1/x",
    "https://web.push.apple.com.evil.test/x", "https://web.push.apple.com:8000/x",
    "https://user@web.push.apple.com/x", "https://web.push.apple.com/x#fragment"])
def test_push_rejects_untrusted_endpoints(endpoint):
    with pytest.raises(ValueError):
        validate_subscription(subscription(endpoint))


def test_push_generic_once_and_no_status_transition(tmp_path, monkeypatch):
    store, push, sent = service(tmp_path, monkeypatch)
    store.subscribe_push(subscription())
    req = store.create("PRIVATE-BED", "PAIN", "Private phrase")
    push.deliver_pending()
    push.deliver_pending()
    assert len(sent) == 1
    assert json.loads(sent[0]["data"]) == {"title": "Sonara", "body": "New Sonara request", "url": "/caregiver"}
    assert sent[0]["timeout"] == 8 and 0 < sent[0]["ttl"] <= 120
    assert store.get(req["request_id"])["status"] == "QUEUED"
    assert len(store.events(req["request_id"])) == 1
    push.store = RequestStore(tmp_path / "requests.db")
    push.deliver_pending()  # Restart does not redeliver the same request/phone pair.
    assert len(sent) == 1


def test_push_ignores_expired_and_acknowledged_requests(tmp_path, monkeypatch):
    store, push, sent = service(tmp_path, monkeypatch)
    store.subscribe_push(subscription())
    old = store.create("BED", "WATER", "Water")
    with store._db:
        store._db.execute("UPDATE requests SET created_at='2000-01-01T00:00:00Z' WHERE request_id=?", (old["request_id"],))
    ack = store.create("BED", "HELP", "Help")
    store.transition(ack["request_id"], "ACKNOWLEDGED", "caregiver")
    push.deliver_pending()
    assert sent == []


def test_push_revoked_subscription_removed_without_changing_request(tmp_path, monkeypatch):
    store, push, sent = service(tmp_path, monkeypatch)
    store.subscribe_push(subscription())
    req = store.create("BED", "WATER", "Water")
    class Gone(Exception):
        response = SimpleNamespace(status_code=410)
    def fail(**kwargs):
        raise Gone()
    push._send = fail
    push.deliver_pending()
    assert store.push_subscriptions() == []
    assert store.get(req["request_id"])["status"] == "QUEUED"


def test_push_defaults_off_and_key_not_replaced(tmp_path):
    cfg = load_config()
    cfg.raw["push"] = {"enabled": False}
    store = RequestStore(":memory:")
    push = PushService(cfg, store)
    assert not push.enabled
    push.deliver_pending()
    pytest.importorskip("cryptography")
    path = tmp_path / "key.pem"
    generate_key(path)
    original = path.read_bytes()
    with pytest.raises(FileExistsError):
        generate_key(path)
    assert path.read_bytes() == original


def test_push_api_requires_auth_and_reports_disabled():
    from fastapi.testclient import TestClient
    from test_device import make
    cfg, store, spk, ctl, app = make()
    with TestClient(app) as client:
        assert client.get("/api/push/config").status_code == 401
        assert client.post("/api/push/subscriptions", json=subscription()).status_code == 401
        h = {"X-Sonara-Token": "t"}
        assert client.get("/api/push/config", headers=h).json()["enabled"] is False
        assert client.post("/api/push/subscriptions", headers=h, json=subscription()).status_code == 503
        assert client.delete("/api/push/subscriptions", headers=h).status_code == 422
        assert client.request("DELETE", "/api/push/subscriptions", headers=h,
                              json={"endpoint": subscription()["endpoint"]}).json() == {"ok": True}
