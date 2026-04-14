import os
import subprocess
import shutil
from datetime import datetime
from core.voice_response import speak

# ─── Common locations ────────────────────────────────────────
LOCATIONS = {
    "desktop":   os.path.expanduser("~/Desktop"),
    "downloads": os.path.expanduser("~/Downloads"),
    "documents": os.path.expanduser("~/Documents"),
    "projects":  os.path.expanduser("~/Desktop/BackEnd"),
    "startup":   os.path.expanduser("~/Desktop/BackEnd/Startup"),
    "home":      os.path.expanduser("~"),
}
# ─────────────────────────────────────────────────────────────


def _find_file(name: str, location: str = None) -> str:
    """
    Finds a file by name.
    If location given → searches there first.
    Falls back to Spotlight search everywhere.
    Returns full path or None.
    """
    # Option B — search in specific location first
    if location:
        base = LOCATIONS.get(location.lower(), location)
        for root, dirs, files in os.walk(base):
            for f in files:
                if name.lower() in f.lower():
                    return os.path.join(root, f)

    # Option A — search everywhere via Spotlight
    result = subprocess.run(
        ["mdfind", "-name", name],
        capture_output=True, text=True, timeout=10
    )
    lines = [l for l in result.stdout.strip().split("\n")
            #  if l and "venv" not in l and ".git" not in l]
            if l and not any(skip in l for skip in [
             "venv", ".git", "/System/", "/Library/",
             "PrivateFrameworks", ".framework", "/usr/",
             "/private/", "node_modules", ".app/Contents",
             ".Trash", "Mobile Documents/com~apple~CloudDocs/.Trash"
         ])]

    if lines:
        return lines[0]   # return first match

    return None


def read_file(name: str, location: str = None) -> None:
    """
    Finds and reads a text file aloud.
    Example: read_file("notes.txt") or read_file("notes.txt", "desktop")
    """
    speak(f"Looking for {name}.")
    path = _find_file(name, location)

    if not path:
        speak(f"Couldn't find {name} anywhere.")
        return

    print(f"📄 Found: {path}")

    try:
        with open(path, "r", errors="ignore") as f:
            content = f.read().strip()

        if not content:
            speak("The file is empty.")
            return

        # Truncate if too long
        if len(content) > 1000:
            content = content[:1000]
            speak(f"File is long — reading the first part.")

        speak(content)

    except Exception as e:
        speak(f"Couldn't read that file.")
        print(f"❌ Error: {e}")


def create_file(name: str, location: str = "desktop") -> None:
    """
    Creates a new file at the given location and opens it.
    Supports multiple formats: .txt, .docx, .pdf, .md, .py, .html, .rtf, .pages, etc.
    Example: create_file("ideas.txt") or create_file("resume.docx", "desktop")
    """
    if location is None:
        location = "desktop"
    base = LOCATIONS.get(location.lower(), os.path.expanduser("~/Desktop"))

    # Add .txt extension if no extension given
    if "." not in name:
        name = name + ".txt"

    path = os.path.join(base, name)

    if os.path.exists(path):
        speak(f"{name} already exists. Opening it.")
        subprocess.Popen(["open", path])
        return

    ext = os.path.splitext(name)[1].lower()

    # Create file based on extension
    if ext == ".docx":
        _create_docx(path)
    elif ext == ".rtf":
        _create_rtf(path)
    elif ext == ".html":
        _create_html(path, name)
    elif ext == ".md":
        with open(path, "w") as f:
            f.write(f"# {os.path.splitext(name)[0]}\n\n")
    elif ext == ".py":
        with open(path, "w") as f:
            f.write(f'# {os.path.splitext(name)[0]}\n\n')
    elif ext == ".json":
        with open(path, "w") as f:
            f.write("{}\n")
    elif ext == ".csv":
        with open(path, "w") as f:
            f.write("")
    elif ext == ".pages":
        # Create via AppleScript — opens Pages with a new doc
        _create_pages_doc(path, name)
        return
    elif ext == ".key":
        # Create via AppleScript — opens Keynote
        _create_keynote_doc(path, name)
        return
    elif ext == ".numbers":
        # Create via AppleScript — opens Numbers
        _create_numbers_doc(path, name)
        return
    else:
        # Default: create as plain text
        with open(path, "w") as f:
            f.write("")

    speak(f"Created {name} on your {location}. Opening it now.")
    print(f"📄 Created: {path}")
    subprocess.Popen(["open", path])


def _create_docx(path: str) -> None:
    """Creates a .docx file using python-docx or fallback."""
    try:
        from docx import Document
        doc = Document()
        doc.save(path)
    except ImportError:
        # Fallback: create via AppleScript + TextEdit
        # TextEdit can save as .docx
        with open(path, "w") as f:
            f.write("")
        print("⚠️  python-docx not installed, created empty file")


def _create_rtf(path: str) -> None:
    """Creates a minimal RTF file."""
    with open(path, "w") as f:
        f.write(r"{\rtf1\ansi\deff0 }")


def _create_html(path: str, name: str) -> None:
    """Creates a minimal HTML file."""
    title = os.path.splitext(name)[0]
    with open(path, "w") as f:
        f.write(f"""<!DOCTYPE html>
<html>
<head><title>{title}</title></head>
<body>
</body>
</html>
""")


def _create_pages_doc(path: str, name: str) -> None:
    """Creates a Pages document via AppleScript."""
    script = f'''
    tell application "Pages"
        activate
        set newDoc to make new document
    end tell
    '''
    subprocess.run(["osascript", "-e", script])
    speak(f"Opened a new Pages document.")
    print(f"📄 Created Pages doc: {name}")


