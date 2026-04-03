import subprocess
import pyaudio
import numpy as np
import time

# ─── Settings ────────────────────────────────────────────────
VOICE = "Daniel"
RATE  = 200
# ─────────────────────────────────────────────────────────────

is_speaking      = False
_speech_process  = None


def _listen_for_interrupt(threshold_multiplier: float = 6.0) -> bool:
    """
    Listens to mic while Jarvis speaks.
    Returns True if user makes a sound (interruption).
    """
    CHUNK            = 1024
    SAMPLE_RATE      = 16000
    CALIBRATE_CHUNKS = 15

    audio  = pyaudio.PyAudio()
    stream = audio.open(
        format=pyaudio.paInt16,
        channels=1,
        rate=SAMPLE_RATE,
        input=True,
        frames_per_buffer=CHUNK
    )

    # ── Wait for Jarvis voice to start coming through speaker ──
    time.sleep(0.3)

    # ── Calibrate WITH Jarvis voice as background ──────────────
    # This sets threshold ABOVE Jarvis's own voice level
    calibration = []
    for _ in range(CALIBRATE_CHUNKS):
        raw   = stream.read(CHUNK, exception_on_overflow=False)
        chunk = np.frombuffer(raw, dtype=np.int16)
        calibration.append(np.abs(chunk).mean())
    threshold = np.mean(calibration) * threshold_multiplier

    interrupted = False

    # ── Listen while speech is running ─────────────────────────
    while _speech_process and _speech_process.poll() is None:
        raw    = stream.read(CHUNK, exception_on_overflow=False)
        chunk  = np.frombuffer(raw, dtype=np.int16)
        volume = np.abs(chunk).mean()

        if volume > threshold:
            interrupted = True
            break

    stream.stop_stream()
    stream.close()
    audio.terminate()
    return interrupted


def speak(text: str) -> bool:
    """
    Speaks text out loud.
    Listens for interruption while speaking.
    Returns True if completed fully, False if interrupted.

    Example:
        completed = speak("Opening Safari for you.")
        if not completed:
            # User interrupted — listen to what they said
    """
    global is_speaking, _speech_process
    is_speaking = True

    print(f"🔊 Jarvis: {text}")

    # Start speaking — non-blocking so mic can listen simultaneously
    _speech_process = subprocess.Popen(
        ["say", "-v", VOICE, "-r", str(RATE), text]
    )

    # Listen for interruption while speaking
    interrupted = _listen_for_interrupt(threshold_multiplier=6.0)

    if interrupted:
        # Kill speech immediately
        _speech_process.terminate()
        _speech_process.wait()
        _speech_process = None
        is_speaking     = False
        print("✋ Interrupted by user")
        return False

    # Wait for speech to finish naturally
    _speech_process.wait()
    _speech_process = None
    is_speaking     = False
    return True


def speak_and_wait(text: str) -> None:
    """
    Speaks text and always waits until finished.
    NOT interruptible — use for warnings like shutdown countdown.
    """
    global is_speaking
    is_speaking = True
    print(f"🔊 Jarvis: {text}")
    subprocess.run(["say", "-v", VOICE, "-r", str(RATE), text])
    is_speaking = False


# ─── Quick test ──────────────────────────────────────────────
if __name__ == "__main__":
    print("Testing interruptible speech...")
    print("Try interrupting mid-sentence!\n")

    result = speak("Hey Aariyan, I am going to say a very long sentence right now and you can interrupt me at any time by speaking. Go ahead, try it, I dare you.")

    if result:
        print("✅ Speech completed without interruption")
    else:
        print("✋ You interrupted me! Listening now...")