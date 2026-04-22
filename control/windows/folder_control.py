import subprocess
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional
from core.voice_response import speak
from core.llm_brain import set_context


# ─── Structured file resolution ──────────────────────────────

@dataclass
class FileMatch:
    """Single file match from a search."""
    path: str
    name: str
    size_bytes: int = 0
    modified_time: str = ""     # ISO 8601
    extension: str = ""
    score: float = 1.0          # 1.0 = exact name, <1.0 = fuzzy


@dataclass
class FileResolution:
    """Result of resolving a filename to a concrete path."""
    resolved: bool                          # True iff we have exactly ONE best match
    path: Optional[str] = None             # full path if resolved
    matches: List[FileMatch] = field(default_factory=list)
    reason: str = "not_found"             # exact_match | fuzzy_top | ambiguous | not_found


# Directories we always skip during walks
_SKIP_DIRS = {
    "venv", ".venv", ".git", "node_modules",
    "__pycache__", ".cache", "Application Support", ".Trash",
}

_SEARCH_DIRS = [
    os.path.expanduser("~/Desktop"),
    os.path.expanduser("~/Documents"),
    os.path.expanduser("~/Downloads"),
]


def find_files(name: str, constraints: dict = None) -> List[FileMatch]:
    """
    Search common directories for files matching `name`.
    Returns a ranked list of FileMatch objects.
    Never opens a microphone. Never speaks.

    Ranking:
      score=1.0  → exact filename match (case-insensitive)
      score=0.7  → filename contains the search term
      score=0.5  → stem contains the search term
    """
    name_lower = name.lower()
    # Strip common extensions from search term for stem matching
    name_stem = os.path.splitext(name_lower)[0]

    matches: List[FileMatch] = []
    seen: set = set()

    for search_dir in _SEARCH_DIRS:
        if not os.path.exists(search_dir):
            continue
        for root, dirs, files in os.walk(search_dir):
            dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
            for f in files:
                f_lower = f.lower()
                f_stem  = os.path.splitext(f_lower)[0]
                full    = os.path.join(root, f)

                if full in seen:
                    continue

                # Score the match
                if f_lower == name_lower:
                    score = 1.0
                elif name_lower in f_lower:
                    score = 0.7
                elif name_stem and name_stem in f_stem:
                    score = 0.5
                else:
                    continue

                seen.add(full)
                try:
                    stat = os.stat(full)
                    size = stat.st_size
                    mtime = datetime.fromtimestamp(stat.st_mtime).isoformat()
                except OSError:
                    size, mtime = 0, ""

                matches.append(FileMatch(
                    path=full,
                    name=f,
                    size_bytes=size,
                    modified_time=mtime,
                    extension=os.path.splitext(f)[1].lower(),
                    score=score,
                ))

    # Sort: score desc, then modified_time desc (newest first)
    matches.sort(key=lambda m: (-m.score, m.modified_time), reverse=False)
    matches.sort(key=lambda m: (-m.score,))
    return matches


def resolve_best_file(name: str, constraints: dict = None) -> FileResolution:
    """
    Resolve a filename to exactly one path, or report ambiguity.
    Never opens a microphone. Returns structured data the caller can act on.

    Returns:
      resolved=True  → path is the single best match
      resolved=False, reason='ambiguous'  → multiple matches; caller must choose
      resolved=False, reason='not_found'  → nothing found
    """
    matches = find_files(name, constraints)

    if not matches:
        return FileResolution(resolved=False, reason="not_found")

    # Group by score tier
    exact   = [m for m in matches if m.score == 1.0]
    fuzzy   = [m for m in matches if m.score < 1.0]

    # One exact match → unambiguous
    if len(exact) == 1:
        return FileResolution(
            resolved=True,
            path=exact[0].path,
            matches=exact,
            reason="exact_match",
        )

    # Multiple exact matches → ambiguous
    if len(exact) > 1:
        return FileResolution(
            resolved=False,
            matches=exact,
            reason="ambiguous",
        )

    # No exact, one fuzzy → use it (top score)
    if len(fuzzy) == 1:
        return FileResolution(
            resolved=True,
            path=fuzzy[0].path,
            matches=fuzzy,
            reason="fuzzy_top",
        )

    # Multiple fuzzy → ambiguous
    return FileResolution(
        resolved=False,
        matches=fuzzy[:5],   # cap at 5 candidates
        reason="ambiguous",
    )



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


def search_file(filename: str, announce: bool = True) -> None:
    """
    Voice-mode wrapper around find_files() + resolve_best_file().
    Uses the mic for disambiguation ONLY when source is voice.
    For programmatic/remote use, call resolve_best_file() directly.
    """
    if announce:
        speak(f"Searching for {filename}.")
    print(f"🔍 Searching for: {filename}")

    resolution = resolve_best_file(filename)

    if not resolution.resolved:
        if resolution.reason == "not_found":
            speak(f"Couldn't find any file named {filename}.")
            return
        # Ambiguous — list options and ask via voice
        shown = resolution.matches[:5]
        speak(f"I found {len(shown)} files.")
        for i, m in enumerate(shown, 1):
            location = os.path.dirname(m.path).replace(os.path.expanduser("~"), "home")
            speak(f"File {i}: {m.name}.")
            print(f"  {i}. {m.name} — {m.path}")

        speak("Which one do you want? Say the number.")
        shown_paths = [m.path for m in shown]

        # Listen for choice — direct mic input, no Gemini
        from core.speech_to_text import listen
        choice = listen()
        print(f"📝 Choice heard: '{choice}'")

        number = _extract_number(choice)
        if number and 1 <= number <= len(shown_paths):
            _open_or_read(shown_paths[number - 1])
        else:
            speak("Didn't catch that. Try again.")
            choice2 = listen()
            number2 = _extract_number(choice2)
            if number2 and 1 <= number2 <= len(shown_paths):
                _open_or_read(shown_paths[number2 - 1])
            else:
                speak("No worries, try searching again.")
        return

    # Single resolved match
    path = resolution.path
    name = os.path.basename(path)
    location = os.path.dirname(path).replace(os.path.expanduser("~"), "home")
    speak(f"Found {name} in {location}.")
    _open_or_read(path)


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