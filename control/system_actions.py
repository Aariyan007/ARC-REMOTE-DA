import subprocess
import time
from core.voice_response import speak, speak_and_wait


def lock_screen():
    """Locks the Mac screen immediately."""
    speak("Locking the screen")
    print("🔒 Locking screen...")
    subprocess.Popen([
        "osascript", "-e",
        'tell application "System Events" to keystroke "q" using {command down, control down}'
    ])


def shutdown_pc():
    """Shuts down the Mac after a 5 second warning."""
    speak_and_wait("Shutting down in 5 seconds. Press Control C to cancel.")
    print("⚠️  Shutting down in 5 seconds... (Ctrl+C to cancel)")
    try:
        for i in range(5, 0, -1):
            print(f"   {i}...")
            time.sleep(1)
        print("🔴 Shutting down now.")
        subprocess.Popen(["osascript", "-e", 'tell app "System Events" to shut down'])
    except KeyboardInterrupt:
        speak("Shutdown cancelled.")
        print("✅ Shutdown cancelled.")


def restart_pc():
    """Restarts the Mac after a 5 second warning."""
    speak_and_wait("Restarting in 5 seconds. Press Control C to cancel.")
    print("⚠️  Restarting in 5 seconds... (Ctrl+C to cancel)")
    try:
        for i in range(5, 0, -1):
            print(f"   {i}...")
            time.sleep(1)
        print("🔄 Restarting now.")
        subprocess.Popen(["osascript", "-e", 'tell app "System Events" to restart'])
    except KeyboardInterrupt:
        speak("Restart cancelled.")
        print("✅ Restart cancelled.")


def sleep_mac():
    """Puts the Mac to sleep."""
    speak_and_wait("Putting your Mac to sleep. Goodnight.")
    subprocess.Popen([
        "osascript", "-e",
        'tell application "System Events" to sleep'
    ])


# ─── Quick test ──────────────────────────────────────────────
if __name__ == "__main__":
    print("Testing lock_screen only (safe test)...")
    print("Your screen will lock in 3 seconds.")
    time.sleep(3)
    lock_screen()