"""
Parameter Extractors — lightweight regex/keyword extraction.

Pulls structured parameters from normalized command text
without any LLM call. Runs in <1ms.
"""

import re
from typing import Optional


# ─── App Name Extraction ─────────────────────────────────────
APP_ALIASES = {
    "vscode":    "vscode",
    "vs code":   "vscode",
    "code":      "vscode",
    "safari":    "safari",
    "chrome":    "chrome",
    "terminal":  "terminal",
    "finder":    "finder",
    "notes":     "notes",
    "music":     "music",
    "spotify":   "spotify",
    "slack":     "slack",
    "discord":   "discord",
    "zoom":      "zoom",
    "telegram":  "telegram",
    "whatsapp":  "whatsapp",
    "messages":  "messages",
    "photos":    "photos",
    "preview":   "preview",
    "calendar":  "calendar",
    "settings":  "system preferences",
    "preferences": "system preferences",
    "activity monitor": "activity monitor",
    "xcode":     "xcode",
    "postman":   "postman",
    "figma":     "figma",
    "notion":    "notion",
    "obsidian":  "obsidian",
}


def extract_app_name(text: str) -> Optional[str]:
    """
    Extracts an app name from the command text.
    Returns canonical app name or None.
    """
    text = text.lower().strip()

    # Check known aliases (longest-first to match "activity monitor" before "activity")
    for alias, canonical in sorted(APP_ALIASES.items(), key=lambda x: len(x[0]), reverse=True):
        if alias in text:
            return canonical

    # Try to extract from "open <app>" pattern
    match = re.search(r'(?:open|launch|start|fire up|run|close|quit|exit|switch to|go to|bring up|hide|minimize)\s+(\w+)', text)
    if match:
        candidate = match.group(1)
        if candidate not in {"the", "my", "a", "an", "up", "it", "this", "that"}:
            return candidate

    return None


# ─── Amount Extraction ────────────────────────────────────────
def extract_amount(text: str, default: int = 10) -> int:
    """
    Extracts a numeric amount from the command.
    Used for volume/brightness controls.
    Returns the number found, or default.
    """
    # "by 30", "to 50", just "20"
    match = re.search(r'\b(\d{1,3})\b', text)
    if match:
        val = int(match.group(1))
        if 0 < val <= 100:
            return val

    # Word-based amounts
    WORD_AMOUNTS = {
        "max": 100, "full": 100, "maximum": 100,
        "half": 50, "halfway": 50,
        "min": 0, "minimum": 0, "zero": 0,
        "a little": 5, "a bit": 5, "slightly": 5,
        "a lot": 30, "way up": 30, "way down": 30,
    }
    for word, amount in WORD_AMOUNTS.items():
        if word in text:
            return amount

    return default


# ─── Query Extraction ────────────────────────────────────────
def extract_query(text: str) -> Optional[str]:
    """
    Extracts a search query from the command.
    For web search, email search, file search.
    """
    # "search for X", "search X", "look up X", "google X", "find X"
    patterns = [
        r'(?:search|google|look up|find|look for|search for|browse)\s+(?:for\s+)?(.+)',
        r'(?:what is|what are|who is|how to|why does|when did)\s+(.+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            query = match.group(1).strip()
            # Clean trailing noise
            query = re.sub(r'\b(on google|on the web|online|on safari|on chrome)\b', '', query).strip()
            if query:
                return query

    return None


# ─── Filename Extraction ─────────────────────────────────────
LOCATION_KEYWORDS = {
    "desktop":   "desktop",
    "downloads": "downloads",
    "documents": "documents",
    "home":      "~",
}


def extract_filename(text: str) -> dict:
    """
    Extracts filename and optional location from the command.
    Returns dict with 'filename' and 'location' keys.
    """
    result = {"filename": None, "location": None}

    # Extract location
    for keyword, loc in LOCATION_KEYWORDS.items():
        if keyword in text:
            result["location"] = loc
            break

    # Try patterns: "read notes.txt", "create file called ideas.md", "delete resume.pdf"
    patterns = [
        r'(?:called|named)\s+([^\s]+\.\w+)',           # "called notes.txt"
        r'(?:file|read|open|delete|rename|copy)\s+([^\s]+\.\w+)',  # "read notes.txt"
        r'([a-zA-Z0-9_-]+\.\w{1,5})',                  # any file with extension
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            result["filename"] = match.group(1)
            break

    # If no extension found, try bare name after action word
    if not result["filename"]:
        match = re.search(r'(?:called|named)\s+(\S+)', text)
        if match:
            result["filename"] = match.group(1)

    return result


# ─── Email Parameter Extraction ──────────────────────────────
def extract_email_params(text: str) -> dict:
    """
    Extracts email parameters: to, subject, body.
    From commands like "send email to john@gmail.com about meeting saying let's meet at 3"
    """
    result = {"to": None, "subject": None, "body": None}

    # Extract email address
    email_match = re.search(r'[\w.+-]+@[\w-]+\.[\w.]+', text)
    if email_match:
        result["to"] = email_match.group(0)

    # Extract recipient name (if no email address)
    if not result["to"]:
        to_match = re.search(r'(?:to|email)\s+(\w+)', text)
        if to_match:
            result["to"] = to_match.group(1)

    # Extract subject: "about X" or "regarding X" or "subject X"
    subject_match = re.search(r'(?:about|regarding|subject|titled?)\s+(.+?)(?:\s+(?:saying|body|message|that says)|$)', text)
    if subject_match:
        result["subject"] = subject_match.group(1).strip()

    # Extract body: "saying X" or "body X" or "that says X"
    body_match = re.search(r'(?:saying|body|message|that says|content)\s+(.+)', text)
    if body_match:
        result["body"] = body_match.group(1).strip()

    return result


# ─── Folder Target Extraction ────────────────────────────────
def extract_folder_target(text: str) -> Optional[str]:
    """
    Extracts folder name/target from the command.
    """
    for keyword, target in LOCATION_KEYWORDS.items():
        if keyword in text:
            return keyword

    # "open folder X", "create folder named X"
    match = re.search(r'(?:folder|directory)\s+(?:called|named)?\s*(\S+)', text)
    if match:
        candidate = match.group(1).strip()
        if candidate not in {"the", "my", "a", "an", "called", "named"}:
            return candidate

    return None


# ─── Quick test ──────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("  PARAM EXTRACTOR TEST")
    print("=" * 60)

    # App name
    print("\n── App Names ──")
    for cmd in ["open vscode", "launch my editor", "close safari", "switch to terminal", "open spotify"]:
        print(f"  '{cmd}' → {extract_app_name(cmd)}")

    # Amount
    print("\n── Amounts ──")
    for cmd in ["volume up by 30", "turn up", "brightness to max", "a little louder"]:
        print(f"  '{cmd}' → {extract_amount(cmd)}")

    # Query
    print("\n── Queries ──")
    for cmd in ["search for python tutorials", "google machine learning", "look up KTU results"]:
        print(f"  '{cmd}' → {extract_query(cmd)}")

    # Filename
    print("\n── Filenames ──")
    for cmd in ["read notes.txt", "delete resume.pdf on desktop", "create file called ideas.md"]:
        print(f"  '{cmd}' → {extract_filename(cmd)}")

    # Email
    print("\n── Email ──")
    for cmd in ["send email to john@gmail.com about meeting saying let's meet at 3"]:
        print(f"  '{cmd}' → {extract_email_params(cmd)}")
