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

# File format keywords — maps spoken words to file extensions
FORMAT_KEYWORDS = {
    "document":     ".docx",
    "doc":          ".docx",
    "docx":         ".docx",
    "word":         ".docx",
    "word document": ".docx",
    "pdf":          ".pdf",
    "text":         ".txt",
    "txt":          ".txt",
    "markdown":     ".md",
    "md":           ".md",
    "python":       ".py",
    "python file":  ".py",
    "script":       ".py",
    "html":         ".html",
    "webpage":      ".html",
    "web page":     ".html",
    "csv":          ".csv",
    "spreadsheet":  ".csv",
    "json":         ".json",
    "rtf":          ".rtf",
    "rich text":    ".rtf",
    "pages":        ".pages",
    "numbers":      ".numbers",
    "keynote":      ".key",
    "presentation": ".key",
    "xml":          ".xml",
    "yaml":         ".yaml",
    "yml":          ".yaml",
    "log":          ".log",
    "swift":        ".swift",
    "java":         ".java",
    "javascript":   ".js",
    "js":           ".js",
    "css":          ".css",
    "sql":          ".sql",
}


def extract_filename(text: str) -> dict:
    """
    Extracts filename and optional location from the command.
    Returns dict with 'filename', 'location', and optionally 'new_name' keys.
    Handles natural speech: "create a file called ideas", "read notes.txt",
    "rename notes.txt to ideas.txt", "delete superman file",
    "create a document called superman", "make a pdf called resume", etc.
    """
    result = {"filename": None, "location": None}

    # Extract location
    for keyword, loc in LOCATION_KEYWORDS.items():
        if keyword in text:
            result["location"] = loc
            break

    # Extract new_name for rename: "rename X to Y"
    rename_match = re.search(r'rename\s+(\S+)\s+to\s+(\S+)', text)
    if rename_match:
        result["filename"] = rename_match.group(1)
        result["new_name"] = rename_match.group(2)
        return result

    # Detect file format from speech ("in document format", "as a pdf", etc.)
    detected_ext = None
    for fmt_word, ext in sorted(FORMAT_KEYWORDS.items(), key=lambda x: len(x[0]), reverse=True):
        # Match patterns like "in X format", "as a X", "X file", "X format", "a X called"
        fmt_patterns = [
            rf'in\s+{re.escape(fmt_word)}\s+format',
            rf'as\s+(?:a\s+)?{re.escape(fmt_word)}',
            rf'{re.escape(fmt_word)}\s+format',
            rf'{re.escape(fmt_word)}\s+file',
            rf'\ba\s+{re.escape(fmt_word)}\s+(?:called|named)\b',
            rf'\ba\s+{re.escape(fmt_word)}\b',
        ]
        for fp in fmt_patterns:
            if re.search(fp, text, re.IGNORECASE):
                detected_ext = ext
                break
        if detected_ext:
            break

    # Try patterns (order matters — most specific first):
    patterns = [
        r'(?:called|named)\s+([^\s]+\.\w+)',                          # "called notes.txt"
        r'(?:file|read|open|delete|rename|copy)\s+([^\s]+\.\w+)',     # "read notes.txt"
        r'([a-zA-Z0-9_-]+\.\w{1,5})',                                 # any file with extension
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            result["filename"] = match.group(1)
            return result

    # No extension found — try bare name patterns:
    bare_patterns = [
        r'(?:called|named)\s+(\S+)',                                   # "file called ideas"
        r'(?:contents?\s+(?:of|in|from))\s+(?:the\s+)?(\w+)',         # "contents of superman", "contents in resume"
        r'(?:create|make|delete|read|open|copy)\s+(?:a\s+)?(?:my\s+)?(?:file\s+)?(?:called\s+|named\s+)?(\w+)(?:\s+file)?',  # "create superman file", "read my notes"
        r'(?:create|make)\s+(\w+)\s+(?:file|document|note)',           # "create superman file"
        r'(?:create|make|read|delete|open|copy)\s+(?:a\s+)?(\w+)$',   # "create ideas" / "read notes" (at end)
    ]
    for pattern in bare_patterns:
        match = re.search(pattern, text)
        if match:
            candidate = match.group(1).strip()
            # Skip noise words and format words
            noise = {"a", "an", "the", "my", "this", "that", "new", "file",
                     "it", "contents", "document", "format", "particular",
                     "something", "some", "stuff", "things", "text",
                     "now", "just", "right", "before", "earlier", "recently",
                     "please", "here", "there", "first", "second", "last",
                     "one", "up", "ok", "okay", "sure", "yes", "no",
                     "kind", "also", "want", "like", "think",
                     "create", "make", "delete", "read", "open", "copy", "write", "add",
                     "and", "then", "with", "for", "so", "to"}
            if candidate not in noise and candidate not in FORMAT_KEYWORDS:
                # Apply detected format extension, fallback to .txt
                if detected_ext and "." not in candidate:
                    result["filename"] = candidate + detected_ext
                else:
                    result["filename"] = candidate
                return result

    return result


# ─── Meta-Word Detection ─────────────────────────────────────
# Words that sound like content but are actually references TO content.
# If every word in extracted content is in this set → user hasn't specified
# actual content yet, so we should ask.
CONTENT_META_WORDS = {
    "contents", "content", "text", "stuff", "something", "some",
    "things", "thing", "a", "the", "in", "it", "that", "this",
    "to", "file", "document", "particular", "there", "into",
    "on", "inside", "also", "want", "like", "do", "not",
    "i", "you", "me", "my", "will", "tell", "what", "add",
    "write", "put", "type", "insert", "append",
}


def _is_meta_content(content: str) -> bool:
    """
    Returns True if the extracted 'content' is all meta-words.
    e.g. 'contents in it' → True (not real content)
         'hi i am superman' → False (real content)
    """
    if not content:
        return True
    words = set(content.lower().split())
    return words.issubset(CONTENT_META_WORDS)


# ─── File Edit Extraction ────────────────────────────────────
def extract_file_edit_params(text: str) -> dict:
    """
    Extracts filename, location, and content for editing a file.
    Handles natural speech patterns like:
    - 'write hi i am superman in create.txt'
    - 'add the contents like hi i am the best superman'
    - 'inside create.txt add hello world'
    - 'put some text in that file'
    """
    result = extract_filename(text)
    result["content"] = None

    # Pattern 1: "in/inside <filename> write/add <content>"
    match_reverse = re.search(
        r'(?:in|inside|on)\s+(?:that\s+|the\s+|a\s+)?(?:particular\s+)?'
        r'(?:file\s+)?(?:name[d]?|called)?\s*([\w\.]+)\s+'
        r'(?:write|add|append|put|type|insert)\s+(.+)', text)
    if match_reverse:
        if not result["filename"]:
            result["filename"] = match_reverse.group(1).strip()
        result["content"] = match_reverse.group(2).strip()
        return result

    # Pattern 2: "contents like <content>" / "something like <content>"
    like_match = re.search(
        r'(?:contents?|something|text|stuff)\s+like\s+(?:a\s+)?(.+)', text)
    if like_match:
        content = like_match.group(1).strip()
        # Clean trailing file references
        content = re.sub(
            r'\s*(?:in|inside|to|into|on)\s+(?:that|the|a|this)\s+'
            r'(?:particular\s+)?(?:file|document|note).*$',
            '', content, flags=re.IGNORECASE).strip()
        if content:
            result["content"] = content
            return result

    # Pattern 3: "write/add <content> in/to <filename>"
    match_content_first = re.search(
        r'(?:write|add|append|put|type|insert)\s+(.+?)\s+'
        r'(?:in|inside|to|into|on)\s+(?:that\s+|the\s+)?'
        r'(?:particular\s+)?(?:file\s+)?(?:name[d]?\s+|called\s+)?'
        r'([\w\.]+)\s*$', text)
    if match_content_first:
        content = match_content_first.group(1).strip()
        fname = match_content_first.group(2).strip()
        if content and fname not in {"the", "a", "that", "this", "my", "file", "document",
                                       "note", "it", "particular", "now", "just", "right",
                                       "here", "there", "please", "first", "last", "one",
                                       "create", "make", "delete", "read", "open", "copy", "write", "add"}:
            result["content"] = content
            if not result["filename"]:
                result["filename"] = fname
            return result

    # Pattern 4: Generic "write/add <content>" (filename from context)
    match = re.search(r'(?:write|add|append|put|type|insert)\s+(.+)', text)
    if match:
        content = match.group(1).strip()

        # Clean up references to the file at the end
        if result["filename"]:
            fname = re.escape(result["filename"])
            content = re.sub(
                rf'\s*(?:in|inside|to|into|on)\s*(?:that|the|a|this)?'
                rf'\s*(?:particular)?\s*(?:file|document)?\s*'
                rf'(?:name|named|called)?\s*{fname}.*$',
                '', content, flags=re.IGNORECASE).strip()

        # Clean generic references
        content = re.sub(
            r'\s*(?:in|inside|to|into|on)\s+(?:that|the|a|this)\s+'
            r'(?:particular\s+)?(?:file|document|note).*$',
            '', content, flags=re.IGNORECASE).strip()
        content = re.sub(
            r'\s*(?:in|inside|to|into|on)\s+(?:it|that|this)(?:\s+file)?$',
            '', content, flags=re.IGNORECASE).strip()
        # Clean "the contents like" prefix
        content = re.sub(
            r'^(?:the\s+)?(?:contents?|text|stuff)\s+(?:like\s+)?(?:a\s+)?',
            '', content, flags=re.IGNORECASE).strip()
        # Clean "some" prefix
        content = re.sub(r'^some\s+', '', content, flags=re.IGNORECASE).strip()

        if content:
            result["content"] = content

    # ── Final meta-word check ────────────────────────────────
    # If the extracted content is all filler/meta words, the user
    # hasn't actually specified what to write. Set to None so the
    # router asks "What do you want me to write?"
    if result["content"] and _is_meta_content(result["content"]):
        print(f"📎 Content '{result['content']}' is all meta-words — clearing")
        result["content"] = None

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
        # Skip noise words like "my", "the", "a"
        to_match = re.search(r'(?:to|email)\s+(?:my\s+|the\s+|a\s+|an\s+)?(\w+)', text)
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


# ─── Compound File Extraction ────────────────────────────────
def extract_compound_file_params(text: str) -> dict:
    """
    Extracts params for compound create+write commands like:
    - 'create a file called notes.txt and write hello world in it'
    - 'make a file named ideas then add some text'
    - 'create superman.txt and put hi i am superman inside'
    - 'create a file and name it superman.txt and also add contents in it'

    Returns dict with filename, location, content, and is_compound flag.
    """
    result = {"filename": None, "location": None, "content": None, "is_compound": False}

    # Smart split: split on "and/then" FOLLOWED by an edit keyword
    # This avoids splitting on "create a file and name it as X"
    split_match = re.split(
        r'\b(?:and\s+(?:then\s+)?(?:also\s+)?(?:i\s+(?:also\s+)?(?:wanted?\s+(?:to\s+)?)?)?(?=(?:write|add|put|type|insert|append))|then\s+(?=(?:write|add|put|type|insert|append))|after\s+that\s+(?=(?:write|add|put|type|insert|append)))',
        text, maxsplit=1
    )

    if len(split_match) < 2:
        # Fallback: try simple split on "and" but validate both parts
        split_match = re.split(r'\b(?:and\s+then|then|and|after\s+that)\b', text)
        # Find the split point where create is before and edit is after
        for i in range(1, len(split_match)):
            before = " ".join(split_match[:i]).strip()
            after  = " ".join(split_match[i:]).strip()
            has_create = bool(re.search(r'\b(?:create|make|new)\b', before))
            has_edit   = bool(re.search(r'\b(?:write|add|put|type|insert|append)\b', after))
            if has_create and has_edit:
                split_match = [before, after]
                break
        else:
            return result

    if len(split_match) < 2:
        return result

    create_part = split_match[0].strip()
    edit_part   = split_match[1].strip()

    # Check if create_part has create keywords
    if not re.search(r'\b(?:create|make|new)\b', create_part):
        return result

    # Check if edit_part has edit keywords
    if not re.search(r'\b(?:write|add|put|type|insert|append)\b', edit_part):
        return result

    # Extract filename from create part
    file_info = extract_filename(create_part)
    result["filename"] = file_info.get("filename")
    result["location"] = file_info.get("location")

    # If create_part didn't find a filename, try the whole text
    # (handles "create a file and name it superman.txt and add...")
    if not result["filename"]:
        whole_info = extract_filename(text)
        result["filename"] = whole_info.get("filename")
        if not result["location"]:
            result["location"] = whole_info.get("location")

    # Extract content from edit part
    edit_info = extract_file_edit_params(edit_part)
    result["content"] = edit_info.get("content")

    # If edit_part mentions a filename but create_part didn't find one
    if not result["filename"] and edit_info.get("filename"):
        result["filename"] = edit_info["filename"]

    result["is_compound"] = True
    return result


def is_compound_file_command(text: str) -> bool:
    """
    Quick check: does this command contain both create AND edit keywords
    joined by a connector word?
    """
    has_create = bool(re.search(
        r'\b(?:create|make|new)\b.*?(?:\b(?:file|document|note|named|called)\b|\w+\.\w+)',
        text
    ))
    has_edit   = bool(re.search(r'\b(?:write|add|put|type|insert|append)\b', text))
    has_join   = bool(re.search(r'\b(?:and|then|after that|and then)\b', text))
    return has_create and has_edit and has_join


# ─── Compound Search and Send Extraction ─────────────────────
def is_find_and_send_command(text: str) -> bool:
    """
    Quick check: does this command contain find/search AND send to email?
    """
    has_find = bool(re.search(r'\b(?:find|search|get|look for)\b', text))
    has_send = bool(re.search(r'\b(?:send|email)\b', text))
    has_join = bool(re.search(r'\b(?:and|then|to)\b', text))
    return has_find and has_send and has_join

def extract_find_and_send_params(text: str) -> dict:
    """
    Extracts filename and email from "find X and send it to Y"
    """
    result = {"filename": None, "to": None}
    
    # Try splitting into find part and send part
    split_match = re.split(r'\b(?:and\s+)?(?:then\s+)?(?:send|email)\b', text, maxsplit=1)
    if len(split_match) == 2:
        find_part = split_match[0].strip()
        send_part = split_match[1].strip()
        
        # 1. Get filename from find_part
        file_info = extract_filename(find_part)
        # If extract_filename failed, fallback to extract_query
        result["filename"] = file_info.get("filename") or extract_query(find_part)
        
        # 2. Get email from send_part
        email_info = extract_email_params("send " + send_part)
        result["to"] = email_info.get("to")
        
    return result


def extract_url(text: str) -> Optional[str]:
    """
    Pull an http(s) URL or bare domain from natural language.
    Used by the Playwright-backed open_url intent.
    """
    t = (text or "").strip()
    if not t:
        return None
    m = re.search(r'(https?://[^\s<>"\'\]]+)', t, re.I)
    if m:
        return m.group(1).rstrip(").,;]}\"'")
    low = t.lower()
    for phrase in ("go to ", "visit ", "navigate to ", "open "):
        if phrase not in low:
            continue
        idx = low.index(phrase) + len(phrase)
        rest = t[idx:].strip()
        if not rest:
            continue
        token = rest.split()[0].strip(".,;!?)]}\"'")
        if "." in token and re.match(r"^[\w./-]+$", token, re.I):
            if not re.match(r"https?://", token, re.I):
                return "https://" + token.lstrip("/")
            return token
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

    # Edit File
    print("\n── Edit Files ──")
    for cmd in [
        "write some contents in superman.txt",
        "inside superman.txt write I am a hero",
        "append this is a test to notes",
        "add hello world",
        "add some contents in it",           # should → content=None
        "add text to the file",              # should → content=None
        "add text to not this text i will tell you what text to add",  # should → content=None
        "write hi i am the best superman",   # should → content="hi i am the best superman"
    ]:
        print(f"  '{cmd}' → {extract_file_edit_params(cmd)}")

    # Compound File
    print("\n── Compound File Commands ──")
    for cmd in [
        "create a file called notes.txt and write hello world in it",
        "make a file named ideas then add some text",
        "create superman.txt and put hi i am superman inside",
        "open vscode",  # not compound
    ]:
        is_comp = is_compound_file_command(cmd)
        params = extract_compound_file_params(cmd) if is_comp else {}
        print(f"  '{cmd}' → compound={is_comp} params={params}")

    # Email
    print("\n── Email ──")
    for cmd in ["send email to john@gmail.com about meeting saying let's meet at 3"]:
        print(f"  '{cmd}' → {extract_email_params(cmd)}")
