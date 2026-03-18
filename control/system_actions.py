import subprocess
import time
from core.responder import generate_response
from core.voice_response import speak, speak_and_wait


def lock_screen(user_said: str = "lock screen"):
    response = generate_response("lock_screen", user_said)
    speak(response)
    subprocess.Popen([
        "osascript", "-e",
        'tell application "System Events" to keystroke "q" using {command down, control down}'
    ])


def shutdown_pc(user_said: str = "shutdown"):
    response = generate_response("shutdown_pc", user_said)
    speak_and_wait(response)
    try:
        for i in range(5, 0, -1):
            print(f"   {i}...")
            time.sleep(1)
        subprocess.Popen(["osascript", "-e", 'tell app "System Events" to shut down'])
    except KeyboardInterrupt:
        speak("Shutdown cancelled.")


def restart_pc(user_said: str = "restart"):
    response = generate_response("restart_pc", user_said)
    speak_and_wait(response)
    try:
        for i in range(5, 0, -1):
            print(f"   {i}...")
            time.sleep(1)
        subprocess.Popen(["osascript", "-e", 'tell app "System Events" to restart'])
    except KeyboardInterrupt:
        speak("Restart cancelled.")


def sleep_mac(user_said: str = "sleep mac"):
    response = generate_response("sleep_mac", user_said)
    speak_and_wait(response)
    subprocess.Popen([
        "osascript", "-e",
        'tell application "System Events" to sleep'
    ])