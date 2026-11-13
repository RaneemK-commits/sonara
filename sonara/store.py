"""Durable request store (SQLite) with an explicit, honest status machine.

QUEUED        saved on the device; caregiver screen has NOT confirmed receipt
DISPLAYED     caregiver browser sent an explicit receipt for this request id
NOT_DISPLAYED no receipt within the timeout (still retried when a caregiver screen connects)
ACKNOWLEDGED  a caregiver clicked Acknowledge   (only ever set by a caregiver action)
COMPLETED     a caregiver clicked Complete
CANCELLED     patient cancelled after sending
"""
from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

ACTIVE = ("QUEUED", "DISPLAYED", "NOT_DISPLAYED", "ACKNOWLEDGED")

TRANSITIONS: dict[str, set[str]] = {
    "QUEUED": {"DISPLAYED", "NOT_DISPLAYED", "ACKNOWLEDGED", "CANCELLED"},
    "NOT_DISPLAYED": {"DISPLAYED", "ACKNOWLEDGED", "CANCELLED"},
    "DISPLAYED": {"ACKNOWLEDGED", "CANCELLED"},
    "ACKNOWLEDGED": {"COMPLETED", "CANCELLED"},
    "COMPLETED": set(),
    "CANCELLED": set(),
}


class TransitionError(ValueError):
    pass


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class RequestStore:
    def __init__(self, db_path: str | Path):
        if str(db_path) != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(db_path), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        with self._lock, self._db:
            self._db.executescript("""
                CREATE TABLE IF NOT EXISTS requests (
                    request_id TEXT PRIMARY KEY, bed_id TEXT NOT NULL, intent TEXT NOT NULL,
                    label TEXT NOT NULL, status TEXT NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, request_id TEXT NOT NULL,
                    status TEXT NOT NULL, actor TEXT NOT NULL, at TEXT NOT NULL);
            """)

    def _next_id(self) -> str:
        n = self._db.execute("SELECT COUNT(*) FROM requests").fetchone()[0] + 1
        return f"req-{n:04d}"

    def create(self, bed_id: str, intent: str, label: str) -> dict:
        with self._lock, self._db:
            rid, ts = self._next_id(), now_iso()
            self._db.execute("INSERT INTO requests VALUES (?,?,?,?,?,?,?)",
                             (rid, bed_id, intent, label, "QUEUED", ts, ts))
            self._db.execute("INSERT INTO events (request_id,status,actor,at) VALUES (?,?,?,?)",
                             (rid, "QUEUED", "patient", ts))
        return self.get(rid)

    def _q(self, sql: str, args=()) -> list[dict]:
        with self._lock:
            return [dict(r) for r in self._db.execute(sql, args).fetchall()]

    def get(self, rid: str) -> dict | None:
        rows = self._q("SELECT * FROM requests WHERE request_id=?", (rid,))
        return rows[0] if rows else None

    def transition(self, rid: str, new: str, actor: str) -> tuple[dict, bool]:
        """Apply a transition. Returns (request, changed). Idempotent for repeated same status."""
        with self._lock, self._db:
            row = self._db.execute("SELECT status FROM requests WHERE request_id=?", (rid,)).fetchone()
            if row is None:
                raise KeyError(rid)
            cur = row["status"]
            if cur == new:
                return self.get(rid), False
            if new not in TRANSITIONS[cur]:
                raise TransitionError(f"{rid}: {cur} → {new} not allowed")
            ts = now_iso()
            self._db.execute("UPDATE requests SET status=?, updated_at=? WHERE request_id=?",
                             (new, ts, rid))
            self._db.execute("INSERT INTO events (request_id,status,actor,at) VALUES (?,?,?,?)",
                             (rid, new, actor, ts))
        return self.get(rid), True

    def active(self) -> list[dict]:
        q = f"SELECT * FROM requests WHERE status IN ({','.join('?' * len(ACTIVE))}) ORDER BY created_at, request_id"
        return self._q(q, ACTIVE)

    def history(self, limit: int = 50) -> list[dict]:
        return self._q("SELECT * FROM requests ORDER BY created_at DESC, request_id DESC LIMIT ?",
                       (limit,))

    def events(self, rid: str) -> list[dict]:
        return self._q("SELECT status, actor, at FROM events WHERE request_id=? ORDER BY id", (rid,))

    def reset(self) -> None:
        """Delete all request metadata (demo reset / data deletion)."""
        with self._lock, self._db:
            self._db.execute("DELETE FROM events")
            self._db.execute("DELETE FROM requests")
