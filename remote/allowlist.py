"""
Remote command validation.

Every command submitted via the remote API passes through validate_command()
before a job is created. This is a defence-in-depth layer in front of the
intent engine and the confirmation flow in core/safety.py.
"""

import re

MAX_COMMAND_LENGTH = 1000

# Sources a remote client may claim. Anything non-"voice" is treated as a
# headless/remote caller by the intent router; "voice" would route confirmation
# prompts to the desktop microphone, so it is never accepted over the network.
ALLOWED_SOURCES = {"api", "controller", "mobile", "web"}

# Raw code / shell payloads are never a valid natural-language command.
_DANGER_PATTERNS = [
    r"\bimport\s+(os|subprocess|sys|shutil|socket)\b",
    r"\bexec\s*\(",
    r"\beval\s*\(",
    r"\b__import__\s*\(",
    r"\brm\s+(-[a-z]*\s+)*-?[a-z]*[rf][a-z]*\s+(/|~)",
    r"\bdel\s+/[sSqQ]\b",
    r"\bformat\s+[a-zA-Z]:",
    r"\bshutdown\s+/[sS]\b",
    r"\bos\.system\b",
    r"\bsubprocess\.",
    r"\bsudo\s+rm\b",
    r"\bmkfs(\.\w+)?\b",
    r"\bdd\s+if=",
    r":\(\)\s*\{\s*:\|:&\s*\};:",
    r"\bcurl\b[^|]*\|\s*(ba|z)?sh\b",
]

_compiled = [re.compile(p, re.IGNORECASE) for p in _DANGER_PATTERNS]


def validate_source(source: str) -> str:
    """Normalise a client-supplied source; unknown values fall back to 'api'."""
    source = (source or "").strip().lower()
    return source if source in ALLOWED_SOURCES else "api"


def validate_command(text: str) -> tuple[bool, str]:
    """
    Returns (True, "") if allowed, else (False, reason).
    """
    if not text or not text.strip():
        return False, "Empty command"

    if "\x00" in text:
        return False, "Invalid characters in command"

    if len(text) > MAX_COMMAND_LENGTH:
        return False, f"Command too long (max {MAX_COMMAND_LENGTH} chars)"

    for pattern in _compiled:
        if pattern.search(text):
            return False, "Command blocked: contains a dangerous pattern"

    return True, ""
