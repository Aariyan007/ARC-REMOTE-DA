import subprocess
import time

# ─── Voice Settings ──────────────────────────────────────────
VOICE = "Daniel"
RATE = 200
# ─────────────────────────────────────────────────────────────

# Global flag — True while Jarvis is speaking
# speech_to_text.py watches this to mute the mic
is_speaking = False


def speak(text: str):
    """
    Speaks text out loud. Blocks until finished.
    Sets is_speaking = True so mic ignores audio during speech.
    """
    global is_speaking
    is_speaking = True
    print(f"🔊 Jarvis: {text}")
    subprocess.run(["say", "-v", VOICE, "-r", str(RATE), text])
    time.sleep(0.3)    # small buffer to clear echo/reverb
    is_speaking = False


def speak_and_wait(text: str):
    """Alias for speak() — both block until finished now."""
    speak(text)


# ─── Quick test ──────────────────────────────────────────────
if __name__ == "__main__":
    speak("Hello. I am Jarvis. Your personal assistant is now online.")
    speak("Opening Safari.")
    speak("Searching Google for python tutorial.")
    speak("It's 1:05 AM.")
    speak("Locking the screen.")
    speak("Shutting down in 5 seconds.")
    print("✅ Voice test complete!")