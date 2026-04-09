import subprocess
import time
from core.voice_response import speak, speak_and_wait

def lock_screen():
    import ctypes
    ctypes.windll.user32.LockWorkStation()

def shutdown_pc():
    speak_and_wait("Shutting down in 5 seconds. Press Control C to cancel.")
    try:
        for i in range(5, 0, -1):
            print(f"   {i}...")
            time.sleep(1)
        subprocess.Popen(["shutdown", "/s", "/t", "0"])
    except KeyboardInterrupt:
        speak("Shutdown cancelled.")

def restart_pc():
    speak_and_wait("Restarting in 5 seconds. Press Control C to cancel.")
    try:
        for i in range(5, 0, -1):
            print(f"   {i}...")
            time.sleep(1)
        subprocess.Popen(["shutdown", "/r", "/t", "0"])
    except KeyboardInterrupt:
        speak("Restart cancelled.")

def sleep_mac():
    # Works on Windows too
    subprocess.Popen(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"])