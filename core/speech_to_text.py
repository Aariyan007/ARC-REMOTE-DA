import whisper
import pyaudio
import numpy as np
import wave
import tempfile
import os

# ─── Settings ───────────────────────────────────────────────
SAMPLE_RATE = 16000        # Whisper works best at 16kHz
CHUNK_SIZE = 1024          # How much audio we read at a time
SILENCE_THRESHOLD = 500    # Volume level below this = silence
SILENCE_DURATION = 1.5     # Seconds of silence before we stop recording
MAX_RECORD_SECONDS = 15    # Safety cap — stop after 15 sec no matter what
# ────────────────────────────────────────────────────────────

# Load Whisper model once when file is imported
# This takes 2-3 seconds on first run — normal
print("Loading Whisper model...")
model = whisper.load_model("base")
print("Whisper ready ✅")


def is_silent(audio_chunk: np.ndarray) -> bool:
    """Check if an audio chunk is silent (you stopped talking)."""
    volume = np.abs(audio_chunk).mean()
    return volume < SILENCE_THRESHOLD


def listen() -> str:
    """
    Opens mic, records until silence detected, returns transcribed text.
    
    Returns:
        str: What you said, lowercased. Example: "open vscode"
        Returns "" if nothing was captured.
    """
    audio_interface = pyaudio.PyAudio()

    stream = audio_interface.open(
        format=pyaudio.paInt16,
        channels=1,
        rate=SAMPLE_RATE,
        input=True,
        frames_per_buffer=CHUNK_SIZE
    )

    print("\n🎙️  Listening...")

    frames = []                      # All audio chunks collected
    silent_chunks = 0                # How many consecutive silent chunks
    has_speech = False               # Have we heard anything yet?

    # How many silent chunks = SILENCE_DURATION seconds
    chunks_per_second = SAMPLE_RATE / CHUNK_SIZE
    max_silent_chunks = int(chunks_per_second * SILENCE_DURATION)
    max_total_chunks = int(chunks_per_second * MAX_RECORD_SECONDS)

    for _ in range(max_total_chunks):
        raw = stream.read(CHUNK_SIZE, exception_on_overflow=False)
        chunk = np.frombuffer(raw, dtype=np.int16)
        frames.append(raw)

        if is_silent(chunk):
            silent_chunks += 1
            # Only stop if we already heard speech, then silence came
            if has_speech and silent_chunks >= max_silent_chunks:
                print("✅ Done listening")
                break
        else:
            # Sound detected — reset silence counter
            has_speech = True
            silent_chunks = 0

    # Clean up mic
    stream.stop_stream()
    stream.close()
    audio_interface.terminate()

    if not has_speech:
        print("⚠️  No speech detected")
        return ""

    # Save audio to a temp file so Whisper can read it
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = tmp.name
        with wave.open(tmp_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(audio_interface.get_sample_size(pyaudio.paInt16))
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(b"".join(frames))

    # Transcribe with Whisper
    print("🧠 Transcribing...")
    result = model.transcribe(tmp_path, language="en", fp16=False)
    text = result["text"].strip().lower()

    # Delete temp file immediately
    os.remove(tmp_path)

    print(f"📝 You said: '{text}'")
    return text


# ─── Quick test ─────────────────────────────────────────────
# Run this file directly to test: python3 speech_to_text.py
if __name__ == "__main__":
    while True:
        command = listen()
        if command:
            print(f"Result: {command}")
        if "stop" in command or "exit" in command:
            print("Stopping test.")
            break