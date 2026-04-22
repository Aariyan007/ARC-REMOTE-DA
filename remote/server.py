import sys
import threading
import uuid
import asyncio
from typing import Optional
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import core.runtime as runtime
from remote.job_store import get_job_store, JobEvent

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
    user: str = "aariyan"

class ReplyIn(BaseModel):
    answer: str

@app.on_event("startup")
def _startup():
    def _boot():
        runtime.boot(voice=False)
    threading.Thread(target=_boot, daemon=True).start()

@app.post("/command")
def run_command(body: CommandIn):
    """
    Submit a command. Returns a job_id immediately.
    """
    if not runtime._booted:
        raise HTTPException(status_code=503, detail="Runtime booting.")

    job_id = str(uuid.uuid4())
    job = get_job_store().get_or_create(job_id)
    job.add_event(JobEvent("ack", f"Command received: {body.text}"))

    def _run():
        # Session ID is the job_id so intent_router can access it
        res = runtime.execute_text_command(
            text=body.text,
            source=body.source,
            session_id=job_id,
            user=body.user
        )
        if res.status == "completed":
            job.add_event(JobEvent("result", res.final_result or "Completed", data=res.to_dict()))
        else:
            job.add_event(JobEvent("error", res.final_result or "Failed", data=res.to_dict()))

    threading.Thread(target=_run, daemon=True).start()
    return {"job_id": job_id}

@app.post("/reply/{job_id}")
def reply_job(job_id: str, body: ReplyIn):
    """
    Answer a clarify/confirm event for a running job.
    """
    job = get_job_store().get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    job.set_reply(body.answer)
    return {"status": "ok"}

@app.websocket("/stream/{job_id}")
async def stream_job(websocket: WebSocket, job_id: str):
    """
    Stream events for a job via WebSocket.
    Events: ack -> clarify/confirm -> executing -> verify -> result
    """
    await websocket.accept()
    job = get_job_store().get(job_id)
    if not job:
        await websocket.close(code=1008)
        return

    sent_idx = 0
    try:
        while True:
            current_len = len(job.events)
            if current_len > sent_idx:
                for i in range(sent_idx, current_len):
                    event = job.events[i]
                    await websocket.send_json(event.to_dict())
                    if event.type in ("result", "error"):
                        await websocket.close()
                        return
                sent_idx = current_len
            await asyncio.sleep(0.1)
    except WebSocketDisconnect:
        pass

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
