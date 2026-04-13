"""
Voice Response — Hybrid TTS system.

Strategy:
- Mac `say` for quick acks ("Got it", "On it") → instant feel
- ElevenLabs for longer/smarter responses → premium quality
- Stream ElevenLabs chunks to reduce perceived latency
- Fallback to Mac `say` when ElevenLabs tokens exhausted
"""

import subprocess
import sys
import os
import time
import pyaudio
import numpy as np
from dotenv import load_dotenv

load_dotenv()

# ─── Settings ────────────────────────────────────────────────
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
VOICE_ID           = os.getenv("ELEVENLABS_VOICE_ID", "TxGEqnHWrfWFTfGW9XjX")  # Josh voice
USE_ELEVENLABS     = os.getenv("USE_ELEVENLABS", "false").lower() == "true"

# Mac fallback settings
MAC_VOICE = "Daniel"
MAC_RATE  = 200

# Threshold: responses shorter than this use Mac say (instant)
# Longer responses use ElevenLabs (quality)
SHORT_RESPONSE_WORDS = 6
# ─────────────────────────────────────────────────────────────

is_speaking     = False
_speech_process = None


# ── Mood → Voice Settings ────────────────────────────────────
MOOD_VOICE_SETTINGS = {
    "focused": {
        "stability":        0.85,
        "similarity_boost": 0.75,
        "style":            0.10,
        "speed":            0.90,   # slightly slower, clear
    },
    "casual": {
        "stability":        0.60,
        "similarity_boost": 0.80,
        "style":            0.35,
        "speed":            1.00,   # normal
    },
    "sarcastic": {
        "stability":        0.45,
        "similarity_boost": 0.75,
        "style":            0.60,   # more expressive
        "speed":            1.10,   # slightly faster
    },
    "night": {
        "stability":        0.80,
        "similarity_boost": 0.70,
        "style":            0.15,
        "speed":            0.85,   # slower, chill
    },
}
# ─────────────────────────────────────────────────────────────


def _get_mood_settings() -> dict:
    """Gets current mood and returns matching voice settings."""
    try:
        from mood.mood_engine import get_current_mood
        mood = get_current_mood()
        mood_name = mood.get("name", "casual")
        return MOOD_VOICE_SETTINGS.get(mood_name, MOOD_VOICE_SETTINGS["casual"])
    except:
        return MOOD_VOICE_SETTINGS["casual"]


def _is_short_response(text: str) -> bool:
    """Check if response is short enough for instant Mac say."""
    return len(text.split()) <= SHORT_RESPONSE_WORDS


def _speak_elevenlabs(text: str) -> bool:
    """Speaks using ElevenLabs API with mood-based voice settings."""
    global is_speaking, _speech_process
    try:
        from elevenlabs import ElevenLabs, VoiceSettings, play
        import io

        client   = ElevenLabs(api_key=ELEVENLABS_API_KEY)
        settings = _get_mood_settings()

        audio = client.text_to_speech.convert(
            voice_id=VOICE_ID,
            text=text,
            model_id="eleven_turbo_v2",   # fastest model
            voice_settings=VoiceSettings(
                stability=settings["stability"],
                similarity_boost=settings["similarity_boost"],
                style=settings["style"],
                use_speaker_boost=True,
            )
        )

        # Save to temp file and play
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            tmp_path = f.name
            for chunk in audio:
                f.write(chunk)

        # Play using afplay (Mac) — non-blocking for interruption support
        _speech_process = subprocess.Popen(["afplay", tmp_path])
        interrupted = _listen_for_interrupt()

        if interrupted:
            _speech_process.terminate()
            _speech_process.wait()
            os.remove(tmp_path)
            is_speaking = False
            print("✋ Interrupted")
            return False

        _speech_process.wait()
        os.remove(tmp_path)
        return True

    except Exception as e:
        print(f"⚠️  ElevenLabs failed: {e} — falling back to Mac say")
        return _speak_mac(text)


