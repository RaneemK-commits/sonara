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
from pydantic import BaseModel, Field

from ..models.enrollment import EnrollmentService

from ..config import Config
from ..metrics import METRICS
from ..store import RequestStore, TransitionError
from .hub import Hub
from .push import PushService, validate_subscription


class RoomInput(BaseModel):
    action: str                 # talk | confirm | cancel | select
    intent: str | None = None


class StartEnrollment(BaseModel):
    profile_id: str = Field(min_length=1, max_length=64)
    keep_audio: bool = False


class SelectIntent(BaseModel):
    intent: str


class CaptureSample(BaseModel):
    manual: bool = True
    seconds: float = Field(default=3., ge=.3, le=5.)


class PushSubscription(BaseModel):
    endpoint: str = Field(max_length=2048)
    keys: dict[str, str]


class PushEndpoint(BaseModel):
    endpoint: str = Field(max_length=2048)


def create_app(cfg: Config, store: RequestStore, hub: Hub, controller) -> FastAPI:
    enrollment = EnrollmentService(cfg, controller)
    srv = cfg.section("server")
    token = srv.get("caregiver_token", "")
    display_timeout = srv.get("display_timeout_s", 10)
    web = cfg.path("web")
    push = PushService(cfg, store)

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
        push.start()
        task = asyncio.create_task(watchdog())
        yield
        task.cancel()
        await asyncio.to_thread(push.stop)
        controller.stop()
        if controller.capture is not None:
            controller.capture.close()

    app = FastAPI(title="Sonara", lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=web), name="static")

    @app.get("/sw.js")
    def service_worker():
        if not (web / "sw.js").is_file():
            raise HTTPException(404, "Push UI has not been installed")
        return FileResponse(web / "sw.js", media_type="application/javascript",
                            headers={"Service-Worker-Allowed": "/", "Cache-Control": "no-cache"})

    @app.get("/manifest.webmanifest")
    def manifest():
        if not (web / "manifest.webmanifest").is_file():
            raise HTTPException(404, "Push UI has not been installed")
        return FileResponse(web / "manifest.webmanifest", media_type="application/manifest+json")

    @app.get("/sonara-demo-ca.crt")
    def demo_certificate():
        # Public CA certificate only; never serve its adjacent private key or directory.
        cert = cfg.path("data/tls/caddy/pki/authorities/local/root.crt")
        if not cert.is_file():
            raise HTTPException(404, "Local demo HTTPS is not installed")
        return FileResponse(cert, media_type="application/x-x509-ca-cert", filename="sonara-demo-ca.crt")

    @app.get("/api/push/config")
    def push_config(x_sonara_token: str | None = Header(None)):
        check(x_sonara_token)
        return {"enabled": push.enabled, "public_key": push.public_key, "error": push.error}

    @app.post("/api/push/subscriptions")
    def subscribe_push(body: PushSubscription, x_sonara_token: str | None = Header(None)):
        check(x_sonara_token)
        if not push.enabled:
            raise HTTPException(503, "Web Push is not configured on this device")
        try:
            store.subscribe_push(validate_subscription(body.model_dump()))
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return {"ok": True}

    @app.delete("/api/push/subscriptions")
    def unsubscribe_push(body: PushEndpoint, x_sonara_token: str | None = Header(None)):
        check(x_sonara_token)
        store.unsubscribe_push(body.endpoint)
        return {"ok": True}

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
        if controller.enrollment_active and body.action in ("talk", "select"):
            raise HTTPException(409, "finish or close voice setup first")
        controller.submit(body.action, body.intent)
        return {"ok": True}

    # Regular def endpoints execute in FastAPI's worker threadpool, including capture/DTW.
    def enroll_call(method, *args, **kwargs):
        if not controller.audio_lock.acquire(blocking=False):
            raise HTTPException(409, "microphone or profile operation busy; retry shortly")
        try:
            return method(*args, **kwargs)
        except (ValueError, OSError, KeyError) as exc:
            raise HTTPException(422, str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(503, str(exc)) from exc
        finally:
            controller.audio_lock.release()

    @app.get("/api/profiles")
    def profiles():
        return enroll_call(enrollment.status)

    @app.post("/api/enrollment/start")
    def start_enrollment(body: StartEnrollment):
        return enroll_call(enrollment.start, body.profile_id, body.keep_audio)

    @app.post("/api/enrollment/intent")
    def select_enrollment_intent(body: SelectIntent):
        return enroll_call(enrollment.select, body.intent)

    @app.post("/api/enrollment/capture")
    def capture_enrollment(body: CaptureSample):
        return enroll_call(enrollment.capture, body.manual, body.seconds)

    @app.post("/api/enrollment/sample")
    def save_enrollment_sample():
        return enroll_call(enrollment.save_sample)

    @app.delete("/api/enrollment/intents/{intent}")
    def delete_enrollment_intent(intent: str):
        return enroll_call(enrollment.remove, intent)

    @app.delete("/api/enrollment/intents/{intent}/samples/{index}")
    def delete_enrollment_sample(intent: str, index: int):
        return enroll_call(enrollment.remove, intent, index)

    @app.post("/api/enrollment/calibrate")
    def calibrate_enrollment():
        return enroll_call(enrollment.calibrate)

    @app.post("/api/enrollment/test")
    def test_enrollment(body: CaptureSample):
        return enroll_call(enrollment.capture, body.manual, body.seconds, test=True)

    @app.post("/api/enrollment/finish")
    def finish_enrollment():
        return enroll_call(enrollment.finish)

    @app.post("/api/enrollment/cancel")
    def cancel_enrollment():
        return enroll_call(enrollment.cancel)

    @app.post("/api/profiles/{profile_id}/load")
    def load_profile(profile_id: str):
        return enroll_call(enrollment.load, profile_id)

    @app.delete("/api/profiles/{profile_id}")
    def delete_profile(profile_id: str):
        return enroll_call(enrollment.delete, profile_id)

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
            # Complete only the transport handshake so browsers receive close code 4401.
            # Closing before accept becomes HTTP 403 and hides the actionable reason.
            # Never register this socket or send request data.
            await sock.accept()
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
