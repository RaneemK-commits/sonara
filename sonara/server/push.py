"""Optional generic Web Push. Delivery never changes a caregiver request's status."""
from __future__ import annotations

import base64
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit


def validate_subscription(value: dict) -> dict:
    endpoint = value.get("endpoint", "")
    if not isinstance(endpoint, str) or len(endpoint) > 2048:
        raise ValueError("invalid push endpoint")
    url = urlsplit(endpoint)
    host = url.hostname or ""
    allowed = (host == "web.push.apple.com" or host.endswith(".push.apple.com")
               or host == "fcm.googleapis.com"
               or host == "updates.push.services.mozilla.com")
    if (url.scheme != "https" or not allowed or url.port not in (None, 443)
            or url.username or url.password or url.fragment):
        raise ValueError("unsupported push provider; use Apple, Chrome or Firefox Web Push")
    keys = value.get("keys", {})
    if not isinstance(keys, dict):
        raise ValueError("invalid subscription keys")
    for name, size in (("auth", 16), ("p256dh", 65)):
        key = keys.get(name, "")
        if not isinstance(key, str) or len(key) > 128:
            raise ValueError("invalid subscription keys")
        try:
            raw = base64.b64decode(key + "=" * (-len(key) % 4), altchars=b"-_", validate=True)
        except ValueError as exc:
            raise ValueError("invalid subscription keys") from exc
        if len(raw) != size or (name == "p256dh" and raw[0] != 4):
            raise ValueError("invalid subscription keys")
    return {"endpoint": endpoint, "keys": {k: keys[k] for k in ("auth", "p256dh")}}


def key_public(path: Path) -> str:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    key = serialization.load_pem_private_key(path.read_bytes(), password=None)
    if not isinstance(key, ec.EllipticCurvePrivateKey) or not isinstance(key.curve, ec.SECP256R1):
        raise ValueError("VAPID key must use P-256")
    raw = key.public_key().public_bytes(serialization.Encoding.X962,
                                        serialization.PublicFormat.UncompressedPoint)
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def generate_key(path: Path) -> None:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    key = ec.generate_private_key(ec.SECP256R1())
    data = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                             serialization.NoEncryption())
    path.parent.mkdir(parents=True, exist_ok=True)
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as out:
        out.write(data)  # Never replace a key: existing phone subscriptions depend on it.


class PushService:
    def __init__(self, cfg, store):
        self.store = store
        options = cfg.section("push")
        self.enabled = bool(options.get("enabled", False))
        self.public_key = ""
        self.key_path = cfg.path(options.get("private_key", "data/webpush-private.pem"))
        self.subject = options.get("subject", "")
        self._stop = threading.Event()
        self._thread = None
        self.error = None
        if self.enabled:
            try:
                from pywebpush import webpush
                if not cfg.section("server").get("caregiver_token"):
                    raise ValueError("push requires a caregiver token")
                if not self.subject.startswith(("mailto:", "https://")):
                    raise ValueError("configure a VAPID contact subject")
                self.public_key = key_public(self.key_path)
                self._send = webpush
            except (ImportError, OSError, ValueError):
                self.enabled = False
                self.error = "push_not_configured"
                print("[push] disabled: check optional dependency, key, token and contact subject")

    def start(self):
        if self.enabled:
            self._thread = threading.Thread(target=self._run, daemon=True, name="webpush")
            self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=12)

    def _run(self):
        while not self._stop.wait(1):
            try:
                self.deliver_pending()
            except Exception:
                # Subscription endpoints and exceptions may contain credentials: never log them.
                print("[push] delivery scan failed; local request flow continues")

    def deliver_pending(self):
        if not self.enabled:
            return
        for request in self.store.active():
            for subscription in self.store.push_subscriptions():
                if self._stop.is_set():
                    return
                current = self.store.get(request["request_id"])
                if (not current or current["created_at"] != request["created_at"]
                        or current["status"] not in ("QUEUED", "NOT_DISPLAYED", "DISPLAYED")):
                    break
                age = (datetime.now(timezone.utc) - datetime.fromisoformat(
                    current["created_at"].replace("Z", "+00:00"))).total_seconds()
                if not 0 <= age < 120:
                    break
                endpoint = subscription["endpoint"]
                if not self.store.claim_push(current["request_id"], endpoint):
                    continue
                try:
                    self._send(subscription_info=validate_subscription(subscription),
                               data=json.dumps({"title": "Sonara", "body": "New Sonara request",
                                                "url": "/caregiver"}),
                               vapid_private_key=str(self.key_path),
                               vapid_claims={"sub": self.subject}, ttl=max(1, int(120 - age)),
                               timeout=8, headers={"Urgency": "normal"})
                except Exception as exc:
                    status = getattr(getattr(exc, "response", None), "status_code", None)
                    if status in (404, 410):
                        self.store.unsubscribe_push(endpoint)
                    print(f"[push] delivery failed (HTTP {status or 'unavailable'}); request status unchanged")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Generate a board-local VAPID key once")
    parser.add_argument("--init-key", type=Path, required=True)
    args = parser.parse_args()
    generate_key(args.init_key)
    print("Created private VAPID key; never commit it. Configure push in data/local.toml.")
