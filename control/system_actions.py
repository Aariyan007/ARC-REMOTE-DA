import subprocess
import time

def lock_screen():
    subprocess.Popen([
        "osascript", "-e",
        'tell application "System Events" to keystroke "q" using {command down, control down}'
    ])

def shutdown_pc():
    print("⚠️  Shutting down in 5 seconds...")
    try:
        for i in range(5, 0, -1):
            print(f"   {i}...")
            time.sleep(1)
        subprocess.Popen(["osascript", "-e", 'tell app "System Events" to shut down'])
    except KeyboardInterrupt:
        print("✅ Cancelled.")

def restart_pc():
    print("⚠️  Restarting in 5 seconds...")
    try:
        for i in range(5, 0, -1):
            print(f"   {i}...")
            time.sleep(1)
        subprocess.Popen(["osascript", "-e", 'tell app "System Events" to restart'])
    except KeyboardInterrupt:
        print("✅ Cancelled.")

def sleep_mac():
    subprocess.Popen([
        "osascript", "-e",
        'tell application "System Events" to sleep'
    ])