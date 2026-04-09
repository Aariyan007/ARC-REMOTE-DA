import os
import subprocess
from core.voice_response import speak


# ─── Volume ──────────────────────────────────────────────────

def volume_up(amount: int = 10) -> None:
    speak(f"Turning up by {amount}.")
    os.system(f"osascript -e 'set volume output volume (output volume of (get volume settings) + {amount})'")

def volume_down(amount: int = 10) -> None:
    speak(f"Turning down by {amount}.")
    os.system(f"osascript -e 'set volume output volume (output volume of (get volume settings) - {amount})'")

def mute() -> None:
    """Mutes the Mac."""
    os.system("osascript -e 'set volume with output muted'")


def unmute() -> None:
    """Unmutes the Mac."""
    os.system("osascript -e 'set volume without output muted'")


def get_volume() -> None:
    """Tells current volume level."""
    result = subprocess.run(
        ["osascript", "-e", "output volume of (get volume settings)"],
        capture_output=True, text=True
    )
    vol = result.stdout.strip()
    speak(f"Volume is at {vol} percent.")
    print(f"🔊 Volume: {vol}%")


# ─── Brightness ──────────────────────────────────────────────

def brightness_up() -> None:
    """Increases brightness."""
    # Uses keyboard shortcut
    os.system("""osascript -e 'tell application "System Events" to key code 144'""")


def brightness_down() -> None:
    """Decreases brightness."""
    os.system("""osascript -e 'tell application "System Events" to key code 145'""")


# ─── Screenshot ──────────────────────────────────────────────

def take_screenshot() -> None:
    """Takes a screenshot and saves to Desktop."""
    import datetime
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path      = os.path.expanduser(f"~/Desktop/screenshot_{timestamp}.png")
    os.system(f"screencapture '{path}'")
    print(f"📸 Saved: {path}")


# ─── Window Management ───────────────────────────────────────

def minimise_all() -> None:
    """Minimises all windows."""
    os.system("osascript -e 'tell application \"System Events\" to keystroke \"m\" using {command down, option down}'")


def show_desktop() -> None:
    """Shows the desktop."""
    os.system("osascript -e 'tell application \"System Events\" to key code 103 using {command down}'")


def switch_app() -> None:
    """Opens app switcher."""
    os.system("osascript -e 'tell application \"System Events\" to keystroke tab using command down'")


def close_window() -> None:
    """Closes current window."""
    os.system("osascript -e 'tell application \"System Events\" to keystroke \"w\" using command down'")


def new_tab() -> None:
    """Opens new tab in current app."""
    os.system("osascript -e 'tell application \"System Events\" to keystroke \"t\" using command down'")


def close_tab() -> None:
    """Closes current tab."""
    os.system("osascript -e 'tell application \"System Events\" to keystroke \"w\" using command down'")


# ─── Do Not Disturb ──────────────────────────────────────────

def do_not_disturb_on() -> None:
    """Enables Do Not Disturb via Focus mode."""
    os.system("osascript -e 'tell application \"System Events\" to tell process \"Control Center\" to click menu bar item \"Focus\" of menu bar 1'")


# ─── Battery ─────────────────────────────────────────────────

def get_battery() -> None:
    """Tells current battery level."""
    result = subprocess.run(
        ["pmset", "-g", "batt"],
        capture_output=True, text=True
    )
    output = result.stdout
    # Extract percentage
    import re
    match = re.search(r'(\d+)%', output)
    if match:
        percent = match.group(1)
        charging = "charging" if "AC Power" in output else "on battery"
        speak(f"Battery is at {percent} percent and {charging}.")
        print(f"🔋 Battery: {percent}% ({charging})")
    else:
        speak("Couldn't read battery level.")


# ─── Smart Sequences ─────────────────────────────────────────

def start_work_day() -> None:
    """Opens your work setup."""
    speak("Starting your work day. Let's get it.")
    # Open your usual apps
    subprocess.Popen(["open", "-a", "Visual Studio Code"])
    subprocess.Popen(["open", "-a", "Terminal"])
    subprocess.Popen(["open", "-a", "Safari"])
    print("🚀 Work day started")
    
def minimise_app(app_name: str) -> None:
    """Minimises a specific app."""
    app_map = {
        "safari":   "Safari",
        "vscode":   "Visual Studio Code",
        "terminal": "Terminal",
        "chrome":   "Google Chrome",
        "finder":   "Finder",
    }
    app = app_map.get(app_name.lower(), app_name)

    # VS Code doesn't support AppleScript miniaturize
    # Use keyboard shortcut instead
    if app_name.lower() == "vscode":
        os.system("""osascript -e '
            tell application "System Events"
                tell process "Code"
                    set value of attribute "AXMinimized" of window 1 to true
                end tell
            end tell
        '""")
    else:
        os.system(f"""osascript -e 'tell application "{app}" to set miniaturized of windows to true'""")
    print(f"🔽 Minimised: {app}")

def close_app(app_name: str) -> None:
    """Fully closes/quits an app."""
    app_map = {
        "safari":   "Safari",
        "vscode":   "Visual Studio Code",
        "terminal": "Terminal",
        "chrome":   "Google Chrome",
        "finder":   "Finder",
        "mail":     "Mail",
    }
    app = app_map.get(app_name.lower(), app_name.title())
    os.system(f"""osascript -e 'tell application "{app}" to quit'""")
    print(f"❌ Closed: {app}")


def switch_to_app(app_name: str) -> None:
    """Brings an app to the front."""
    app_map = {
        "safari":   "Safari",
        "vscode":   "Visual Studio Code",
        "terminal": "Terminal",
        "chrome":   "Google Chrome",
        "finder":   "Finder",
    }
    app = app_map.get(app_name.lower(), app_name.title())
    os.system(f"""osascript -e 'tell application "{app}" to activate'""")
    print(f"🔄 Switched to: {app}")


def fullscreen() -> None:
    """Makes current window fullscreen."""
    os.system("""osascript -e 'tell application "System Events" to keystroke "f" using {command down, control down}'""")
    print("⛶ Fullscreen toggled")


def mission_control() -> None:
    """Shows all open windows."""
    os.system("""osascript -e 'tell application "System Events" to key code 160'""")
    print("🪟 Mission Control opened")

def end_work_day() -> None:
    """Closes everything and locks screen."""
    speak("Ending your work day. Good work today.")
    import time
    time.sleep(2)
    # Lock screen
    subprocess.Popen([
        "osascript", "-e",
        'tell application "System Events" to keystroke "q" using {command down, control down}'
    ])


# ─── Quick test ──────────────────────────────────────────────
if __name__ == "__main__":
    print("Testing system controls...")
    get_volume()
    get_battery()
    take_screenshot()