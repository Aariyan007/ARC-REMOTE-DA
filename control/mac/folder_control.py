import subprocess
import os
from core.voice_response import speak


def open_folder(folder_name: str) -> None:
    """Opens a common folder in Finder."""
    folder_map = {
        "downloads":  os.path.expanduser("~/Downloads"),
        "desktop":    os.path.expanduser("~/Desktop"),
        "documents":  os.path.expanduser("~/Documents"),
        "projects":   os.path.expanduser("~/Desktop/BackEnd"),
        "startup":    os.path.expanduser("~/Desktop/BackEnd/Startup"),
        "home":       os.path.expanduser("~"),
        "music":      os.path.expanduser("~/Music"),
        "pictures":   os.path.expanduser("~/Pictures"),
    }

    # Try exact match first
    path = folder_map.get(folder_name.lower())

    # Try partial match
    if not path:
        for key, val in folder_map.items():
            if key in folder_name.lower():
                path = val
                break

    if path and os.path.exists(path):
        speak(f"Opening {folder_name}.")
        subprocess.Popen(["open", path])
    else:
        # Try Spotlight search
        speak(f"Searching for {folder_name}.")
        subprocess.Popen(["open", "-a", "Finder"])


def create_folder(folder_name: str, location: str = "desktop") -> None:
    """Creates a new folder at specified location."""
    location_map = {
        "desktop":   os.path.expanduser("~/Desktop"),
        "downloads": os.path.expanduser("~/Downloads"),
        "documents": os.path.expanduser("~/Documents"),
    }

    base = location_map.get(location.lower(), os.path.expanduser("~/Desktop"))
    path = os.path.join(base, folder_name)

    if os.path.exists(path):
        speak(f"Folder {folder_name} already exists.")
        return

    os.makedirs(path)
    speak(f"Created folder {folder_name} on your {location}.")
    print(f"📁 Created: {path}")
    subprocess.Popen(["open", path])


def search_file(filename: str) -> None:
    """Searches for a file using Spotlight."""
    speak(f"Searching for {filename}.")
    print(f"🔍 Searching for: {filename}")
    # Open Spotlight search
    script = f'tell application "Finder" to activate'
    subprocess.Popen(["osascript", "-e", script])
    subprocess.Popen([
        "mdfind", "-name", filename
    ], stdout=subprocess.PIPE)

    # Show results via Spotlight UI
    subprocess.Popen([
        "open", f"spotlight:{filename}"
    ])


def show_recent_files() -> None:
    """Shows recently opened files."""
    speak("Opening recent files.")
    subprocess.Popen([
        "osascript", "-e",
        'tell application "Finder" to open folder "Recents" of computer'
    ])


# ─── Quick test ──────────────────────────────────────────────
if __name__ == "__main__":
    print("Testing folder control...")
    open_folder("downloads")