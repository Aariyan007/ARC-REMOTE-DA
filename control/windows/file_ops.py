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
    Falls back to searching common directories.
    Returns full path or None.
    """
    # Option B — search in specific location first
    if location:
        base = LOCATIONS.get(location.lower(), location)
        for root, dirs, files in os.walk(base):
            for f in files:
                if name.lower() in f.lower():
                    return os.path.join(root, f)

    # Option A — search common directories (Windows equivalent of Spotlight)
    search_dirs = [
        os.path.expanduser("~/Desktop"),
        os.path.expanduser("~/Documents"),
        os.path.expanduser("~/Downloads"),
    ]
    for search_dir in search_dirs:
        if not os.path.exists(search_dir):
            continue
        for root, dirs, files in os.walk(search_dir):
            # Skip common junk directories
            dirs[:] = [d for d in dirs if d not in (
                "venv", ".venv", ".git", "node_modules",
                "__pycache__", ".cache"
            )]
            for f in files:
                if name.lower() in f.lower():
                    return os.path.join(root, f)

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
    Supports multiple formats: .txt, .docx, .pdf, .md, .py, .html, .rtf, etc.
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
        os.startfile(path)
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
        # Apple Pages not available on Windows — create .docx instead
        alt_path = path.replace(".pages", ".docx")
        _create_docx(alt_path)
        speak(f"Pages is Mac-only. Created a Word document instead.")
        path = alt_path
        name = os.path.basename(alt_path)
    elif ext == ".key":
        # Apple Keynote not available on Windows — create .pptx instead
        alt_path = path.replace(".key", ".pptx")
        _create_pptx(alt_path)
        speak(f"Keynote is Mac-only. Created a PowerPoint instead.")
        path = alt_path
        name = os.path.basename(alt_path)
    elif ext == ".numbers":
        # Apple Numbers not available on Windows — create .xlsx instead
        alt_path = path.replace(".numbers", ".xlsx")
        _create_xlsx(alt_path)
        speak(f"Numbers is Mac-only. Created an Excel file instead.")
        path = alt_path
        name = os.path.basename(alt_path)
    else:
        # Default: create as plain text
        with open(path, "w") as f:
            f.write("")

    speak(f"Created {name} on your {location}. Opening it now.")
    print(f"📄 Created: {path}")
    os.startfile(path)


def _create_docx(path: str) -> None:
    """Creates a .docx file using python-docx or fallback."""
    try:
        from docx import Document
        doc = Document()
        doc.save(path)
    except ImportError:
        # Fallback: create empty file
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


def _create_pptx(path: str) -> None:
    """Creates a .pptx file using python-pptx or fallback."""
    try:
        from pptx import Presentation
        prs = Presentation()
        prs.save(path)
    except ImportError:
        with open(path, "w") as f:
            f.write("")
        print("⚠️  python-pptx not installed, created empty file")


def _create_xlsx(path: str) -> None:
    """Creates a .xlsx file using openpyxl or fallback."""
    try:
        from openpyxl import Workbook
        wb = Workbook()
        wb.save(path)
    except ImportError:
        with open(path, "w") as f:
            f.write("")
        print("⚠️  openpyxl not installed, created empty file")


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
        os.startfile(path)
    except Exception as e:
        speak("Couldn't write to that file.")
        print(f"❌ Error: {e}")


def delete_file(name: str, location: str = None) -> None:
    """
    Moves a file to Recycle Bin (safe — recoverable).
    Example: delete_file("notes.txt") or delete_file("notes.txt", "desktop")
    """
    speak(f"Looking for {name} to delete.")
    path = _find_file(name, location)

    if not path:
        speak(f"Couldn't find {name}.")
        return

    try:
        # Try send2trash for safe Recycle Bin deletion
        try:
            from send2trash import send2trash
            send2trash(path)
        except ImportError:
            # Fallback: use PowerShell to move to Recycle Bin
            ps_cmd = (
                f'$shell = New-Object -ComObject Shell.Application; '
                f'$item = $shell.Namespace(0).ParseName("{path}"); '
                f'$item.InvokeVerb("delete")'
            )
            subprocess.run(["powershell", "-c", ps_cmd], timeout=10)
        speak(f"Moved {name} to recycle bin.")
        print(f"🗑️  Deleted: {path}")
    except Exception as e:
        speak("Couldn't delete that file.")
        print(f"❌ Error: {e}")


def rename_file(old_name: str, new_name: str, location: str = None) -> dict:
    """
    Renames a file.
    Example: rename_file("notes.txt", "ideas.txt")
    """
    speak(f"Looking for {old_name}.")
    path = _find_file(old_name, location)

    if not path:
        speak(f"Couldn't find {old_name}.")
        return {
            "success": False,
            "error": f"Couldn't find {old_name}.",
            "old_name": old_name,
            "new_name": new_name,
        }

    # Keep same extension if new name has none
    if "." not in new_name and "." in old_name:
        ext = os.path.splitext(old_name)[1]
        new_name = new_name + ext

    new_path = os.path.join(os.path.dirname(path), new_name)

    try:
        os.rename(path, new_path)
        speak(f"Renamed to {new_name}.")
        print(f"✏️  Renamed: {path} → {new_path}")
        return {
            "success": True,
            "old_name": old_name,
            "new_name": new_name,
            "path": new_path,
        }
    except Exception as e:
        speak("Couldn't rename that file.")
        print(f"❌ Error: {e}")
        return {
            "success": False,
            "error": str(e),
            "old_name": old_name,
            "new_name": new_name,
        }


def get_recent_files(count: int = 5) -> None:
    """
    Finds and reads the most recently modified files.
    """
    speak("Finding your recent files.")
    try:
        search_dirs = [
            os.path.expanduser("~/Desktop"),
            os.path.expanduser("~/Documents"),
            os.path.expanduser("~/Downloads"),
        ]
        all_files = []
        for search_dir in search_dirs:
            if not os.path.exists(search_dir):
                continue
            for root, dirs, files in os.walk(search_dir):
                # Skip junk directories
                dirs[:] = [d for d in dirs if d not in (
                    "venv", ".venv", ".git", "node_modules",
                    "__pycache__", ".cache"
                )]
                for f in files:
                    if not f.endswith(".pyc"):
                        full = os.path.join(root, f)
                        all_files.append(full)

        # Sort by modification time
        all_files = sorted(
            all_files,
            key=lambda f: os.path.getmtime(f) if os.path.exists(f) else 0,
            reverse=True
        )

        if not all_files:
            speak("No recent files found.")
            return

        speak(f"Your {min(count, len(all_files))} most recent files:")
        for f in all_files[:count]:
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
