import subprocess
import os
from core.voice_response import speak
from core.llm_brain import set_context


def open_folder(folder_name: str) -> None:
    """Opens a common folder in Explorer."""
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
    subprocess.Popen(["explorer", path])


def search_file(filename: str) -> None:
    """
    Searches for files using os.walk on common directories.
    Lists results and asks user which one to open.
    Reads contents if text file.
    """
    speak(f"Searching for {filename}.")
    print(f"🔍 Searching for: {filename}")

    # Search common directories (Windows equivalent of Spotlight/mdfind)
    search_dirs = [
        os.path.expanduser("~/Desktop"),
        os.path.expanduser("~/Documents"),
        os.path.expanduser("~/Downloads"),
    ]
    files = []
    for search_dir in search_dirs:
        if not os.path.exists(search_dir):
            continue
        for root, dirs, dir_files in os.walk(search_dir):
            # Skip junk directories
            dirs[:] = [d for d in dirs if d not in (
                "venv", ".venv", ".git", "node_modules",
                "__pycache__", ".cache", "Application Support",
                ".Trash"
            )]
            for f in dir_files:
                if filename.lower() in f.lower():
                    full_path = os.path.join(root, f)
                    files.append(full_path)

    if not files:
        speak(f"Couldn't find any file named {filename}.")
        return

    # Only one result
    if len(files) == 1:
        path     = files[0]
        name     = os.path.basename(path)
        location = os.path.dirname(path).replace(os.path.expanduser("~"), "home")
        speak(f"Found one file: {name} in {location}.")
        _open_or_read(path)
        return

    # Multiple results — list them
    shown = files[:5]
    speak(f"I found {len(shown)} files.")

    for i, f in enumerate(shown, 1):
        name     = os.path.basename(f)
        location = os.path.dirname(f).replace(os.path.expanduser("~"), "home")
        speak(f"File {i}: {name}.")
        print(f"  {i}. {name} — {f}")

    speak("Which one do you want? Say the number.")

    # Listen for choice — direct mic input, no Gemini
    from core.speech_to_text import listen
    choice = listen()
    print(f"📝 Choice heard: '{choice}'")

    # Extract number
    number = _extract_number(choice)

    if number and 1 <= number <= len(shown):
        _open_or_read(shown[number - 1])
    else:
        speak("Didn't catch that. Try again.")
        choice2 = listen()
        number2 = _extract_number(choice2)
        if number2 and 1 <= number2 <= len(shown):
            _open_or_read(shown[number2 - 1])
        else:
            speak("No worries, try searching again.")


def _open_or_read(path: str) -> None:
    """Opens a file. If text file, offers to read contents."""
    name = os.path.basename(path)
    TEXT_EXTENSIONS = (".txt", ".py", ".md", ".js", ".json",
                       ".csv", ".html", ".css", ".yaml", ".env")

    if path.endswith(TEXT_EXTENSIONS):
        speak(f"Want me to read {name} or just open it? Say read or open.")
        from core.speech_to_text import listen
        answer = listen()
        print(f"📝 Answer: '{answer}'")

        if "read" in answer.lower():
            _read_contents(path)
        else:
            os.startfile(path)
            speak(f"Opening {name}.")
    else:
        # Non-text file (PDF, docx etc) — just open
        os.startfile(path)
        speak(f"Opening {name}.")
        print(f"📂 Opened: {path}")


def _read_contents(path: str) -> None:
    """Reads text file contents aloud."""
    try:
        with open(path, "r", errors="ignore") as f:
            content = f.read().strip()

        if not content:
            speak("The file is empty.")
            return

        # Truncate if too long
        if len(content) > 800:
            speak("File is long — reading first part.")
            content = content[:800]

        speak(content)
        print(f"📄 Read: {path}")

    except Exception as e:
        speak("Couldn't read that file.")
        print(f"❌ Error: {e}")


def _extract_number(text: str) -> int:
    word_map = {
        "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
        "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5,
        "1": 1, "2": 2, "3": 3, "4": 4, "5": 5,
    }
    # Take LAST number — "number 4 I want number 3" → returns 3
    last_found = None
    for word in text.lower().split():
        word = word.strip(".,!?")
        if word in word_map:
            last_found = word_map[word]
    return last_found


def show_recent_files() -> None:
    """Shows recently modified files."""
    speak("Finding recent files.")
    search_dirs = [
        os.path.expanduser("~/Desktop"),
        os.path.expanduser("~/Documents"),
        os.path.expanduser("~/Downloads"),
    ]
    all_files = []
    for search_dir in search_dirs:
        if not os.path.exists(search_dir):
            continue
        for root, dirs, dir_files in os.walk(search_dir):
            dirs[:] = [d for d in dirs if d not in (
                "venv", ".venv", ".git", "node_modules", "__pycache__", ".cache"
            )]
            for f in dir_files:
                if not f.endswith(".pyc"):
                    all_files.append(os.path.join(root, f))

    all_files = sorted(
        all_files,
        key=lambda f: os.path.getmtime(f) if os.path.exists(f) else 0,
        reverse=True
    )
    if not all_files:
        speak("No recent files found.")
        return
    speak(f"Your {min(5, len(all_files))} most recent files:")
    for f in all_files[:5]:
        speak(os.path.basename(f))
        print(f"📄 {os.path.basename(f)} — {f}")


# ─── Quick test ──────────────────────────────────────────────
if __name__ == "__main__":
    search_file("resume")