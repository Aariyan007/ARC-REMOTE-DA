import subprocess
from core.voice_response import speak

def open_vscode():
    subprocess.Popen(["open", "-a", "Visual Studio Code"])

def open_safari():
    subprocess.Popen(["open", "-a", "Safari"])

def open_terminal():
    subprocess.Popen(["open", "-a", "Terminal"])
    
def open_settings():
    subprocess.Popen(["open", "-a", "System Preferences"])
    
def open_any_app(app_name: str) -> None:
    """Opens any app by name — Mac finds it automatically."""
    import subprocess
    # Try exact name first
    result = subprocess.run(
        ["open", "-a", app_name],
        capture_output=True
    )
    if result.returncode != 0:
        # Try with title case
        result = subprocess.run(
            ["open", "-a", app_name.title()],
            capture_output=True
        )
    if result.returncode != 0:
        print(f"❌ Couldn't find app: {app_name}")
        speak(f"Couldn't find {app_name} on your Mac.")
    else:
        print(f"✅ Opened: {app_name}")