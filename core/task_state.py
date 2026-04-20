"""
Task State — Pending clarification state manager.

When ARC asks a follow-up question (e.g., "What should I name the file?"),
this module stores what was being done so the user's short answer can
resume the original task instead of being treated as a brand-new command.

Example flow:
    User: "dude make a stupid file"
    ARC:  stores PendingTask(action="create_file", missing_param="filename")
    ARC:  speaks "What should I name the file?"
    User: "notes"
    ARC:  detects pending → fills filename="notes" → resumes create_file

Expiry: 30 seconds. If the user says something completely different
with high intent confidence, the pending state is cleared.
"""

from __future__ import annotations

import time
import threading
from dataclasses import dataclass, field, asdict
from typing import Optional


# ─── Settings ────────────────────────────────────────────────
PENDING_TTL_SECONDS = 30.0       # Pending task expires after this
SHORT_ANSWER_MAX_WORDS = 5       # Answers longer than this are treated as new commands
# ─────────────────────────────────────────────────────────────


@dataclass
class PendingTask:
    """A task that ARC started but paused to ask a clarification question."""

    action: str                              # e.g., "create_file"
    known_params: dict = field(default_factory=dict)  # params already extracted
    missing_param: str = ""                  # the one param we asked about
    question_asked: str = ""                 # what ARC said to the user
    original_command: str = ""               # raw user command
    normalized_command: str = ""             # cleaned version
    timestamp: float = 0.0                   # when the pending task was created
    intent_source: str = ""                  # "builtin" | "learned" | "gemini"
    confidence: float = 0.0                  # intent confidence at time of pause
    # Phase 1 fix [P2]: Multi-step continuity
    follow_up_action: str = ""               # next action to chain after this one completes
    follow_up_params: dict = field(default_factory=dict)  # params for the follow-up action

    def is_expired(self) -> bool:
        """Check if this pending task has timed out."""
        return (time.time() - self.timestamp) > PENDING_TTL_SECONDS

    def to_dict(self) -> dict:
        return asdict(self)


# ─── Module-level state ─────────────────────────────────────
_pending: Optional[PendingTask] = None
_lock = threading.Lock()


def set_pending(task: PendingTask) -> None:
    """Store a pending task. Overwrites any existing pending task."""
    global _pending
    with _lock:
        task.timestamp = time.time()
        _pending = task
    print(f"⏸️  Pending task set: {task.action} (missing: {task.missing_param})")


def get_pending() -> Optional[PendingTask]:
    """
    Returns the current pending task, or None if expired/absent.
    Automatically clears expired tasks.
    """
    global _pending
    with _lock:
        if _pending is None:
            return None
        if _pending.is_expired():
            print(f"⏰ Pending task expired: {_pending.action}")
            _pending = None
            return None
        return _pending


def clear_pending() -> None:
    """Clear any pending task."""
    global _pending
    with _lock:
        if _pending:
            print(f"🧹 Pending task cleared: {_pending.action}")
        _pending = None


def has_pending() -> bool:
    """Quick check: is there a non-expired pending task?"""
    return get_pending() is not None


# ── New-command detection words ──────────────────────────────
# If the user's response contains these action-like words,
# it's probably a new command, not an answer to the pending question.
_NEW_COMMAND_INDICATORS = {
    "open", "close", "create", "delete", "search", "play",
    "shut", "restart", "lock", "mute", "unmute",
    "volume", "brightness", "screenshot", "minimize",
    "switch", "rename", "copy", "send", "read",
    "what time", "what date", "what's the", "how much",
    "tell me", "show me",
}

# Cancellation words — user wants to abandon the pending task
_CANCEL_WORDS = {
    "cancel", "nevermind", "never mind", "forget it",
    "stop", "abort", "no", "nope", "skip",
}


