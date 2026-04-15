import subprocess
import shutil
import os
from core.voice_response import speak


# ─── Hard-coded terminal openers (Issue 3 fix) ──────────────

def open_cmd():
    """Opens Windows Command Prompt."""
    try:
        subprocess.Popen(["cmd"])
        print("✅ Opened: Command Prompt")
    except Exception as e:
        print(f"❌ Failed to open CMD: {e}")
        speak("Couldn't open Command Prompt.")


def open_powershell():
    """Opens PowerShell — prefers pwsh (PowerShell 7) if installed."""
    try:
        if shutil.which("pwsh"):
            subprocess.Popen(["pwsh"])
            print("✅ Opened: PowerShell 7 (pwsh)")
        else:
            subprocess.Popen(["powershell"])
            print("✅ Opened: Windows PowerShell")
    except Exception as e:
        print(f"❌ Failed to open PowerShell: {e}")
        speak("Couldn't open PowerShell.")


def open_windows_terminal():
    """Opens Windows Terminal (wt)."""
    try:
        subprocess.Popen(["wt"])
        print("✅ Opened: Windows Terminal")
    except FileNotFoundError:
        # Windows Terminal not installed — fall back to CMD
        print("⚠️  Windows Terminal not found, opening CMD instead")
        speak("Windows Terminal isn't installed. Opening Command Prompt.")
        open_cmd()
    except Exception as e:
        print(f"❌ Failed to open Windows Terminal: {e}")
        speak("Couldn't open Windows Terminal.")


# ─── Standard app openers ────────────────────────────────────

def open_vscode():
    subprocess.Popen(["code"], shell=True)

def open_safari():
    # Windows doesn't have Safari — open default browser
    import webbrowser
    webbrowser.open("https://google.com")

def open_terminal():
    """Default 'open terminal' on Windows → opens CMD."""
    open_cmd()

def open_settings():
    subprocess.Popen(["start", "ms-settings:"], shell=True)

def open_chrome():
    subprocess.Popen(["start", "chrome"], shell=True)

def open_browser():
    import webbrowser
    webbrowser.open("https://google.com")

def open_notepad():
    subprocess.Popen(["notepad.exe"])

def open_explorer():
    subprocess.Popen(["explorer.exe"])

def open_any_app(app_name: str) -> None:
    """Opens any app by name — Windows finds it via Start menu / PATH."""
    import subprocess
    # Common app name → executable mapping
    app_map = {
        "vscode": "code",
        "visual studio code": "code",
        "chrome": "chrome",
        "google chrome": "chrome",
        "firefox": "firefox",
        "edge": "msedge",
        "microsoft edge": "msedge",
        "notepad": "notepad",
        "calculator": "calc",
        "paint": "mspaint",
        "word": "winword",
        "excel": "excel",
        "powerpoint": "powerpnt",
        "outlook": "outlook",
        "teams": "msteams",
        "spotify": "spotify",
        "discord": "discord",
        "slack": "slack",
        "terminal": "cmd",
        "command prompt": "cmd",
        "cmd": "cmd",
        "powershell": "powershell",
        "file explorer": "explorer",
        "explorer": "explorer",
        "task manager": "taskmgr",
        "settings": "ms-settings:",
    }

    exe = app_map.get(app_name.lower(), app_name)

    # Try opening via start command (works for most apps)
    result = subprocess.run(
        ["start", "", exe],
        capture_output=True, shell=True
    )
    if result.returncode != 0:
        # Try with title case
        result = subprocess.run(
            ["start", "", app_name.title()],
            capture_output=True, shell=True
        )
    if result.returncode != 0:
        print(f"❌ Couldn't find app: {app_name}")
        speak(f"Couldn't find {app_name} on your PC.")
    else:
        print(f"✅ Opened: {app_name}")