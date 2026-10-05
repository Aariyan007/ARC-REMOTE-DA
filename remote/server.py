import os
import threading
import uuid
import asyncio
import time
import traceback
from typing import Optional, NamedTuple
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Depends, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

try:
    import dotenv
    dotenv.load_dotenv()
except ImportError:
    pass

import core.runtime as runtime
from remote import db
from remote.job_store import get_job_store, JobEvent, TERMINAL_TYPES
from remote.auth import (
    generate_pairing_code, verify_pairing_code, create_access_token,
    verify_access_token, is_locked_out, issue_ws_ticket, redeem_ws_ticket,
)
from remote.allowlist import validate_command, validate_source
from remote.security import log_audit_event

MAX_JOBS = int(os.getenv("ARC_MAX_JOBS", "8"))
MAX_JOBS_PER_DEVICE = int(os.getenv("ARC_MAX_JOBS_PER_DEVICE", "3"))
JOB_TIMEOUT = float(os.getenv("ARC_JOB_TIMEOUT", "600"))
WS_PING_INTERVAL = 20.0

_DEFAULT_CORS = [
    "capacitor://localhost", "ionic://localhost",
    "https://localhost", "http://localhost",
    "http://localhost:5173", "http://127.0.0.1:5173",
]


def _cors_origins() -> list:
    extra = [o.strip() for o in os.getenv("ARC_CORS_ORIGINS", "").split(",") if o.strip()]
    return _DEFAULT_CORS + extra


_boot_error: Optional[str] = None


def _boot():
    global _boot_error
    try:
        if not runtime.boot(voice=False):
            _boot_error = "Runtime failed to initialise actions (see server log)."
    except Exception as e:
        _boot_error = f"{type(e).__name__}: {e}"
        traceback.print_exc()


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("✨ ARC Server Starting...")
    try:
        db.prune_old_jobs()
    except Exception as e:
        print(f"Warning: prune failed: {e}")
    from remote.pair import announce_pairing
    announce_pairing(generate_pairing_code(announce=False))
    threading.Thread(target=_boot, daemon=True).start()
    yield


app = FastAPI(title="ARC Remote Daemon", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)


class CommandIn(BaseModel):
    text: str
    source: str = "api"


class ReplyIn(BaseModel):
    answer: str
    nonce: Optional[str] = None


class PairIn(BaseModel):
    code: str
    device_name: str


class PushIn(BaseModel):
    token: str
    platform: str = "unknown"


class Device(NamedTuple):
    id: str
    name: str


def _authenticate(token: str) -> Optional[Device]:
    payload = verify_access_token(token or "")
    if not payload or not payload.get("jti"):
        return None
    device_id = payload["jti"]
    if not db.device_is_active(device_id):
        return None
    return Device(device_id, str(payload.get("device", "unknown"))[:64])


def get_current_device(authorization: Optional[str] = Header(None)) -> Device:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid token")
    device = _authenticate(authorization.split(" ", 1)[1])
    if not device:
        raise HTTPException(status_code=401, detail="Invalid, expired or revoked token")
    db.touch_device(device.id, time.time())
    return device


def _client(request: Request) -> str:
    return request.client.host if request.client else "unknown"


# ── Pairing & devices ────────────────────────────────────────

@app.post("/pair")
def pair_device(body: PairIn, request: Request):
    client = _client(request)
    wait = is_locked_out(client)
    if wait:
        log_audit_event("", client, "pair_locked_out", body.device_name)
        raise HTTPException(
            status_code=429, detail="Too many failed attempts. Try again later.",
            headers={"Retry-After": str(wait)},
        )
    name = (body.device_name or "device").strip()[:64] or "device"
    if not verify_pairing_code(body.code, client):
        log_audit_event("", client, "pair_failed", name)
        wait = is_locked_out(client)
        if wait:
            raise HTTPException(
                status_code=429, detail="Too many failed attempts. Try again later.",
                headers={"Retry-After": str(wait)},
            )
        raise HTTPException(status_code=401, detail="Invalid or expired code")
    device_id = uuid.uuid4().hex[:16]
    db.register_device(device_id, name, time.time())
    token = create_access_token(name, device_id)
    log_audit_event("", device_id, "paired", f"{name} from {client}")
    return {"token": token, "device_id": device_id}


@app.post("/auth/refresh")
def refresh_token(device: Device = Depends(get_current_device)):
    return {"token": create_access_token(device.name, device.id)}


@app.post("/ws-ticket")
def ws_ticket(device: Device = Depends(get_current_device)):
    """One-time, 30s ticket for opening a WebSocket without putting the bearer token in the URL."""
    return {"ticket": issue_ws_ticket(device.id, device.name)}


