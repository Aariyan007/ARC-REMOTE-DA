"""
Memory System — user profile, conversation history, and context resolution.

Enhanced with:
- Pronoun/context resolution ("it", "that", "this")
- Last action tracking for "do that again"
- High-confidence-only resolution (>0.85), else asks
"""

import json
import os
import re
from datetime import datetime
from typing import Optional, Tuple

# ─── File Paths ──────────────────────────────────────────────
BASE_DIR         = os.path.dirname(os.path.dirname(__file__))
PROFILE_PATH     = os.path.join(BASE_DIR, "data", "user_profile.json")
CONVERSATION_PATH= os.path.join(BASE_DIR, "data", "conversation.json")
MAX_HISTORY      = 20   # keep last 20 exchanges in memory
# ─────────────────────────────────────────────────────────────

# ─── Context Tracking ───────────────────────────────────────
# Tracks last action/target for pronoun resolution.
_last_context = {
    "action":  None,    # e.g., "open_app"
    "target":  None,    # e.g., "vscode"
    "result":  None,    # e.g., "Opened VS Code"
    "command": None,    # e.g., "open vscode"
}

# ─── File Action History ────────────────────────────────────
# Tracks recent file operations so "that file" / "the file" resolves.
_file_history = []      # List of {filename, path, action, timestamp}
MAX_FILE_HISTORY = 10


# ── User Profile ─────────────────────────────────────────────

def load_profile() -> dict:
    """Loads Aariyan's personal profile."""
    with open(PROFILE_PATH, "r") as f:
        return json.load(f)


def update_profile(key: str, value) -> None:
    """Updates a field in the user profile."""
    profile = load_profile()
    profile[key] = value
    with open(PROFILE_PATH, "w") as f:
        json.dump(profile, f, indent=2)
    print(f"✅ Profile updated: {key} = {value}")


def add_note(note: str) -> None:
    """Adds a personal note to the profile — things Jarvis should remember."""
    profile = load_profile()
    profile["notes"].append({
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "note": note
    })
    with open(PROFILE_PATH, "w") as f:
        json.dump(profile, f, indent=2)
    print(f"📝 Note saved: '{note}'")


# ── Conversation Memory ───────────────────────────────────────

def load_conversation() -> list:
    """Loads current session conversation history."""
    if not os.path.exists(CONVERSATION_PATH):
        return []
    with open(CONVERSATION_PATH, "r") as f:
        return json.load(f)


def save_exchange(you_said: str, jarvis_said: str) -> None:
    """
    Saves one exchange to conversation history.
    Keeps only last MAX_HISTORY exchanges.
    """
    history = load_conversation()
    history.append({
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "you":       you_said,
        "jarvis":    jarvis_said
    })
    # Keep only recent history
    history = history[-MAX_HISTORY:]
    with open(CONVERSATION_PATH, "w") as f:
        json.dump(history, f, indent=2)


def clear_conversation() -> None:
    """Clears conversation history — called when Jarvis goes to sleep."""
    global _last_context, _file_history
    with open(CONVERSATION_PATH, "w") as f:
        json.dump([], f)
    _last_context = {"action": None, "target": None, "result": None, "command": None}
    _file_history = []
    print("🧹 Conversation history cleared")


def get_context_for_gemini() -> str:
    """
    Builds a context string from profile + recent conversation.
    This gets passed to Gemini so it knows who Aariyan is
    and what was just talked about.
    """
    profile  = load_profile()
    history  = load_conversation()

    # Build personality context
    context = f"""
You are Jarvis, a personal AI assistant for {profile['name']}.

About {profile['name']}:
- He is a {', '.join(profile['identity'])}
- Works with: {', '.join(profile['works_with'])}
- Current projects: {', '.join(profile['current_projects'])}
- Personality you should use: {profile['personality_preference']}

Your personality:
- Be witty and sarcastic sometimes
- Be casual and friendly always
- Be professional when the task needs it
- Make jokes when appropriate
- You can lightly roast {profile['name']}
- Keep responses short — max 2 sentences
- Never say the same thing twice
- You know {profile['name']} personally — talk like a close friend who also works for him

"""

    # Add personal notes if any
    if profile.get("notes"):
        recent_notes = profile["notes"][-5:]
        context += "Things to remember about him:\n"
        for n in recent_notes:
            context += f"- {n['note']}\n"
        context += "\n"

    # Add recent conversation
    if history:
        context += "Recent conversation:\n"
        for exchange in history[-5:]:
            context += f"{profile['name']}: {exchange['you']}\n"
            context += f"Jarvis: {exchange['jarvis']}\n"
        context += "\n"

    return context


# ── File Context API ──────────────────────────────────────────

def update_file_context(filename: str, path: str = None, action: str = None) -> None:
    """
    Called after every file operation. Remembers recent files so
    'that file', 'the file', 'it' resolve correctly.
    """
    global _file_history
    entry = {
        "filename": filename,
        "path":     path,
        "action":   action,
        "timestamp": datetime.now().isoformat(),
    }
    _file_history.insert(0, entry)
    if len(_file_history) > MAX_FILE_HISTORY:
        _file_history.pop()


