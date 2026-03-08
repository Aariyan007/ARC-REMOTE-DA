import whisper
import pyaudio
import numpy as np
import wave
import tempfile
import os

# ─── Settings ───────────────────────────────────────────────
SAMPLE_RATE = 16000        # Whisper works best at 16kHz
CHUNK_SIZE = 1024          # How much audio we read at a time
SILENCE_DURATION = 1.5     # Seconds of silence before we stop recording
MAX_RECORD_SECONDS = 15    # Safety cap — stop after 15 sec no matter what
# ────────────────────────────────────────────────────────────

# Load Whisper model once when file is imported
print("Loading Whisper model...")
model = whisper.load_model("base")
print("Whisper ready ✅")


def calibrate_silence(stream) -> float:
    """Measure background noise for 1 second, return threshold above it."""
    print("🔇 Calibrating background noise...")
    chunks = []
    for _ in range(int(SAMPLE_RATE / CHUNK_SIZE)):
        raw = stream.read(CHUNK_SIZE, exception_on_overflow=False)
        chunk = np.frombuffer(raw, dtype=np.int16)
        chunks.append(np.abs(chunk).mean())

    background = np.mean(chunks)
    threshold = background * 2.5
    print(f"✅ Threshold set to {int(threshold)} (background was {int(background)})")
    return threshold


def is_silent(audio_chunk: np.ndarray, threshold: float) -> bool:
    """Check if an audio chunk is silent."""
    return np.abs(audio_chunk).mean() < threshold


def listen() -> str:
    """
    Opens mic, calibrates for background noise, records until silence,
    transcribes with Whisper, returns lowercased text.
    """
    audio_interface = pyaudio.PyAudio()

    stream = audio_interface.open(
        format=pyaudio.paInt16,
        channels=1,
        rate=SAMPLE_RATE,
        input=True,
        frames_per_buffer=CHUNK_SIZE
    )

    # ✅ Calibration happens HERE — after stream is open
    silence_threshold = calibrate_silence(stream)

    print("\n🎙️  Listening...")

    frames = []
    silent_chunks = 0
    has_speech = False

    chunks_per_second = SAMPLE_RATE / CHUNK_SIZE
    max_silent_chunks = int(chunks_per_second * SILENCE_DURATION)
    max_total_chunks = int(chunks_per_second * MAX_RECORD_SECONDS)

    for _ in range(max_total_chunks):
        raw = stream.read(CHUNK_SIZE, exception_on_overflow=False)
        chunk = np.frombuffer(raw, dtype=np.int16)
        frames.append(raw)

        if is_silent(chunk, silence_threshold):
            silent_chunks += 1
            if has_speech and silent_chunks >= max_silent_chunks:
                print("✅ Done listening")
                break
        else:
            has_speech = True
            silent_chunks = 0

    # Clean up mic
    stream.stop_stream()
    stream.close()
    audio_interface.terminate()

    if not has_speech:
        print("⚠️  No speech detected")
        return ""

    # Save to temp file for Whisper
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = tmp.name
        with wave.open(tmp_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(audio_interface.get_sample_size(pyaudio.paInt16))
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(b"".join(frames))

    # Transcribe
    print("🧠 Transcribing...")
    result = model.transcribe(tmp_path, language="en", fp16=False)
    text = result["text"].strip().lower()

    # Delete temp file immediately
    os.remove(tmp_path)

    print(f"📝 You said: '{text}'")
    return text


# ─── Quick test ─────────────────────────────────────────────
if __name__ == "__main__":
    while True:
        command = listen()
        if command:
            print(f"Result: {command}")
        if "stop" in command or "exit" in command:
            print("Stopping test.")
            break