@app.get("/devices")
def list_devices(device: Device = Depends(get_current_device)):
    return {
        "current": device.id,
        "devices": [d for d in db.list_devices() if not d["revoked"]],
    }


@app.delete("/devices/{device_id}")
def revoke_device(device_id: str, device: Device = Depends(get_current_device)):
    if not db.revoke_device(device_id):
        raise HTTPException(status_code=404, detail="Device not found")
    log_audit_event("", device.id, "device_revoked", device_id)
    return {"status": "ok"}


@app.post("/devices/push")
def register_push(body: PushIn, device: Device = Depends(get_current_device)):
    db.set_push_token(device.id, body.token[:512], body.platform[:16])
    return {"status": "ok"}


# ── Static web UI ────────────────────────────────────────────

try:
    app.mount("/assets", StaticFiles(directory="ui/assets"), name="assets")
except Exception:
    pass


def _static(path: str):
    if os.path.exists(path):
        return FileResponse(path)
    raise HTTPException(status_code=404)


@app.get("/")
def home():
    if os.path.exists("ui/index.html"):
        return FileResponse("ui/index.html")
    return JSONResponse({"status": "ARC Remote Daemon", "version": "1.1.0"})


@app.get("/manifest.json")
def manifest():
    return _static("ui/manifest.json")


@app.get("/sw.js")
def sw():
    return _static("ui/sw.js")


@app.get("/favicon.svg")
def favicon():
    return _static("ui/favicon.svg")


@app.get("/health")
def health_check():
    """Server health and runtime boot status."""
    booted = getattr(runtime, "_booted", False)
    out = {"status": "ok", "booted": booted}
    if _boot_error:
        out["boot_error"] = _boot_error
    return out


# ── Jobs ─────────────────────────────────────────────────────

def _owned_job_row(job_id: str, device: Device):
    """Return the job's DB row if it exists and belongs to `device`, else 404."""
    row = db.get_job(job_id)
    if not row or row["user"] != device.id:
        raise HTTPException(status_code=404, detail="Job not found")
    return row


def _job_events(job_id: str, since: int = 0) -> list:
    """Events for a job: live memory if present, else persisted history."""
    job = get_job_store().get(job_id)
    if job:
        with job.lock:
            return [e.to_dict() for e in job.events[since:]]
    return db.get_job_events(job_id, since)


@app.post("/command")
def run_command(body: CommandIn, device: Device = Depends(get_current_device)):
    """Submit a command. Returns a job_id immediately."""
    if not runtime._booted:
        detail = f"Runtime failed to boot: {_boot_error}" if _boot_error else "Runtime booting."
        raise HTTPException(status_code=503, detail=detail)

    ok, reason = validate_command(body.text)
    if not ok:
        log_audit_event("", device.id, "command_rejected", f"{reason}: {body.text[:200]}")
        raise HTTPException(status_code=400, detail=reason)
    source = validate_source(body.source)

    store = get_job_store()
    if store.running_count() >= MAX_JOBS or store.running_count(device.id) >= MAX_JOBS_PER_DEVICE:
        raise HTTPException(status_code=429, detail="Too many running jobs. Wait for one to finish.")

    job_id = str(uuid.uuid4())
    job = store.get_or_create(job_id, device.id)
    db.save_job(job_id, command=body.text, source=source, user=device.id, status="created", created_at=time.time())
    log_audit_event(job_id, device.id, "command", body.text)

    job.add_event(JobEvent("ack", f"Command received: {body.text}"))

    def _on_timeout():
        if job.add_event(JobEvent("error", f"Timed out after {int(JOB_TIMEOUT)}s")):
            job.cancelled = True
            log_audit_event(job_id, device.id, "job_timeout", body.text)

    timer = threading.Timer(JOB_TIMEOUT, _on_timeout)
    timer.daemon = True
    timer.start()

    def _run():
        try:
            job.add_event(JobEvent(
                "progress", "Routing command...",
                data={"stage": "routing", "step": 1, "total_steps": 4}
            ))
            job.add_event(JobEvent(
                "executing", f"Classifying: {body.text}",
                data={"stage": "classifying", "step": 2, "total_steps": 4}
            ))

            # Session ID is the job_id so intent_router can access it
            res = runtime.execute_text_command(
                text=body.text,
                source=source,
                session_id=job_id,
                user=device.name
            )

            if res is None:
                res = runtime.CommandResponse.ok(
                    job_id, "route",
                    f"Command '{body.text[:60]}' was processed.",
                    source=source,
                )

            # res.status is an ExecutionStatus enum, not a string.
            if getattr(res.status, 'value', res.status) == "completed":
                action = getattr(res, 'interpreted_action', None) or res.to_dict().get('interpreted_action', '')
                if action and action not in ('general_chat', 'answer_question', 'chat_response'):
                    job.add_event(JobEvent(
                        "verify", f"Verified: {action}",
                        data={"stage": "verifying", "action": action, "step": 3, "total_steps": 4}
                    ))
                job.add_event(JobEvent("result", res.final_result or "Completed", data=res.to_dict()))
            else:
                job.add_event(JobEvent("error", res.final_result or "Failed", data=res.to_dict()))
        except Exception as e:
            traceback.print_exc()
            # Don't leak internals to the client; the traceback stays in the server log.
            job.add_event(JobEvent("error", f"Internal error: {type(e).__name__}"))
        finally:
            timer.cancel()
            try:
                db.update_job_status(job_id, "cancelled" if job.cancelled else (
                    "failed" if job.events and job.events[-1].type == "error" else "completed"))
                log_audit_event(job_id, device.id, "job_finished", job.events[-1].message if job.events else "")
            except Exception:
                pass

    threading.Thread(target=_run, daemon=True).start()
    return {"job_id": job_id}


