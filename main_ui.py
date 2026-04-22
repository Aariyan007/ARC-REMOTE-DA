"""
Desktop API Server — FastAPI entry point for remote command execution.

Exposes:
  POST /command          → execute a text command, returns CommandResponse JSON
  GET  /status/{id}      → poll a previous command's result
  GET  /video            → MJPEG camera stream (optional)
  GET  /face             → face detection state
  GET  /sensor           → sensor data update endpoint
  GET  /sensor-data      → current sensor readings
  GET  /                 → serve the local UI

Start with:
  uvicorn main_ui:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import sys
import threading
import time
import atexit
import uuid
from typing import Optional

# ── pkg_resources fix ─────────────────────────────────────────
try:
    import pkg_resources  # type: ignore
except ImportError:
    class _MockDistribution:
        def __init__(self, version='2.0.10'):
            self.version = version
    class _MockPkgResources:
        def get_distribution(self, name):
            return _MockDistribution()
    sys.modules['pkg_resources'] = _MockPkgResources()

try:
    import dotenv
    dotenv.load_dotenv()
except ImportError:
    pass

# ── FastAPI ───────────────────────────────────────────────────
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse, FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ── Jarvis Runtime ────────────────────────────────────────────
import core.runtime as runtime

# ═══════════════════════════════════════════════════════════════
#   FASTAPI APP
# ═══════════════════════════════════════════════════════════════

app = FastAPI(
    title="Desktop Automation Engine",
    description="Remote control your desktop — find files, send emails, open apps.",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],    # tighten for production
    allow_methods=["*"],
    allow_headers=["*"],
)

try:
    app.mount("/ui", StaticFiles(directory="ui"), name="ui")
except Exception:
    pass  # ui directory may not exist in all environments


# ── Request / Response models ─────────────────────────────────

class CommandIn(BaseModel):
    text: str
    source: str = "api"
    session_id: Optional[str] = None
    user: str = "aariyan"


class ConfirmIn(BaseModel):
    request_id: str
    choice: str    # e.g. full file path, or "cancel"
    source: str = "api"


# ── Camera setup (optional — disable if camera not present) ───

_camera_enabled = False
_lock = threading.Lock()
latest_frame = None
latest_face = None
sensor_data = {"heart": 0, "temp": 0.0}

try:
    import cv2
    import mediapipe as mp

    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    cap.set(cv2.CAP_PROP_FPS, 30)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    def _camera_loop():
        global latest_frame, latest_face
        detector = mp.solutions.face_detection.FaceDetection(
            model_selection=0, min_detection_confidence=0.6
        )
        frame_count = 0
        while True:
            success, frame = cap.read()
            if not success:
                time.sleep(0.01)
                continue
            frame_count += 1
            if frame_count % 3 == 0:
                small = cv2.resize(frame, (640, 360))
                rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
                result = detector.process(rgb)
                face = None
                if result.detections:
                    det = result.detections[0]
                    box = det.location_data.relative_bounding_box
                    h, w = frame.shape[:2]
                    face = (int(box.xmin * w), int(box.ymin * h),
                            int(box.width * w), int(box.height * h))
                with _lock:
                    latest_face = face
            with _lock:
                latest_frame = frame

    threading.Thread(target=_camera_loop, daemon=True).start()
    _camera_enabled = True

    @atexit.register
    def _cleanup():
        cap.release()

except Exception as e:
    print(f"ℹ️  Camera disabled: {e}")


# ═══════════════════════════════════════════════════════════════
#   COMMAND API
# ═══════════════════════════════════════════════════════════════

@app.on_event("startup")
def _startup():
    """Boot the runtime in the background on server start."""
    def _boot():
        runtime.boot(voice=False)  # API mode: no Whisper preload needed
    threading.Thread(target=_boot, daemon=True).start()


@app.get("/")
def home():
    try:
        return FileResponse("ui/index.html")
    except Exception:
        return JSONResponse({"status": "Desktop Automation Engine", "version": "2.0.0"})


@app.post("/command")
def run_command(body: CommandIn):
    """
    Execute a text command on the desktop.

    Example:
        POST /command
        { "text": "find uber.txt and email it to aariyan@gmail.com", "source": "phone" }

    Returns a CommandResponse JSON object.
    """
    if not runtime._booted:
        raise HTTPException(status_code=503, detail="Runtime still booting. Retry in a few seconds.")

    response = runtime.execute_text_command(
        text=body.text,
        source=body.source,
        session_id=body.session_id,
        user=body.user,
    )
    return JSONResponse(response.to_dict())


@app.post("/confirm")
def confirm_command(body: ConfirmIn):
    """
    Resolve a NEEDS_CONFIRMATION command by providing a choice.

    Example:
        POST /confirm
        { "request_id": "abc-123", "choice": "/Users/aariyan/Documents/uber.txt" }
    """
    prev = runtime.get_result(body.request_id)
    if prev is None:
        raise HTTPException(status_code=404, detail=f"No result found for request_id={body.request_id}")

    if body.choice.lower() == "cancel":
        from core.command_models import CommandResponse, ExecutionStatus
        cancelled = CommandResponse(
            request_id=str(uuid.uuid4()),
            status=ExecutionStatus.CANCELLED,
            interpreted_action=prev.interpreted_action,
            final_result="Cancelled by user.",
            source=body.source,
        )
        runtime.store_result(cancelled)
        return JSONResponse(cancelled.to_dict())

    # Reconstruct command with the chosen file
    orig_data = prev.data
    filename_chosen = body.choice
    recipient = orig_data.get("recipient", "")

    if not recipient:
        raise HTTPException(status_code=400, detail="Cannot resume — no recipient in original request data.")

    response = runtime.execute_text_command(
        text=f"email {filename_chosen} to {recipient}",
        source=body.source,
        session_id=body.request_id,
    )
    return JSONResponse(response.to_dict())


@app.get("/status/{request_id}")
def get_status(request_id: str):
    """Poll the result of a previously submitted command."""
    result = runtime.get_result(request_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"No result for request_id={request_id}")
    return JSONResponse(result.to_dict())


@app.get("/health")
def health():
    return {"status": "ok", "booted": runtime._booted}


# ═══════════════════════════════════════════════════════════════
#   CAMERA / SENSOR (optional)
# ═══════════════════════════════════════════════════════════════

def _generate_frames():
    encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), 50]
    while True:
        with _lock:
            frame = latest_frame
        if frame is None:
            time.sleep(0.01)
            continue
        ret, buf = cv2.imencode(".jpg", frame, encode_params)
        if not ret:
            continue
        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n\r\n"
            + buf.tobytes()
            + b"\r\n"
        )
        time.sleep(0.02)


@app.get("/video")
def video():
    if not _camera_enabled:
        raise HTTPException(status_code=503, detail="Camera not available.")
    return StreamingResponse(
        _generate_frames(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


@app.get("/face")
def face():
    if not _camera_enabled:
        return {"face": False}
    with _lock:
        f = latest_face
    if f is None:
        return {"face": False}
    x, y, w, h = f
    return {"face": True, "x": x, "y": y, "w": w, "h": h}


@app.get("/sensor")
def sensor(heart: int = 0, temp: float = 0.0):
    sensor_data["heart"] = heart
    sensor_data["temp"] = round(temp, 1)
    return {"status": "ok"}


@app.get("/sensor-data")
def get_sensor_data():
    return sensor_data


# ═══════════════════════════════════════════════════════════════
#   ENTRY POINT
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)