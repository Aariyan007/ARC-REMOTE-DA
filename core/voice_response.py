import subprocess


# ─── Voice Settings ──────────────────────────────────────────
# Mac built-in voices — change VOICE to try different ones:
# "Alex" "Samantha" "Daniel" "Karen" "Moira" "Siri"
VOICE = "Daniel"
RATE = 200    # Words per minute — default is 175, higher = faster
# ─────────────────────────────────────────────────────────────


def speak(text: str):
    """
    Speaks text out loud using Mac's built-in voice.
    Non-blocking — Jarvis keeps running while speaking.

    Example:
        speak("Opening Safari")
        → Jarvis says "Opening Safari" out loud
    """
    print(f"🔊 Jarvis: {text}")
    subprocess.Popen(["say", "-v", VOICE, "-r", str(RATE), text])


def speak_and_wait(text: str):
    """
    Speaks text and waits until finished before continuing.
    Use this for important messages like shutdown warnings.

    Example:
        speak_and_wait("Shutting down in 5 seconds")
        → Jarvis finishes speaking before countdown starts
    """
    print(f"🔊 Jarvis: {text}")
    subprocess.run(["say", "-v", VOICE, "-r", str(RATE), text])


# ─── Quick test ──────────────────────────────────────────────
if __name__ == "__main__":
    print("Testing voice responses...\n")

    speak_and_wait("Hello. I am Jarvis. Your personal assistant is now online.")
    speak_and_wait("Opening Safari.")
    speak_and_wait("Searching Google for python tutorial.")
    speak_and_wait("It's 1:05 AM.")
    speak_and_wait("Locking the screen.")
    speak_and_wait("Shutting down in 5 seconds.")

    print("\n✅ Voice test complete!")