def _create_keynote_doc(path: str, name: str) -> None:
    """Creates a Keynote presentation via AppleScript."""
    script = '''
    tell application "Keynote"
        activate
        set newDoc to make new document
    end tell
    '''
    subprocess.run(["osascript", "-e", script])
    speak(f"Opened a new Keynote presentation.")
    print(f"📄 Created Keynote: {name}")


def _create_numbers_doc(path: str, name: str) -> None:
    """Creates a Numbers spreadsheet via AppleScript."""
    script = '''
    tell application "Numbers"
        activate
        set newDoc to make new document
    end tell
    '''
    subprocess.run(["osascript", "-e", script])
    speak(f"Opened a new Numbers spreadsheet.")
    print(f"📄 Created Numbers: {name}")


def edit_file(name: str, content: str, location: str = None) -> None:
    """
    Appends text to a file, creating it if it doesn't exist.
    """
    path = _find_file(name, location)

    if not path:
        # File doesn't exist, create it first
        base = LOCATIONS.get(location.lower() if location else "desktop", os.path.expanduser("~/Desktop"))
        if "." not in name:
            name = name + ".txt"
        path = os.path.join(base, name)
        verb = "Created and added"
    else:
        verb = "Added"

    try:
        with open(path, "a") as f:
            f.write(f"\n{content}\n")

        speak(f"{verb} text to {name}.")
        print(f"✏️  Edited: {path}")
        subprocess.Popen(["open", path])
    except Exception as e:
        speak("Couldn't write to that file.")
        print(f"❌ Error: {e}")


def delete_file(name: str, location: str = None) -> None:
    """
    Moves a file to Trash (safe — recoverable).
    Example: delete_file("notes.txt") or delete_file("notes.txt", "desktop")
    """
    speak(f"Looking for {name} to delete.")
    path = _find_file(name, location)

    if not path:
        speak(f"Couldn't find {name}.")
        return

    try:
        # Move to trash using AppleScript — safe and recoverable
        script = f'tell application "Finder" to delete POSIX file "{path}"'
        subprocess.run(["osascript", "-e", script])
        speak(f"Moved {name} to trash.")
        print(f"🗑️  Deleted: {path}")
    except Exception as e:
        speak("Couldn't delete that file.")
        print(f"❌ Error: {e}")


def rename_file(old_name: str, new_name: str, location: str = None) -> None:
    """
    Renames a file.
    Example: rename_file("notes.txt", "ideas.txt")
    """
    speak(f"Looking for {old_name}.")
    path = _find_file(old_name, location)

    if not path:
        speak(f"Couldn't find {old_name}.")
        return

    # Keep same extension if new name has none
    if "." not in new_name and "." in old_name:
        ext = os.path.splitext(old_name)[1]
        new_name = new_name + ext

    new_path = os.path.join(os.path.dirname(path), new_name)

    try:
        os.rename(path, new_path)
        speak(f"Renamed to {new_name}.")
        print(f"✏️  Renamed: {path} → {new_path}")
    except Exception as e:
        speak("Couldn't rename that file.")
        print(f"❌ Error: {e}")


def get_recent_files(count: int = 5) -> None:
    """
    Finds and reads the most recently modified files.
    """
    speak("Finding your recent files.")
    try:
        result = subprocess.run(
            ["mdfind", "-onlyin", os.path.expanduser("~"),
             "kMDItemContentModificationDate >= $time.today(-1)"],
            capture_output=True, text=True, timeout=10
        )

        files = [
            f for f in result.stdout.strip().split("\n")
            if f and not any(skip in f for skip in
                           ["venv", ".git", "Library", "cache", ".pyc"])
        ]

        # Sort by modification time
        files = sorted(files, key=lambda f: os.path.getmtime(f)
                      if os.path.exists(f) else 0, reverse=True)

        if not files:
            speak("No recent files found.")
            return

        speak(f"Your {min(count, len(files))} most recent files:")
        for f in files[:count]:
            filename = os.path.basename(f)
            speak(filename)
            print(f"📄 {filename} — {f}")

    except Exception as e:
        speak("Couldn't get recent files.")
        print(f"❌ Error: {e}")


def copy_file(name: str, destination: str = "desktop") -> None:
    """
    Copies a file to a destination folder.
    Example: copy_file("jarvis.py", "desktop")
    """
    speak(f"Looking for {name}.")
    path = _find_file(name)

    if not path:
        speak(f"Couldn't find {name}.")
        return

    dest_dir = LOCATIONS.get(destination.lower(), os.path.expanduser("~/Desktop"))
    dest_path = os.path.join(dest_dir, os.path.basename(path))

    try:
        shutil.copy2(path, dest_path)
        speak(f"Copied {name} to {destination}.")
        print(f"📋 Copied: {path} → {dest_path}")
    except Exception as e:
        speak("Couldn't copy that file.")
        print(f"❌ Error: {e}")


# ─── Quick test ──────────────────────────────────────────────
if __name__ == "__main__":
    print("Testing file operations...\n")

    # Test create
    create_file("jarvis_test", "desktop")

    import time
    time.sleep(1)

    # Test read
    read_file("jarvis_test.txt", "desktop")

    time.sleep(1)

    # Test rename
    rename_file("jarvis_test.txt", "jarvis_renamed.txt", "desktop")

    time.sleep(1)

    # Test recent files
    get_recent_files(3)

    time.sleep(1)

    # Test delete
    delete_file("jarvis_renamed.txt", "desktop")