def is_pending_answer(text: str) -> bool:
    """
    Determine if the user's input is likely an answer to the pending
    clarification question, rather than a completely new command.

    Heuristics:
    1. Short inputs (≤ SHORT_ANSWER_MAX_WORDS) are almost always answers
    2. Inputs that contain action verbs are likely new commands
    3. Cancellation words clear the pending state

    Returns True if this looks like an answer to the pending question.
    """
    if not text or not text.strip():
        return False

    pending = get_pending()
    if pending is None:
        return False

    text_lower = text.strip().lower()
    words = text_lower.split()

    # Check for cancellation (word-boundary match, not substring)
    words_set = set(words)
    for cancel in _CANCEL_WORDS:
        if " " in cancel:
            # Multi-word cancellation phrase: check as substring
            if cancel in text_lower:
                clear_pending()
                return False
        else:
            # Single word: must be standalone word
            if cancel in words_set:
                clear_pending()
                return False

    # Short answers are almost always responses to the question
    if len(words) <= SHORT_ANSWER_MAX_WORDS:
        # But check if it's obviously a new command
        for indicator in _NEW_COMMAND_INDICATORS:
            if text_lower.startswith(indicator):
                return False
        return True

    # Longer inputs — check if they look like new commands
    for indicator in _NEW_COMMAND_INDICATORS:
        if indicator in text_lower:
            return False

    # Default: if it's not clearly a new command, treat as answer
    return True


def resume_with_answer(answer: str) -> Optional[dict]:
    """
    Fill in the missing parameter from the pending task with the user's answer.

    Returns a dict with:
        action: str
        params: dict (complete, with the missing param filled in)
        original_command: str
        intent_source: str
        confidence: float

    Returns None if no pending task or answer is empty.
    """
    pending = get_pending()
    if pending is None:
        return None

    answer = answer.strip()
    if not answer:
        clear_pending()
        return None

    # Fill in the missing parameter
    params = dict(pending.known_params)
    params[pending.missing_param] = answer

    # For file operations, also set common aliases
    if pending.missing_param == "filename":
        params["filename"] = answer
    elif pending.missing_param == "target":
        params["target"] = answer
        params["name"] = answer
    elif pending.missing_param == "query":
        params["query"] = answer

    result = {
        "action": pending.action,
        "params": params,
        "original_command": pending.original_command,
        "normalized_command": pending.normalized_command,
        "intent_source": pending.intent_source,
        "confidence": pending.confidence,
    }

    clear_pending()
    return result


# ─── Follow-up Intent Detection ─────────────────────────────
# Splits compound commands like "make a folder and then write in it"
# into (primary_clause, follow_up_action, follow_up_params).

import re

# Conjunction patterns that split a compound command into two clauses.
# Order matters — longer patterns first to avoid partial matches.
_FOLLOW_UP_SPLITTERS = [
    r"\s*,?\s*and\s+then\s+",         # "and then"
    r"\s*,?\s*then\s+",               # "then"
    r"\s*,?\s*after\s+that\s+",       # "after that"
    r"\s*,?\s*(?:i\s+)?(?:want\s+to|wanna)\s+",  # ", I want to" / ", wanna"
    r"\s*,?\s*(?:i\s+)?(?:need\s+to)\s+",         # ", I need to"
    r"\s*,?\s*also\s+",               # "also"
    r"\s*;\s*",                        # semicolon separator
]

# Maps verb phrases in the follow-up clause to action names + param extraction.
_FOLLOW_UP_VERB_MAP = [
    # (regex_pattern, action, param_key_for_capture_group)
    (r"(?:write|put|type|add)\s+(.+?)(?:\s+in\s+it)?$", "edit_file", "content"),
    (r"(?:open)\s+(?:it|that|the\s+\w+)$", "open_app", None),
    (r"(?:rename)\s+(?:it|that)\s+(?:to\s+)?(.+)$", "rename_file", "new_name"),
    (r"(?:delete|remove)\s+(?:it|that)$", "delete_file", None),
    (r"(?:read|view|look\s+at)\s+(?:it|that)$", "read_file", None),
    (r"(?:copy)\s+(?:it|that)(?:\s+to\s+(.+))?$", "copy_file", "destination"),
    (r"(?:move)\s+(?:it|that)\s+to\s+(.+)$", "move_file", "destination"),
    (r"(?:send)\s+(?:it|that)(?:\s+to\s+(.+))?$", "send_email", "to"),
    (r"(?:search|find|look)\s+(?:for\s+)?(.+)$", "search_google", "query"),
    (r"(?:edit)\s+(?:it|that)$", "edit_file", None),
]


