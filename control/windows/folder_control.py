import subprocess
import os
from core.voice_response import speak

def open_folder(folder_name: str) -> None:
    folder_map = {
        "downloads":  os.path.expanduser("~/Downloads"),
        "desktop":    os.path.expanduser("~/Desktop"),
        "documents":  os.path.expanduser("~/Documents"),
        "pictures":   os.path.expanduser("~/Pictures"),
        "music":      os.path.expanduser("~/Music"),
    }
    path = folder_map.get(folder_name.lower())
    if not path:
        for key, val in folder_map.items():
            if key in folder_name.lower():
                path = val
                break
    if path and os.path.exists(path):
        speak(f"Opening {folder_name}.")
        subprocess.Popen(["explorer", path])
    else:
        speak(f"Couldn't find {folder_name}.")

def create_folder(folder_name: str, location: str = "desktop") -> None:
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
    speak(f"Created folder {folder_name}.")
    subprocess.Popen(["explorer", path])
    print(f"📁 Created: {path}")

def search_file(filename: str) -> None:
    speak(f"Searching for {filename}.")
    subprocess.Popen(["explorer", f"search-ms:query={filename}&crumb=location:C%3A%5C"])
    print(f"🔍 Searching: {filename}")