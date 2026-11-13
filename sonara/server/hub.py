"""WebSocket fan-out. `publish()` is thread-safe so the audio/controller thread can use it."""
from __future__ import annotations

import asyncio
import json

from fastapi import WebSocket


class Hub:
    def __init__(self):
        self.loop: asyncio.AbstractEventLoop | None = None
        self.clients: dict[WebSocket, str] = {}  # ws -> role ("caregiver" | "room")

    def attach_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop

    def count(self, role: str) -> int:
        return sum(1 for r in self.clients.values() if r == role)

    async def register(self, ws: WebSocket, role: str) -> None:
        self.clients[ws] = role

    def unregister(self, ws: WebSocket) -> None:
        self.clients.pop(ws, None)

    async def send(self, ws: WebSocket, event: dict) -> None:
        await ws.send_text(json.dumps(event))

    async def broadcast(self, event: dict, role: str | None = None) -> None:
        data = json.dumps(event)
        for ws, r in list(self.clients.items()):
            if role and r != role:
                continue
            try:
                await ws.send_text(data)
            except Exception:
                self.unregister(ws)

    def publish(self, event: dict, role: str | None = None) -> None:
        """Schedule a broadcast from any thread."""
        if self.loop is None:
            return
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is self.loop:
            self.loop.create_task(self.broadcast(event, role))
        else:
            asyncio.run_coroutine_threadsafe(self.broadcast(event, role), self.loop)