def detect_follow_up_intent(text: str) -> tuple[str, str, dict]:
    """
    Detect if a command contains a follow-up intent after a conjunction.

    Examples:
        "make a folder and then write hello in it"
        → ("make a folder", "edit_file", {"content": "hello"})

        "create a file, I want to put my notes in it"
        → ("create a file", "edit_file", {"content": "my notes"})

        "open vscode and then open chrome"
        → ("open vscode", "open_app", {})

    Returns:
        (primary_clause, follow_up_action, follow_up_params)
        If no follow-up detected: (original_text, "", {})
    """
    text_lower = text.strip().lower()

    for splitter in _FOLLOW_UP_SPLITTERS:
        match = re.search(splitter, text_lower)
        if not match:
            continue

        primary = text_lower[:match.start()].strip()
        follow_clause = text_lower[match.end():].strip()

        if not primary or not follow_clause:
            continue

        # Try to match the follow-up clause to a known verb pattern
        for pattern, action, param_key in _FOLLOW_UP_VERB_MAP:
            verb_match = re.match(pattern, follow_clause)
            if verb_match:
                params = {}
                if param_key and verb_match.lastindex and verb_match.lastindex >= 1:
                    captured = verb_match.group(1).strip()
                    if captured:
                        params[param_key] = captured
                return (primary, action, params)

    return (text, "", {})

if __name__ == "__main__":
    import sys
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')

    print("=" * 60)
    print("  TASK STATE TEST")
    print("=" * 60)

    # Test 1: Set and retrieve pending task
    print("\n-- Set Pending --")
    task = PendingTask(
        action="create_file",
        known_params={"location": "desktop"},
        missing_param="filename",
        question_asked="What should I name the file?",
        original_command="dude make a stupid file",
        normalized_command="make file",
    )
    set_pending(task)

    p = get_pending()
    assert p is not None, "Pending should exist"
    assert p.action == "create_file"
    print(f"  [PASS] Pending: {p.action} (missing: {p.missing_param})")

    # Test 2: is_pending_answer
    print("\n-- Is Pending Answer --")
    assert is_pending_answer("notes") is True, "Short answer should be pending answer"
    assert is_pending_answer("project notes") is True, "Two-word answer should be pending answer"
    assert is_pending_answer("open chrome") is False, "New command should NOT be pending answer"
    assert is_pending_answer("search for python") is False, "New command should NOT be pending answer"
    print("  [PASS] All is_pending_answer checks passed")

    # Test 3: Resume with answer
    print("\n-- Resume With Answer --")
    set_pending(task)
    result = resume_with_answer("project_notes")
    assert result is not None
    assert result["action"] == "create_file"
    assert result["params"]["filename"] == "project_notes"
    print(f"  [PASS] Resumed: {result['action']} with {result['params']}")

    # Test 4: Pending should be cleared after resume
    assert get_pending() is None, "Pending should be cleared after resume"
    print("  [PASS] Pending cleared after resume")

    # Test 5: Cancellation
    print("\n-- Cancellation --")
    set_pending(task)
    assert is_pending_answer("nevermind") is False, "Cancel should not be answer"
    assert get_pending() is None, "Pending should be cleared after cancel"
    print("  [PASS] Cancel clears pending")

    # Test 6: Expiry
    print("\n-- Expiry --")
    expired_task = PendingTask(
        action="create_file",
        missing_param="filename",
        timestamp=time.time() - 60,
    )
    import core.task_state as _ts_mod
    with _lock:
        _ts_mod._pending = expired_task
    assert get_pending() is None, "Expired task should return None"
    print("  [PASS] Expired task auto-cleared")

    print("\n[PASS] Task state test passed!")

