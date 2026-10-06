"""
File search with "did you mean" suggestions, plus download tickets.

Search is exact-first; when nothing matches well it falls back to similar file
names (typos, different word order, partial names) so the phone can still offer
something useful. Downloads never take a client-supplied path: the phone gets a
ticket for a path the server itself returned from a search.
"""

import difflib
import os
import re
import secrets
import threading
import time
from typing import Dict, List, Optional

from remote_tools import policy

SKIP_DIRS = {
    "AppData", "Windows", "Program Files", "Program Files (x86)", "Library",
    "Applications", ".Trash", "node_modules", "__pycache__", "venv", ".venv",
    ".git", ".svn", "site-packages",
}
MAX_FILES_INDEXED = 60000
INDEX_TTL = 60.0
TICKET_TTL = 600.0

_index_lock = threading.Lock()
_index_cache: Dict[tuple, tuple] = {}   # roots -> (built_at, [(path, name_lower, stem_lower)])


def _norm(s: str) -> str:
    return re.sub(r"[\s_\-.]+", " ", s.lower()).strip()


def _build_index(roots: List[str]) -> list:
    entries = []
    for root in roots:
        for dirpath, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in SKIP_DIRS]
            for f in files:
                if f.startswith("."):
                    continue
                entries.append((os.path.join(dirpath, f), f.lower(), _norm(os.path.splitext(f)[0])))
                if len(entries) >= MAX_FILES_INDEXED:
                    return entries
    return entries


def _get_index(roots: List[str]) -> list:
    key = tuple(roots)
    now = time.time()
    with _index_lock:
        cached = _index_cache.get(key)
        if cached and now - cached[0] < INDEX_TTL:
            return cached[1]
    entries = _build_index(roots)
    with _index_lock:
        _index_cache[key] = (now, entries)
    return entries


def clear_index_cache() -> None:
    with _index_lock:
        _index_cache.clear()


def _score(query_norm: str, query_ext: str, query_words: List[str], name_lower: str, stem: str):
    """(score 0..1, is_hit). A hit is a real name match (equal, contained, or every word
    present); anything found only by fuzzy similarity is a suggestion, not a hit."""
    ext_penalty = 0.25 if query_ext and not name_lower.endswith(query_ext) else 0.0

    stem_words = set(stem.split())
    all_words = bool(query_words) and all(
        w in stem_words or any(w in sw for sw in stem_words) for w in query_words)

    if stem == query_norm:
        base, hit = 1.0, True
    elif query_norm and query_norm in stem:
        base, hit = 0.9 - min(0.1, (len(stem) - len(query_norm)) / 200), True
    elif all_words:
        base, hit = 0.85, True
    elif stem and stem in query_norm and len(stem) >= 3:
        base, hit = 0.7, False
    else:
        ratio = difflib.SequenceMatcher(None, query_norm, stem).ratio()
        overlap = (sum(1 for w in query_words if w in stem_words or any(w in sw for sw in stem_words))
                   / len(query_words)) if query_words else 0.0
        base, hit = max(ratio, 0.35 + 0.5 * overlap if overlap else 0.0), False
    return max(0.0, base - ext_penalty), hit and not ext_penalty


def _describe(path: str, score: float, hit: bool) -> dict:
    try:
        st = os.stat(path)
        size, modified = st.st_size, st.st_mtime
    except OSError:
        size, modified = 0, 0.0
    return {
        "name": os.path.basename(path),
        "path": path,
        "folder": os.path.dirname(path),
        "size": size,
        "modified": modified,
        "score": round(score, 3),
        "match_type": "exact" if hit else "similar",
    }


def find_files(query: str, roots: Optional[List[str]] = None, limit: int = 5,
               min_similar: float = 0.45) -> dict:
    """
    Returns {"query", "exact": bool, "matches": [...]}.
    `exact` is True when the best match is a real hit; otherwise `matches` are
    "did you mean" suggestions (possibly empty).
    """
    query = (query or "").strip()
    roots = policy.file_roots() if roots is None else roots
    if not query or not roots:
        return {"query": query, "exact": False, "matches": []}

    ext_m = re.search(r"\.(\w{1,8})$", query.lower())
    query_ext = ext_m.group(0) if ext_m else ""
    stem_q = query[: -len(query_ext)] if query_ext else query
    query_norm = _norm(stem_q)
    query_words = [w for w in query_norm.split() if len(w) > 1]

    scored = []
    for path, name_lower, stem in _get_index(roots):
        sc, hit = _score(query_norm, query_ext, query_words, name_lower, stem)
        if sc >= min_similar:
            scored.append((sc, hit, path))
    # Real hits always outrank suggestions; then by score, then shorter path.
    scored.sort(key=lambda x: (not x[1], -x[0], len(x[2])))

    top = scored[: max(1, limit)]
    exact = bool(top) and top[0][1]
    matches = [_describe(p, sc, hit) for sc, hit, p in top]
    return {"query": query, "exact": exact, "matches": matches}


# ── Download tickets ─────────────────────────────────────────

_tickets_lock = threading.Lock()
_tickets: Dict[str, tuple] = {}   # ticket -> (device_id, real_path, expires)


def issue_download_ticket(device_id: str, path: str) -> Optional[str]:
    """Ticket for a file the server found. None if the path is not downloadable."""
    real = policy.safe_file_path(path)
    if not real:
        return None
    try:
        if os.path.getsize(real) > policy.max_download_bytes():
            return None
    except OSError:
        return None
    ticket = secrets.token_urlsafe(24)
    now = time.time()
    with _tickets_lock:
        for t in [t for t, v in _tickets.items() if v[2] < now]:
            _tickets.pop(t, None)
        _tickets[ticket] = (device_id, real, now + TICKET_TTL)
    return ticket


def resolve_download_ticket(ticket: str, device_id: str) -> Optional[str]:
    """Real path for a valid ticket owned by `device_id`; re-validated against policy now."""
    with _tickets_lock:
        entry = _tickets.get(ticket or "")
    if not entry or entry[2] < time.time() or entry[0] != device_id:
        return None
    return policy.safe_file_path(entry[1])


def attach_download_urls(result: dict, device_id: str) -> dict:
    """Add `download_url` (+ `downloadable`) to each match; mutates and returns result."""
    for m in result.get("matches", []):
        ticket = issue_download_ticket(device_id, m["path"])
        m["downloadable"] = bool(ticket)
        if ticket:
            m["download_url"] = f"/files/{ticket}"
    return result
