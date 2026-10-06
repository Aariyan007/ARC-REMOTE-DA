"""
Shared safety policy for remote tools: which folders the phone may touch,
path validation (no symlink / ".." escapes) and secret redaction.
"""

import os
import re
from typing import List, Optional

DEFAULT_ROOT_NAMES = ("Desktop", "Documents", "Downloads")
DEFAULT_MAX_DOWNLOAD_MB = 200


def file_roots() -> List[str]:
    """Folders the phone may search and download from (ARC_FILE_ROOTS, os.pathsep-separated)."""
    raw = os.getenv("ARC_FILE_ROOTS", "")
    if raw.strip():
        roots = [os.path.expanduser(p.strip()) for p in raw.split(os.pathsep) if p.strip()]
    else:
        home = os.path.expanduser("~")
        roots = [os.path.join(home, n) for n in DEFAULT_ROOT_NAMES]
    out = []
    for r in roots:
        real = os.path.realpath(r)
        if os.path.isdir(real) and real not in out:
            out.append(real)
    return out


def max_download_bytes() -> int:
    try:
        mb = float(os.getenv("ARC_MAX_DOWNLOAD_MB", DEFAULT_MAX_DOWNLOAD_MB))
    except ValueError:
        mb = DEFAULT_MAX_DOWNLOAD_MB
    return int(max(1.0, mb) * 1024 * 1024)


def _is_within(path: str, root: str) -> bool:
    try:
        return os.path.commonpath([path, root]) == root
    except ValueError:  # different drives on Windows
        return False


def safe_file_path(path: str, roots: Optional[List[str]] = None) -> Optional[str]:
    """
    Resolve `path` and return the real path only if it is an existing regular file
    inside an allowed root. Symlinks are resolved first, so a link inside a root that
    points outside is rejected. Returns None otherwise.
    """
    if not path or "\x00" in path:
        return None
    roots = file_roots() if roots is None else roots
    real = os.path.realpath(os.path.expanduser(path))
    if not os.path.isfile(real):
        return None
    if not any(_is_within(real, r) for r in roots):
        return None
    return real


_SECRET_PATTERNS = [
    re.compile(r"(?i)\b(password|passwd|pwd|secret|token|api[_-]?key)\b(\s*[=:]\s*)\S+"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{8,}"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{20,}"),
]


def redact(text: str) -> str:
    """Mask obvious secrets in text before it reaches events, logs or the audit trail."""
    if not text:
        return text
    out = text
    out = _SECRET_PATTERNS[0].sub(lambda m: f"{m.group(1)}{m.group(2)}[REDACTED]", out)
    for p in _SECRET_PATTERNS[1:]:
        out = p.sub("[REDACTED]", out)
    return out
