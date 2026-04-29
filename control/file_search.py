import os
import re
import sys
from typing import Optional, List, Tuple

# ── Hidden/system directories to skip during search ──────────
_SKIP_DIRS = {
    'AppData', 'Windows', 'Program Files', 'Program Files (x86)',
    'Library', 'Applications', '.Trash', 'node_modules', '__pycache__',
    'venv', '.venv', '.git', '.svn', 'site-packages',
}


def _get_default_search_dirs() -> List[str]:
    """Return platform-aware default search directories."""
    home = os.path.expanduser("~")
    dirs = [
        os.path.join(home, "Desktop"),
        os.path.join(home, "Documents"),
        os.path.join(home, "Downloads"),
    ]
    # On Windows, also check the user profile root
    if sys.platform == "win32":
        user_profile = os.environ.get("USERPROFILE", "")
        if user_profile:
            for extra in ("OneDrive", "OneDrive - Personal"):
                candidate = os.path.join(user_profile, extra)
                if os.path.isdir(candidate) and candidate not in dirs:
                    dirs.append(candidate)
    return dirs


def search_files_advanced_multiple(query: str, root_dir: str = None, top_k: int = 5) -> List[str]:
    """
    Searches the filesystem for a file matching the natural language query.
    Returns a list of the top_k best absolute paths.

    Supports:
      - Exact match: "resume.txt" → resume.txt (score 100)
      - Name without extension: "resume" → resume.txt, resume.pdf, etc. (score 90)
      - Substring match: "resume" → my_resume_2024.pdf (score 50)
      - Fuzzy word match: "project notes" → project_notes.md (score 25)
    """
    if root_dir:
        search_dirs = [root_dir]
    else:
        search_dirs = _get_default_search_dirs()

    query_lower = query.lower().strip()

    # Separate extension from query if user provided one
    ext_match = re.search(r'\.(\w+)$', query_lower)
    target_ext = ext_match.group(0) if ext_match else None
    base_query = query_lower.replace(target_ext, '').strip() if target_ext else query_lower

    # Split query into words for fuzzy matching
    query_words = [w for w in base_query.split() if len(w) > 1]

    matches: List[Tuple[int, str]] = []

    for search_dir in search_dirs:
        if not os.path.isdir(search_dir):
            continue

        for root, dirs, files in os.walk(search_dir):
            # Prune hidden and system directories in-place
            dirs[:] = [
                d for d in dirs
                if not d.startswith('.') and d not in _SKIP_DIRS
            ]

            for file in files:
                file_lower = file.lower()
                name, ext = os.path.splitext(file_lower)
                score = 0

                # If user specified an extension, only match that extension
                if target_ext and ext != target_ext:
                    continue

                # ── Scoring ──────────────────────────────────────
                if base_query == name:
                    # Exact name match (with or without extension)
                    score = 100
                elif base_query == file_lower:
                    # Exact full filename match
                    score = 100
                elif not target_ext and base_query == name:
                    # User said "resume", file is "resume.txt"
                    score = 90
                elif base_query in name:
                    # Substring: "resume" in "my_resume_2024"
                    score = 50
                elif name in base_query:
                    # Reverse substring: filename is shorter
                    score = 30
                elif query_words and all(w in name or w in file_lower for w in query_words):
                    # All words present: "project notes" → "project_notes.md"
                    score = 25
                elif query_words and any(w in name for w in query_words):
                    # Partial word match: at least one word matches
                    matched = sum(1 for w in query_words if w in name)
                    score = 10 + (matched * 5)

                if score > 0:
                    # Boost score for files in more "expected" locations
                    depth = root.count(os.sep) - search_dir.count(os.sep)
                    if depth == 0:
                        score += 5  # Direct child of search dir
                    matches.append((score, os.path.join(root, file)))

    if matches:
        matches.sort(key=lambda x: x[0], reverse=True)
        return [m[1] for m in matches[:top_k]]
    return []


def search_files_advanced(query: str, root_dir: str = None) -> Optional[str]:
    """Returns the absolute path of the single best match."""
    results = search_files_advanced_multiple(query, root_dir, top_k=1)
    if results:
        print(f"🔍 Found best match for '{query}': {results[0]}")
        return results[0]
    print(f"⚠️ No matches found for '{query}'")
    return None
