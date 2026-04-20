"""
Voice Response — Mac `say` only TTS system.

All speech uses Mac `say` for now. Zero network latency, zero API cost.
ElevenLabs will be re-added as final polish after the core pipeline works.

Three delivery modes:
    speak_ack(text)    — Fast rate Mac say, for short acks (<100ms)
    speak_result(text) — Normal rate Mac say, for results (<200ms)
    speak_chat(text)   — Normal rate Mac say, for chat/answers (<300ms)
"""

import subprocess
import sys
import os
import time
import numpy as np

# ─── Settings ────────────────────────────────────────────────
# ElevenLabs disabled for now — all speech via Mac say
USE_ELEVENLABS = False

# Mac voice settings
MAC_VOICE      = "Daniel"
MAC_RATE_ACK   = 230   # Faster for snappy acks
MAC_RATE_NORMAL = 200   # Normal for results and chat
# ─────────────────────────────────────────────────────────────

is_speaking     = False
_speech_process = None


def _speak_mac(text: str, rate: int = MAC_RATE_NORMAL) -> bool:
    """Speaks using Mac built-in say command."""
    global _speech_process, is_speaking
    if sys.platform != "darwin":
        return _speak_fallback(text)

    _speech_process = subprocess.Popen(
        ["say", "-v", MAC_VOICE, "-r", str(rate), text]
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


def _speak_fallback(text: str) -> bool:
    """Fallback TTS for non-Mac platforms."""
    global is_speaking
    try:
        import pyttsx3
        engine = pyttsx3.init()
        voices = engine.getProperty('voices')
        for voice in voices:
            if 'david' in voice.name.lower() or 'mark' in voice.name.lower():
                engine.setProperty('voice', voice.id)
                break
        engine.setProperty('rate', 180)
        engine.say(text)
        engine.runAndWait()
        return True
    except Exception as e:
        print(f"❌ TTS error: {e}")
        return True  # Don't block on TTS failure


def _listen_for_interrupt(threshold_multiplier: float = 12.0) -> bool:
    """Listens for user interruption while Jarvis speaks."""
    try:
        import pyaudio
    except ImportError:
        # No pyaudio — just wait for process to finish
        if _speech_process:
            _speech_process.wait()
        return False

    CHUNK            = 1024
    SAMPLE_RATE      = 16000
    CALIBRATE_CHUNKS = 20

    audio  = pyaudio.PyAudio()
    stream = audio.open(
        format=pyaudio.paInt16,
        channels=1,
        rate=SAMPLE_RATE,
        input=True,
        frames_per_buffer=CHUNK
    )

    # Wait for speaker to start — calibrate WITH Jarvis voice as background
    time.sleep(0.4)

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


# ═══════════════════════════════════════════════════════════════
#  The 3 delivery modes
# ═══════════════════════════════════════════════════════════════

def speak_ack(text: str) -> bool:
    """
    Quick ack — fast rate Mac say. For "On it.", "Renaming." etc.
    Target: <100ms perceived latency.
    """
    global is_speaking
    if not text:
        return True  # Empty ack = skip
    is_speaking = True
    print(f"🔊 Jarvis (ack): {text}")
    result = _speak_mac(text, rate=MAC_RATE_ACK)
    is_speaking = False
    return result


def speak_result(text: str) -> bool:
    """
    Result delivery — normal rate Mac say. For "Chrome's open.", "Renamed X to Y."
    Target: <200ms perceived latency.
    """
    global is_speaking
    if not text:
        return True
    is_speaking = True
    print(f"🔊 Jarvis: {text}")
    result = _speak_mac(text, rate=MAC_RATE_NORMAL)
    is_speaking = False
    return result


def speak_chat(text: str) -> bool:
    """
    Chat/answer delivery — normal rate Mac say. For personality and answers.
    Target: <300ms perceived latency.
    """
    global is_speaking
    if not text:
        return True
    is_speaking = True
    print(f"🔊 Jarvis: {text}")
    result = _speak_mac(text, rate=MAC_RATE_NORMAL)
    is_speaking = False
    return result


def speak_and_wait(text: str) -> None:
    """Always completes — not interruptible. For warnings/confirmations."""
    global is_speaking
    is_speaking = True
    print(f"🔊 Jarvis: {text}")
    if sys.platform == "darwin":
        subprocess.run(["say", "-v", MAC_VOICE, "-r", str(MAC_RATE_NORMAL), text])
    else:
        _speak_fallback(text)
    is_speaking = False


# ═══════════════════════════════════════════════════════════════
#  Backward-compat aliases (old code still calls these)
# ═══════════════════════════════════════════════════════════════

def speak(text: str, force_elevenlabs: bool = False) -> bool:
    """Alias → speak_result. Kept for backward compatibility."""
    return speak_result(text)


def speak_instant(text: str) -> bool:
    """Alias → speak_ack. Kept for backward compatibility."""
    return speak_ack(text)


def speak_smart(text: str) -> bool:
    """Alias → speak_chat. Kept for backward compatibility."""
    return speak_chat(text)


# ─── Quick test ──────────────────────────────────────────────
if __name__ == "__main__":
    print(f"Platform: {sys.platform}")
    print(f"ElevenLabs: {USE_ELEVENLABS}")
    print("Testing Mac say only voice...\n")

    speak_ack("On it.")
    time.sleep(0.3)

    speak_result("Chrome is open.")
    time.sleep(0.3)

    speak_chat("You have 3 unread emails and a meeting at 2 PM.")
    time.sleep(0.3)

    # Test aliases
    speak("Testing backward compat.")
    speak_instant("Got it.")