@app.post("/reply/{job_id}")
def reply_job(job_id: str, body: ReplyIn, device: Device = Depends(get_current_device)):
    """Answer a pending clarify/confirm prompt for one of this device's jobs."""
    _owned_job_row(job_id, device)
    job = get_job_store().get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if not job.set_reply(body.answer, nonce=body.nonce):
        raise HTTPException(status_code=409, detail="No matching prompt is waiting for a reply")
    log_audit_event(job_id, device.id, "reply", body.answer[:200])
    return {"status": "ok"}


@app.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str, device: Device = Depends(get_current_device)):
    _owned_job_row(job_id, device)
    job = get_job_store().get(job_id)
    if not job or job.finished:
        raise HTTPException(status_code=409, detail="Job is not running")
    if job.add_event(JobEvent("error", "Cancelled by user")):
        job.cancelled = True
        log_audit_event(job_id, device.id, "job_cancelled", "")
    return {"status": "ok"}


@app.get("/jobs/health_check_ping")
def health_ping(device: Device = Depends(get_current_device)):
    """Authenticated ping so the app can verify token validity with no side effects."""
    return {"status": "ok", "timestamp": time.time()}


@app.get("/jobs")
def list_my_jobs(limit: int = 20, device: Device = Depends(get_current_device)):
    return {"jobs": db.list_jobs(device.id, max(1, min(limit, 100)))}


@app.get("/jobs/{job_id}")
def get_job_status(job_id: str, since: int = 0, device: Device = Depends(get_current_device)):
    """Poll job events (alternative to WebSocket). `since` skips already-seen events."""
    row = _owned_job_row(job_id, device)
    return {
        "job_id": job_id,
        "status": row["status"],
        "events": _job_events(job_id, max(0, since)),
    }


@app.websocket("/stream/{job_id}")
async def stream_job(websocket: WebSocket, job_id: str):
    """
    Stream events for a job. Auth: obtain a one-time ticket via POST /ws-ticket and
    connect to /stream/{job_id}?ticket=<ticket>[&since=<n>]. `since` resumes after
    the first n events so a reconnect does not replay history.
    """
    redeemed = redeem_ws_ticket(websocket.query_params.get("ticket", ""))
    if not redeemed or not db.device_is_active(redeemed[0]):
        await websocket.close(code=1008)
        return
    device = Device(*redeemed)

    row = db.get_job(job_id)
    if not row or row["user"] != device.id:
        await websocket.close(code=1008)
        return

    try:
        sent_idx = max(0, int(websocket.query_params.get("since", "0")))
    except ValueError:
        sent_idx = 0

    await websocket.accept()
    loop = asyncio.get_running_loop()
    job = get_job_store().get(job_id)

    try:
        if job is None:
            # Job from before a restart (or evicted): replay history, then close.
            events = db.get_job_events(job_id, sent_idx)
            for e in events:
                await websocket.send_json(e)
            if not events or events[-1]["type"] not in TERMINAL_TYPES:
                if row["status"] in ("created", "running") or not events:
                    await websocket.send_json({
                        "type": "error", "message": "Job was interrupted by a server restart",
                        "data": {}, "timestamp": time.time(),
                    })
            await websocket.close()
            return

        def _wait_for_new_event():
            with job.new_event_cond:
                if len(job.events) <= sent_idx and not job.finished:
                    job.new_event_cond.wait(timeout=2.0)

        last_ping = time.time()
        while True:
            with job.lock:
                pending = job.events[sent_idx:]
            for event in pending:
                await websocket.send_json(event.to_dict())
                sent_idx += 1
                if event.type in TERMINAL_TYPES:
                    await websocket.close()
                    return
            if not db.device_is_active(device.id):
                await websocket.close(code=1008)
                return
            if time.time() - last_ping >= WS_PING_INTERVAL:
                await websocket.send_json({"type": "ping", "message": "", "data": {}, "timestamp": time.time()})
                last_ping = time.time()
            await loop.run_in_executor(None, _wait_for_new_event)
    except WebSocketDisconnect:
        pass


