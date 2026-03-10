import subprocess
import time
from core.voice_response import speak_and_wait

def lock_screen():
    speak_and_wait("Locking the screen")
    """Locks the Mac screen immediately."""
    print("🔒 Locking screen...")
    subprocess.Popen([
        "osascript", "-e",
        'tell application "System Events" to keystroke "q" using {command down, control down}'
    ])


def shutdown_pc():
    speak_and_wait("Shutting down in 5 seconds")
    """
    Shuts down the Mac after a 5 second warning.
    Gives time to cancel if Whisper misheard.
    """
    print("⚠️  Shutting down in 5 seconds... (Ctrl+C to cancel)")
    try:
        for i in range(5, 0, -1):
            print(f"   {i}...")
            time.sleep(1)
        print("🔴 Shutting down now.")
        subprocess.Popen(["osascript", "-e", 'tell app "System Events" to shut down'])
    except KeyboardInterrupt:
        print("✅ Shutdown cancelled.")


def restart_pc():
    speak_and_wait("Restarting in 5 seconds")
    """
    Restarts the Mac after a 5 second warning.
    Gives time to cancel if Whisper misheard.
    """
    print("⚠️  Restarting in 5 seconds... (Ctrl+C to cancel)")
    try:
        for i in range(5, 0, -1):
            print(f"   {i}...")
            time.sleep(1)
        print("🔄 Restarting now.")
        subprocess.Popen(["osascript", "-e", 'tell app "System Events" to restart'])
    except KeyboardInterrupt:
        print("✅ Restart cancelled.")


# ─── Quick test ──────────────────────────────────────────────
# Run: python3 control/system_actions.py
if __name__ == "__main__":
    print("Testing lock_screen only (safe test)...")
    print("Your screen will lock in 3 seconds.")
    time.sleep(3)
    lock_screen()