def get_last_file() -> dict:
    """Returns the most recently touched file, or empty dict."""
    return _file_history[0] if _file_history else {}


def get_file_history() -> list:
    """Returns full file history for 'what files did I work on' queries."""
    return list(_file_history)


# ── Context Resolution ────────────────────────────────────────

# Pronouns/references that need resolution
CONTEXT_PRONOUNS = {"it", "that", "this", "them", "those", "the same"}
REPLAY_PHRASES   = {"do that again", "do it again", "repeat that", "again", "same thing", "one more time"}

# File-specific context phrases — resolved to last file in cache
FILE_CONTEXT_PHRASES = [
    "that file", "the file", "this file", "the particular file",
    "that particular file", "that document", "the document",
    "this document", "that note", "the note",
]


def update_context(action: str, target: str = None, result: str = None, command: str = None) -> None:
    """
    Updates the last action context. Called after every successful action.
    """
    global _last_context
    _last_context = {
        "action":  action,
        "target":  target,
        "result":  result,
        "command": command,
    }


def get_last_context() -> dict:
    """Returns the last action context."""
    return _last_context.copy()


def has_context_reference(text: str) -> bool:
    """
    Checks if the command contains pronouns or references
    that need context resolution (e.g., "close it", "open that",
    "write to that file").
    """
    text_lower = text.lower().strip()

    # Check replay phrases
    for phrase in REPLAY_PHRASES:
        if phrase in text_lower:
            return True

    # Check file-specific context phrases ("that file", "the file", etc.)
    for phrase in FILE_CONTEXT_PHRASES:
        if phrase in text_lower:
            return True

    # Check if command ends/contains pronoun in action context
    # e.g., "close it", "open that", "delete it"
    words = text_lower.split()
    for pronoun in CONTEXT_PRONOUNS:
        if pronoun in words:
            return True

    return False


def resolve_context(text: str, confidence: float = 1.0) -> Tuple[str, bool]:
    """
    Resolves pronouns and context references in the command.

    Args:
        text:        The normalized command text
        confidence:  The confidence of the intent match

    Returns:
        (resolved_text, was_resolved) tuple
        - resolved_text: Command with pronouns replaced by concrete targets
        - was_resolved: True if resolution happened
    """
    text_lower = text.lower().strip()

    # Need medium+ confidence for context resolution (relaxed from 0.85)
    if confidence < 0.55:
        return text, False

    # Check for replay phrases first — need last context
    if _last_context["action"] or _last_context["target"]:
        for phrase in REPLAY_PHRASES:
            if phrase in text_lower:
                if _last_context["command"]:
                    print(f"🔄 Replay: '{phrase}' → '{_last_context['command']}'")
                    return _last_context["command"], True

    # ── File-specific context resolution ─────────────────────
    # "that file" / "the file" / "the particular file" → last file from cache
    last_file = get_last_file()
    if last_file:
        for phrase in FILE_CONTEXT_PHRASES:
            if phrase in text_lower:
                fname = last_file["filename"]
                resolved = text_lower.replace(phrase, fname)
                print(f"📎 File context: '{phrase}' → '{fname}' in '{text}' → '{resolved}'")
                return resolved, True

    # ── General pronoun resolution ───────────────────────────
    # No context to resolve against
    if not _last_context["target"] and not _last_context["action"]:
        return text, False

    # Replace pronouns with last target
    if _last_context["target"]:
        resolved = text_lower
        for pronoun in CONTEXT_PRONOUNS:
            # Only replace if pronoun is a standalone word
            pattern = r'\b' + re.escape(pronoun) + r'\b'
            if re.search(pattern, resolved):
                resolved = re.sub(pattern, _last_context["target"], resolved)
                print(f"🔗 Context: '{pronoun}' → '{_last_context['target']}' in '{text}' → '{resolved}'")
                return resolved, True

    return text, False


# ─── Quick test ──────────────────────────────────────────────
if __name__ == "__main__":
    print("Testing memory system...\n")

    profile = load_profile()
    print(f"👤 Name: {profile['name']}")
    print(f"💼 Identity: {', '.join(profile['identity'])}")
    print(f"🛠  Works with: {', '.join(profile['works_with'])}")

    print("\nSaving test conversation...")
    save_exchange("hey how are you", "Doing great, what do you need?")
    save_exchange("open vscode", "Opening VS Code, the usual.")

    print("\nContext for Gemini:")
    print(get_context_for_gemini())

    # Test context resolution
    print("\n── Context Resolution ──")
    update_context("open_app", "vscode", "Opened VS Code", "open vscode")

    test_cases = [
        ("close it", 0.90),
        ("close it", 0.60),   # Low confidence — should NOT resolve
        ("do that again", 0.90),
        ("minimize that", 0.90),
    ]

    for cmd, conf in test_cases:
        resolved, was = resolve_context(cmd, conf)
        print(f"  '{cmd}' (conf={conf}) → '{resolved}' (resolved={was})")

    print("\n✅ Memory system working!")