import subprocess
import os
from core.voice_response import speak

def open_vscode():
    subprocess.Popen(["code"], shell=True)

def open_safari():
    # Windows doesn't have Safari — open default browser
    import webbrowser
    webbrowser.open("https://google.com")

def open_terminal():
    subprocess.Popen(["cmd.exe"])

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