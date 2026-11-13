"""Local HTTP + WebSocket server running on the UNO Q.

/room       room display (kiosk browser on the external screen, same board)
/caregiver  caregiver dashboard (phone/laptop browser on the local Wi-Fi)

Only structured request metadata crosses the network. No audio is ever served.
"""
from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..config import Config
from ..metrics import METRICS
from ..store import RequestStore, TransitionError
from .hub import Hub


class RoomInput(BaseModel):
    action: str                 # talk | confirm | cancel | select
    intent: str | None = None


def create_app(cfg: Config, store: RequestStore, hub: Hub, controller) -> FastAPI:
    srv = cfg.section("server")
    token = srv.get("caregiver_token", "")
    display_timeout = srv.get("display_timeout_s", 10)
    web = cfg.path("web")

    def check(tok: str | None) -> None:
        if token and tok != token:
            raise HTTPException(401, "caregiver token required")

    def apply(rid: str, status: str, actor: str) -> dict:
        try:
            req, changed = store.transition(rid, status, actor)
        except KeyError:
            raise HTTPException(404, f"unknown request {rid}")
        except TransitionError as e:
            raise HTTPException(409, str(e))
        if changed:
            hub.publish({"type": "request", "request": req})
            controller.on_request_status(req)
        return req

    async def watchdog():
        """QUEUED with no caregiver-screen receipt after the timeout → NOT_DISPLAYED (honest)."""
        while True:
            await asyncio.sleep(1)
            now = datetime.now(timezone.utc)
            for r in store.active():
                if r["status"] != "QUEUED":
                    continue
                created = datetime.fromisoformat(r["created_at"].replace("Z", "+00:00"))
                if (now - created).total_seconds() > display_timeout:
                    try:
                        apply(r["request_id"], "NOT_DISPLAYED", "system")
                    except HTTPException:  # raced with a receipt/ack — fine
                        pass

    @asynccontextmanager
    async def lifespan(app):
        hub.attach_loop(asyncio.get_running_loop())
        controller.start()
        task = asyncio.create_task(watchdog())
        yield
        task.cancel()
        controller.stop()

    app = FastAPI(title="Sonara", lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=web), name="static")

    @app.get("/")
    def index():
        return RedirectResponse("/room")

    @app.get("/room")
    def room():
        return FileResponse(web / "room" / "index.html")

    @app.get("/caregiver")
    def caregiver():
        return FileResponse(web / "caregiver" / "index.html")

    @app.get("/api/health")
    def health():
        return {"ok": True, "bed_id": cfg.bed_id, "caregiver_screens": hub.count("caregiver"),
                "room_screens": hub.count("room"), "state": controller.state,
                "recognizer_ready": bool(controller.recognizer and controller.recognizer.ready)}

    @app.get("/api/requests")
    def list_requests(active: bool = False):
        return store.active() if active else store.history()

    @app.post("/api/requests/{rid}/acknowledge")
    def acknowledge(rid: str, x_sonara_token: str | None = Header(None)):
        check(x_sonara_token)
        return apply(rid, "ACKNOWLEDGED", "caregiver")

    @app.post("/api/requests/{rid}/complete")
    def complete(rid: str, x_sonara_token: str | None = Header(None)):
        check(x_sonara_token)
        return apply(rid, "COMPLETED", "caregiver")

    @app.get("/api/requests/{rid}/events")
    def events(rid: str):
        return store.events(rid)

    @app.post("/api/room/input")
    def room_input(body: RoomInput):
        if body.action not in ("talk", "confirm", "cancel", "select"):
            raise HTTPException(400, "bad action")
        controller.submit(body.action, body.intent)
        return {"ok": True}

    @app.get("/api/metrics")
    def metrics():
        return METRICS.summary()

    @app.post("/api/reset")
    def reset(x_sonara_token: str | None = Header(None)):
        """Delete all stored request metadata (demo reset / data deletion)."""
        check(x_sonara_token)
        store.reset()
        controller.request_id = None
        hub.publish({"type": "snapshot", "active": [], "history": []})
        controller._publish()
        return {"ok": True}

    @app.websocket("/ws")
    async def ws(sock: WebSocket, role: str = "room"):
        tok = sock.query_params.get("token")
        if role == "caregiver" and token and tok != token:
            await sock.close(code=4401)
            return
        await sock.accept()
        await hub.register(sock, role)
        try:
            if role == "caregiver":
                # replay everything outstanding; the browser answers with receipts
                await hub.send(sock, {"type": "snapshot", "active": store.active(),
                                      "history": store.history(20)})
            else:
                await hub.send(sock, controller.room_state())
            while True:
                msg = json.loads(await sock.receive_text())
                if role == "caregiver" and msg.get("type") == "receipt":
                    req = store.get(msg.get("request_id", ""))
                    if req and req["status"] in ("QUEUED", "NOT_DISPLAYED"):
                        apply(req["request_id"], "DISPLAYED", "caregiver_screen")
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            hub.unregister(sock)

    return app
