import numpy as np
import wave
import tempfile
import os
import core.voice_response as voice_response

# ─── Settings ───────────────────────────────────────────────
SAMPLE_RATE = 16000
CHUNK_SIZE = 1024
SILENCE_DURATION = 1.5
MAX_RECORD_SECONDS = 15
WHISPER_PROMPT = (
    "Jarvis open vscode safari terminal chrome "
    "search google find file resume email weather time date "
    "volume brightness screenshot battery mute unmute "
    "lock screen shutdown restart sleep minimise fullscreen "
    "what time is it what is the weather open my "
    "hey how are you good morning"
)
CORRECTIONS = {
    "jihadis": "jarvis",
    "javas":   "jarvis",
    "davas":   "jarvis",
    "java":    "jarvis",
    "jabas":   "jarvis",
    "dava":    "jarvis",   # fixed — removed space
    "crome":   "chrome",
    "saf":     "safari",
    # Terminal mishearings
    "power cell":  "powershell",
    "power shell": "powershell",
    "power sel":   "powershell",
    "powersel":    "powershell",
    "powercell":   "powershell",
}

# ─── Garbage Words ───────────────────────────────────────────
# Single-word transcriptions Whisper hallucinates from ambient noise.
# If the entire transcript is just one of these, discard it.
GARBAGE_WORDS = {
    "you", "the", "a", "an", "and", "is", "it", "to", "of",
    "in", "on", "i", "he", "she", "we", "they", "do", "so",
    "if", "or", "but", "be", "at", "by", "my", "me", "no",
    "oh", "ah", "uh", "um", "hmm", "huh", "ok", "okay",
    "nah", "nope", "right", "well",
    "thank", "thanks", "bye", "hi", "hey", "percent","pls.",
}
# ────────────────────────────────────────────────────────────
# ────────────────────────────────────────────────────────────

model = None


def _get_pyaudio():
    """Import PyAudio lazily so non-audio code can still import this module."""
    try:
        import pyaudio
        return pyaudio
    except ImportError as e:
        raise RuntimeError("PyAudio is required for microphone input.") from e

def _get_model():
    global model
    if model is None:
        import whisper
        model = whisper.load_model("small")
    return model


def preload_whisper():
    """Pre-warm the Whisper model at startup so it never loads mid-command."""
    global model
    if model is None:
        import whisper
        print("🧠 Loading Whisper model...")
        model = whisper.load_model("small")
        print("✅ Whisper ready")


def _deduplicate_whisper(text: str) -> str:
    """Remove stuttered/repeated phrases from Whisper output.
    e.g. 'send email send email' → 'send email'
    e.g. 'open terminal open terminal open' → 'open terminal'
    """
    if not text:
        return text
    words = text.split()
    if len(words) < 4:
        return text

    # Try phrase lengths from half-sentence down to 2 words
    for phrase_len in range(len(words) // 2, 1, -1):
        phrase = ' '.join(words[:phrase_len])
        rest = ' '.join(words[phrase_len:])
        # Check if the rest starts with the same phrase
        if rest.startswith(phrase):
            # Remove the repeated portion, keep any trailing words
            remainder = rest[len(phrase):].strip()
            cleaned = phrase + (" " + remainder if remainder else "")
            return _deduplicate_whisper(cleaned)  # recurse

    return text


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
    Ignores all audio while Jarvis is speaking to prevent feedback loop.
    """
    pyaudio = _get_pyaudio()
    audio_interface = pyaudio.PyAudio()

    stream = audio_interface.open(
        format=pyaudio.paInt16,
        channels=1,
        rate=SAMPLE_RATE,
        input=True,
        frames_per_buffer=CHUNK_SIZE
    )

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

        # ── Ignore audio while Jarvis is speaking ────────────
        if voice_response.is_speaking:
            continue   # throw away chunk, don't add to frames
        # ─────────────────────────────────────────────────────

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
    result = _get_model().transcribe(
        tmp_path,
        language="en",
        fp16=False,
        initial_prompt=WHISPER_PROMPT
    )
    text = result["text"].strip().lower()

    for wrong, right in CORRECTIONS.items():
        text = text.replace(wrong, right)

    text = _deduplicate_whisper(text)

    os.remove(tmp_path)

    # ── Reject garbage single-word hallucinations ────────────
    if text and len(text.split()) <= 1 and text in GARBAGE_WORDS:
        print(f"🗑️  Ignoring noise: '{text}'")
        return ""

    print(f"📝 You said: '{text}'")
    return text


def listen_long(max_seconds: int = 30, silence_seconds: float = 2.5) -> str:
    """
    Extended listen — for longer voice input like email body.
    Uses a longer silence threshold and recording limit to avoid
    cutting the user off mid-sentence.
    """
    pyaudio = _get_pyaudio()
    audio_interface = pyaudio.PyAudio()

    stream = audio_interface.open(
        format=pyaudio.paInt16,
        channels=1,
        rate=SAMPLE_RATE,
        input=True,
        frames_per_buffer=CHUNK_SIZE
    )

    silence_threshold = calibrate_silence(stream)

    print("\n🎙️  Listening (extended)...")

    frames = []
    silent_chunks = 0
    has_speech = False

    chunks_per_second = SAMPLE_RATE / CHUNK_SIZE
    max_silent_chunks = int(chunks_per_second * silence_seconds)
    max_total_chunks = int(chunks_per_second * max_seconds)

    for _ in range(max_total_chunks):
        raw = stream.read(CHUNK_SIZE, exception_on_overflow=False)

        # ── Ignore audio while Jarvis is speaking ────────────
        if voice_response.is_speaking:
            continue
        # ─────────────────────────────────────────────────────

        chunk = np.frombuffer(raw, dtype=np.int16)
        frames.append(raw)

        if is_silent(chunk, silence_threshold):
            silent_chunks += 1
            if has_speech and silent_chunks >= max_silent_chunks:
                print("✅ Done listening (extended)")
                break
        else:
            has_speech = True
            silent_chunks = 0

    # Clean up mic
    stream.stop_stream()
    stream.close()
    audio_interface.terminate()

    if not has_speech:
        print("⚠️  No speech detected (extended)")
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
    print("🧠 Transcribing (extended)...")
    result = _get_model().transcribe(
        tmp_path,
        language="en",
        fp16=False,
        initial_prompt=WHISPER_PROMPT
    )
    text = result["text"].strip().lower()

    for wrong, right in CORRECTIONS.items():
        text = text.replace(wrong, right)

    text = _deduplicate_whisper(text)

    os.remove(tmp_path)

    # ── Reject garbage single-word hallucinations ────────────
    if text and len(text.split()) <= 1 and text in GARBAGE_WORDS:
        print(f"🗑️  Ignoring noise: '{text}'")
        return ""

    print(f"📝 You said (extended): '{text}'")
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