def _speak_mac(text: str) -> bool:
    """Speaks using Mac built-in say command."""
    global _speech_process
    _speech_process = subprocess.Popen(
        ["say", "-v", MAC_VOICE, "-r", str(MAC_RATE), text]
    )
    interrupted = _listen_for_interrupt()
    if interrupted:
        _speech_process.terminate()
        _speech_process.wait()
        _speech_process = None
        return False
    _speech_process.wait()
    _speech_process = None
    return True


def _listen_for_interrupt(threshold_multiplier: float = 6.0) -> bool:
    """Listens for user interruption while Jarvis speaks."""
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

    # Wait for speaker to start — calibrate WITH Jarvis voice as background
    time.sleep(0.3)

    calibration = []
    for _ in range(CALIBRATE_CHUNKS):
        raw   = stream.read(CHUNK, exception_on_overflow=False)
        chunk = np.frombuffer(raw, dtype=np.int16)
        calibration.append(np.abs(chunk).mean())
    threshold = np.mean(calibration) * threshold_multiplier

    interrupted = False
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


def speak(text: str, force_elevenlabs: bool = False) -> bool:
    """
    Hybrid TTS — speaks text using the best engine for the response.

    Short responses (≤6 words) → Mac say (instant, <50ms)
    Long responses → ElevenLabs if available, else Mac say

    Args:
        text:              The text to speak
        force_elevenlabs:  Override to force ElevenLabs (for smart follow-ups)

    Returns:
        True if completed, False if interrupted.
    """
    global is_speaking
    is_speaking = True
    print(f"🔊 Jarvis: {text}")

    use_el = force_elevenlabs or (USE_ELEVENLABS and not _is_short_response(text))

    if use_el:
        result = _speak_elevenlabs(text)
    else:
        result = _speak_mac(text)

    is_speaking = False
    return result


def speak_instant(text: str) -> bool:
    """
    Always uses Mac say for instant response.
    Used for quick acks like "Got it", "On it".
    """
    global is_speaking
    is_speaking = True
    print(f"🔊 Jarvis (instant): {text}")
    result = _speak_mac(text)
    is_speaking = False
    return result


def speak_smart(text: str) -> bool:
    """
    Uses ElevenLabs if available, for richer/longer responses.
    Falls back to Mac say if ElevenLabs unavailable.
    """
    global is_speaking
    is_speaking = True
    print(f"🔊 Jarvis (smart): {text}")

    if USE_ELEVENLABS:
        result = _speak_elevenlabs(text)
    else:
        result = _speak_mac(text)

    is_speaking = False
    return result


def speak_and_wait(text: str) -> None:
    """Always completes — not interruptible. For warnings."""
    global is_speaking
    is_speaking = True
    print(f"🔊 Jarvis: {text}")

    if USE_ELEVENLABS:
        try:
            from elevenlabs import ElevenLabs, VoiceSettings
            client   = ElevenLabs(api_key=ELEVENLABS_API_KEY)
            settings = _get_mood_settings()
            audio    = client.text_to_speech.convert(
                voice_id=VOICE_ID,
                text=text,
                model_id="eleven_turbo_v2",
                voice_settings=VoiceSettings(
                    stability=settings["stability"],
                    similarity_boost=settings["similarity_boost"],
                    style=settings["style"],
                )
            )
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                tmp_path = f.name
                for chunk in audio:
                    f.write(chunk)
            subprocess.run(["afplay", tmp_path])
            os.remove(tmp_path)
        except Exception as e:
            print(f"⚠️  ElevenLabs failed: {e}")
            subprocess.run(["say", "-v", MAC_VOICE, "-r", str(MAC_RATE), text])
    else:
        subprocess.run(["say", "-v", MAC_VOICE, "-r", str(MAC_RATE), text])

    is_speaking = False


# ─── Quick test ──────────────────────────────────────────────
if __name__ == "__main__":
    print(f"Using ElevenLabs: {USE_ELEVENLABS}")
    print("Testing hybrid voice...\n")

    from mood.mood_engine import set_mood

    set_mood("casual")

    # Short response — should use Mac say (instant)
    speak("Got it.")
    time.sleep(0.5)

    # Longer response — would use ElevenLabs if available
    speak("Here's your morning briefing. You have 3 unread emails and a meeting at 2 PM.")
    time.sleep(0.5)

    # Force instant
    speak_instant("On it.")