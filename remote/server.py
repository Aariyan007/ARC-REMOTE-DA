import sys
import threading
import uuid
import asyncio
from typing import Optional
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Depends, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import time
import core.runtime as runtime
from remote.job_store import get_job_store, JobEvent
from remote.db import save_job
from remote.auth import generate_pairing_code, verify_pairing_code, create_access_token, verify_access_token
from remote.security import log_audit_event

app = FastAPI(title="ARC Remote Daemon (Phase 1)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class CommandIn(BaseModel):
    text: str
    source: str = "api"

class ReplyIn(BaseModel):
    answer: str

class PairIn(BaseModel):
    code: str
    device_name: str

def get_current_device(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid token")
    token = authorization.split(" ")[1]
    payload = verify_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return payload.get("device", "unknown")

@app.on_event("startup")
def _startup():
    print("✨ ARC Server Starting...")
    generate_pairing_code()
    def _boot():
        runtime.boot(voice=False)
    threading.Thread(target=_boot, daemon=True).start()

@app.post("/pair")
def pair_device(body: PairIn):
    if verify_pairing_code(body.code):
        token = create_access_token(body.device_name)
        return {"token": token}
    raise HTTPException(status_code=401, detail="Invalid or expired code")

@app.get("/pairing-code")
def get_code():
    # Only for testing/local UI. Real setup would display on desktop screen.
    return {"code": generate_pairing_code()}

from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

try:
    app.mount("/assets", StaticFiles(directory="ui/assets"), name="assets")
except Exception:
    pass

@app.get("/")
def home():
    import os
    if os.path.exists("ui/index.html"):
        return FileResponse("ui/index.html")
    return JSONResponse({"status": "ARC Remote Daemon", "version": "1.0.0"})

@app.get("/manifest.json")
def manifest():
    import os
    if os.path.exists("ui/manifest.json"):
        return FileResponse("ui/manifest.json")
    raise HTTPException(status_code=404)

@app.get("/sw.js")
def sw():
    import os
    if os.path.exists("ui/sw.js"):
        return FileResponse("ui/sw.js")
    raise HTTPException(status_code=404)

@app.get("/favicon.svg")
def favicon():
    import os
    if os.path.exists("ui/favicon.svg"):
        return FileResponse("ui/favicon.svg")
    raise HTTPException(status_code=404)

@app.get("/health")
def health_check():
    """
    Returns the server health and runtime boot status.
    """
    booted = getattr(runtime, "_booted", False)
    return {"status": "ok", "booted": booted}

@app.post("/command")
def run_command(body: CommandIn, device: str = Depends(get_current_device)):
    """
    Submit a command. Returns a job_id immediately.
    """
    if not runtime._booted:
        raise HTTPException(status_code=503, detail="Runtime booting.")

    job_id = str(uuid.uuid4())
    job = get_job_store().get_or_create(job_id)
    save_job(job_id, command=body.text, source=body.source, user=device, status="created", created_at=time.time())
    
    # Audit log
    log_audit_event(job_id, device, "command", body.text)
    
    job.add_event(JobEvent("ack", f"Command received: {body.text}"))

    def _run():
        try:
            # ── Stage 1: Routing ─────────────────────────────────
            job.add_event(JobEvent(
                "progress", "Routing command...",
                data={"stage": "routing", "step": 1, "total_steps": 4}
            ))

            # ── Stage 2: Classifying intent ──────────────────────
            job.add_event(JobEvent(
                "executing", f"Classifying: {body.text}",
                data={"stage": "classifying", "step": 2, "total_steps": 4}
            ))

            # Session ID is the job_id so intent_router can access it
            res = runtime.execute_text_command(
                text=body.text,
                source=body.source,
                session_id=job_id,
                user=device
            )
            
            if res is None:
                # BUG 12 FIX: route() didn't store a result (e.g. interrupted command).
                # Build a descriptive fallback using the correct factory signature.
                res = runtime.CommandResponse.ok(
                    job_id,
                    "route",
                    f"Command '{body.text[:60]}' was processed.",
                    source=body.source,
                )

            # BUG 1 FIX: res.status is an ExecutionStatus enum, not a string.
            # Comparing enum to str "completed" is always False.
            if getattr(res.status, 'value', res.status) == "completed":
                action = getattr(res, 'interpreted_action', None) or res.to_dict().get('interpreted_action', '')

                # ── Stage 3: Verification (skip for chat/question intents)
                if action and action not in ('general_chat', 'answer_question', 'chat_response'):
                    job.add_event(JobEvent(
                        "verify", f"Verified: {action}",
                        data={"stage": "verifying", "action": action, "step": 3, "total_steps": 4}
                    ))

                # ── Stage 4: Final result ────────────────────────
                job.add_event(JobEvent("result", res.final_result or "Completed", data=res.to_dict()))
            else:
                job.add_event(JobEvent("error", res.final_result or "Failed", data=res.to_dict()))
        except Exception as e:
            job.add_event(JobEvent("error", f"Internal error: {str(e)}", data={"traceback": str(e)}))

    threading.Thread(target=_run, daemon=True).start()
    return {"job_id": job_id}

@app.post("/reply/{job_id}")
def reply_job(job_id: str, body: ReplyIn, device: str = Depends(get_current_device)):
    """
    Answer a clarify/confirm event for a running job.
    """
    job = get_job_store().get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    job.set_reply(body.answer)
    return {"status": "ok"}

@app.get("/jobs/health_check_ping")
def health_ping(device: str = Depends(get_current_device)):
    """
    Authenticated ping for the mobile app to verify token validity
    without triggering any intent routing side effects.
    """
    return {"status": "ok", "timestamp": time.time()}

@app.get("/jobs/{job_id}")
def get_job_status(job_id: str, device: str = Depends(get_current_device)):
    """
    Poll for job status and events (alternative to WebSocket).
    """
    job = get_job_store().get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    return {
        "job_id": job_id,
        "events": [e.to_dict() for e in job.events]
    }

@app.websocket("/stream/{job_id}")
async def stream_job(websocket: WebSocket, job_id: str, token: str = None):
    """
    Stream events for a job via WebSocket.
    Events: ack -> clarify/confirm -> executing -> verify -> result

    BUG 5 FIX: WebSocket cannot use HTTP Authorization header from browser.
    Token is passed as a query param: /stream/{job_id}?token=<bearer_token>

    BUG-N FIX: replaced asyncio.sleep(0.1) polling with a condition-variable
    wait via run_in_executor. The old 10 Hz poll added up to 100ms latency per
    event, which was especially bad for 'clarify' prompts that need to appear
    immediately so the user knows to respond.
    """
    await websocket.accept()

    # Auth check — token comes as query param since WS headers aren't standard
    raw_token = websocket.query_params.get("token", "")
    if not raw_token:
        await websocket.send_json({"type": "error", "message": "Missing token"})
        await websocket.close(code=1008)
        return
    from remote.auth import verify_access_token
    payload = verify_access_token(raw_token)
    if not payload:
        await websocket.send_json({"type": "error", "message": "Invalid or expired token"})
        await websocket.close(code=1008)
        return

    job = get_job_store().get(job_id)
    if not job:
        await websocket.close(code=1008)
        return

    loop = asyncio.get_event_loop()
    sent_idx = 0

    def _wait_for_new_event():
        """Block in a thread until a new event is added or 2s timeout."""
        with job.new_event_cond:
            # Only wait if there's nothing new to send right now
            if len(job.events) <= sent_idx:
                job.new_event_cond.wait(timeout=2.0)

    try:
        while True:
            # Flush any events that arrived since last iteration
            current_len = len(job.events)
            if current_len > sent_idx:
                for i in range(sent_idx, current_len):
                    event = job.events[i]
                    await websocket.send_json(event.to_dict())
                    if event.type in ("result", "error"):
                        await websocket.close()
                        return
                sent_idx = current_len
            else:
                # Nothing new — block until the background thread notifies us
                # (or the 2s timeout fires as a safety net)
                await loop.run_in_executor(None, _wait_for_new_event)
    except WebSocketDisconnect:
        pass

import datetime

@app.get("/suggestions")
def get_suggestions(device: str = Depends(get_current_device)):
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
    recent_cmds = get_recent_commands(device, limit=5)
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
    uvicorn.run(app, host="0.0.0.0", port=8000)