import datetime

@app.get("/suggestions")
def get_suggestions(device: Device = Depends(get_current_device)):
    """
    Returns dynamic command suggestions based on:
    1. Time of day (morning / afternoon / evening / night)
    2. Recent command history for this device (last 5 distinct commands)
    3. Capability-aware extras (Playwright browser, etc.)
    """
    from remote.db import get_recent_commands

    hour = datetime.datetime.now().hour
    suggestions = []

    # ── 1. Time-based suggestions ────────────────────────────────
    if 5 <= hour < 12:
        suggestions.extend([
            {"cmd": "good morning",   "icon": "☀️",  "label": "Good morning"},
            {"cmd": "read my emails", "icon": "📧",  "label": "Check emails"},
            {"cmd": "read the news",  "icon": "📰",  "label": "Today's news"},
        ])
    elif 12 <= hour < 17:
        suggestions.extend([
            {"cmd": "take a screenshot",  "icon": "📸", "label": "Screenshot"},
            {"cmd": "what time is it",    "icon": "🕐", "label": "Check time"},
            {"cmd": "search my emails",   "icon": "📧", "label": "Search emails"},
        ])
    elif 17 <= hour < 22:
        suggestions.extend([
            {"cmd": "play some music",  "icon": "🎵", "label": "Play music"},
            {"cmd": "get battery level","icon": "🔋", "label": "Battery"},
            {"cmd": "lock screen",      "icon": "🔒", "label": "Lock screen"},
        ])
    else:
        suggestions.extend([
            {"cmd": "good night", "icon": "🌙", "label": "Good night"},
            {"cmd": "lock screen","icon": "🔒", "label": "Lock screen"},
            {"cmd": "sleep",      "icon": "😴", "label": "Sleep Mac"},
        ])

    # ── 2. Always-available core shortcuts ───────────────────────
    suggestions.extend([
        {"cmd": "open chrome",    "icon": "🌐", "label": "Open Chrome"},
        {"cmd": "find my files",  "icon": "📁", "label": "Find files"},
        {"cmd": "volume up",      "icon": "🔊", "label": "Volume up"},
        {"cmd": "send an email",  "icon": "✉️", "label": "Send email"},
        {"cmd": "create a file",  "icon": "📄", "label": "New file"},
        {"cmd": "what can you do","icon": "💡", "label": "Help"},
    ])

    # ── 3. Capability-aware: Playwright browser ───────────────────
    try:
        import importlib.util
        if importlib.util.find_spec("playwright") is not None:
            suggestions.extend([
                {"cmd": "open youtube", "icon": "▶️",  "label": "YouTube"},
                {"cmd": "open google",  "icon": "🔍",  "label": "Google"},
            ])
    except Exception:
        pass

    # ── 4. Recent command history for this device ─────────────────
    recent_cmds = get_recent_commands(device.id, limit=5)
    already = {s["cmd"] for s in suggestions}

    # Icon heuristics for recent commands
    def _icon_for(cmd: str) -> str:
        cmd_l = cmd.lower()
        if "battery"    in cmd_l: return "🔋"
        if "screenshot" in cmd_l: return "📸"
        if "email"      in cmd_l: return "📧"
        if "music"      in cmd_l or "play"   in cmd_l: return "🎵"
        if "volume"     in cmd_l: return "🔊"
        if "brightness" in cmd_l: return "☀️"
        if "file"       in cmd_l or "create" in cmd_l: return "📄"
        if "open"       in cmd_l: return "🚀"
        if "search"     in cmd_l or "find"   in cmd_l: return "🔍"
        if "lock"       in cmd_l or "sleep"  in cmd_l: return "🔒"
        return "🔁"

    def _truncate(s: str, n: int = 24) -> str:
        return s if len(s) <= n else s[:n - 1] + "…"

    recent_suggestions = [
        {
            "cmd":   r["command"],
            "icon":  _icon_for(r["command"]),
            "label": _truncate(r["command"], 24),
            "recent": True,
        }
        for r in recent_cmds
        if r["command"] not in already
    ][:3]  # cap at 3 recent

    # Prepend recent so they appear first in the UI
    suggestions = recent_suggestions + suggestions

    return {"suggestions": suggestions}


if __name__ == "__main__":
    import uvicorn
    # Loopback by default; expose via `tailscale serve` (HTTPS) or set ARC_HOST=0.0.0.0 on a trusted LAN.
    uvicorn.run(app, host=os.getenv("ARC_HOST", "127.0.0.1"), port=int(os.getenv("ARC_PORT", "8000")))
