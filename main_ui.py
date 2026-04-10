import sys
import threading
import time
import atexit
# Add this import at the top of main_ui.py
from core.voice_response import speak
from core.logger import print_todays_summary
try:
    import pkg_resources
except ImportError:
    class _MockDistribution:
        def __init__(self, version='2.0.10'):
            self.version = version
    class _MockPkgResources:
        def get_distribution(self, name):
            return _MockDistribution()
    sys.modules['pkg_resources'] = _MockPkgResources()

# ── pkg_resources fix for SpeechBrain ────────────────────────
try:
    import pkg_resources  # type: ignore
except ImportError:
    pass

# ── FastAPI / Camera ──────────────────────────────────────────
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse, FileResponse
import cv2
import mediapipe as mp

# ── Jarvis Core ───────────────────────────────────────────────
from core.listener import start_listener
from core.speech_to_text import listen
from core.intent_router import route

# ── Control ───────────────────────────────────────────────────
from control.mac.open_apps import open_vscode, open_safari, open_terminal
from control.web_search import search_google
from control.time_utils import tell_time, tell_date
from control.mac.system_actions import lock_screen, shutdown_pc, restart_pc

# ═══════════════════════════════════════════════════════════════
#   FASTAPI APP
# ═══════════════════════════════════════════════════════════════

app = FastAPI()
app.mount("/ui", StaticFiles(directory="ui"), name="ui")

# ── Camera setup ─────────────────────────────────────────────
cap = cv2.VideoCapture(1)
cap = cv2.VideoCapture(1, cv2.CAP_DSHOW)
cap.set(cv2.CAP_PROP_FRAME_WIDTH,  640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
cap.set(cv2.CAP_PROP_FPS,          30)
cap.set(cv2.CAP_PROP_BUFFERSIZE,   1)   # prevents lag buildup

# ── Shared state ─────────────────────────────────────────────
_lock        = threading.Lock()
latest_frame = None
latest_face  = None
sensor_data  = {"heart": 0, "temp": 0.0}

# ── Camera thread ─────────────────────────────────────────────
def camera_loop():
    global latest_frame, latest_face

    local_detector = mp.solutions.face_detection.FaceDetection(
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
            small  = cv2.resize(frame, (640, 360))
            rgb    = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
            result = local_detector.process(rgb)

            face = None
            if result.detections:
                det = result.detections[0]
                box = det.location_data.relative_bounding_box
                h, w = frame.shape[:2]
                x  = int(box.xmin  * w)
                y  = int(box.ymin  * h)
                bw = int(box.width  * w)
                bh = int(box.height * h)
                face = (x, y, bw, bh)

            with _lock:
                latest_face = face

        with _lock:
            latest_frame = frame

threading.Thread(target=camera_loop, daemon=True).start()

# ── MJPEG stream ──────────────────────────────────────────────
def generate_frames():
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

# ── Routes ────────────────────────────────────────────────────
@app.get("/")
def home():
    return FileResponse("ui/index.html")

@app.get("/video")
def video():
    return StreamingResponse(
        generate_frames(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma":        "no-cache",
            "Expires":       "0",
        }
    )

@app.get("/face")
def face():
    with _lock:
        f = latest_face
    if f is None:
        return {"face": False}
    x, y, w, h = f
    return {"face": True, "x": x, "y": y, "w": w, "h": h}

@app.get("/sensor")
def sensor(heart: int = 0, temp: float = 0.0):
    sensor_data["heart"] = heart
    sensor_data["temp"]  = round(temp, 1)
    return {"status": "ok"}

@app.get("/sensor-data")
def get_sensor_data():
    return sensor_data

# ── Cleanup on exit ───────────────────────────────────────────
@atexit.register
def cleanup():
    cap.release()

# ═══════════════════════════════════════════════════════════════
#   JARVIS ASSISTANT LOOP
# ═══════════════════════════════════════════════════════════════

ACTIONS = {
    "open_vscode":   open_vscode,
    "open_safari":   open_safari,
    "open_terminal": open_terminal,
    "search_google": search_google,
    "tell_time":     tell_time,
    "tell_date":     tell_date,
    "lock_screen":   lock_screen,
    "shutdown_pc":   shutdown_pc,
    "restart_pc":    restart_pc,
}

def assistant_loop():
    speak("Yes, I'm listening")
    print("\n✅ FRIEND activated — listening for your command...")

    while True:
        command = listen()

        if not command:
            print("⚠️  Didn't catch that. Try again.")
            continue

        if any(word in command for word in ["goodbye", "go to sleep", "stop listening"]):
            print_todays_summary()
            print("😴 Jarvis going to sleep. Say the wake word to activate again.")
            break

        route(command, ACTIONS)

def jarvis_loop():
    print("=" * 50)
    print("  JARVIS STARTING UP")
    print("=" * 50)
    print("Say the wake word to activate Jarvis...\n")

    while True:
        activated = start_listener()
        if activated:
            assistant_loop()
            print("\nWaiting for wake word again...\n")

# ── Entry point ───────────────────────────────────────────────
if __name__ == "__main__":
    # Jarvis assistant runs in background thread
    threading.Thread(target=jarvis_loop, daemon=True).start()

    # FastAPI serves the UI + camera stream
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)