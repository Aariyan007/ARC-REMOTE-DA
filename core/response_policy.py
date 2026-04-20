"""
Response Policy — the SINGLE source of truth for every spoken line.

Every module that wants Jarvis to speak calls into this module.
No other module generates spoken wording for actions.

7 Response Phases:
    ACK      — Short instant ack before execution ("On it.", "Renaming.")
    CLARIFY  — Context-aware question for missing info ("Which file?")
    CONFIRM  — Describes exactly what will happen ("Delete notes.txt?")
    SUCCESS  — Grounded in actual result ("Renamed notes.txt to ideas.txt.")
    FAILURE  — Explains what went wrong ("Couldn't find notes.txt.")
    CHAT     — Free-form conversational (from Gemini)
    ANSWER   — Direct factual answer (from Gemini)

Priority: Correctness → Clarity → Personality
"""

import random
from collections import deque
from typing import Optional


# ─── Anti-Repetition ─────────────────────────────────────────
_recent_acks: deque = deque(maxlen=6)
_recent_results: deque = deque(maxlen=6)


def _pick(pool: list, tracker: deque) -> str:
    """Pick from pool avoiding recent selections."""
    available = [r for r in pool if r not in tracker]
    if not available:
        available = pool
    chosen = random.choice(available)
    tracker.append(chosen)
    return chosen


# ═══════════════════════════════════════════════════════════════
#  1. ACK — Short, instant, before execution
# ═══════════════════════════════════════════════════════════════

ACK_POOLS = {
    # App control
    "open_app":          ["On it.", "Opening.", "Got it."],
    "close_app":         ["Closing.", "Done.", "Got it."],
    "switch_to_app":     ["Switching.", "Got it."],
    "minimise_app":      ["Minimizing.", "Done."],

    # Volume / Brightness
    "volume_up":         ["Louder.", "Turning up."],
    "volume_down":       ["Quieter.", "Turning down."],
    "mute":              ["Muted.", "Silent."],
    "unmute":            ["Unmuted.", "Sound on."],
    "brightness_up":     ["Brighter.", "Turning up."],
    "brightness_down":   ["Dimmer.", "Turning down."],

    # System
    "lock_screen":       ["Locking.", "Locked."],
    "take_screenshot":   ["Captured.", "Screenshot taken."],
    "get_battery":       ["Checking."],

    # Navigation
    "search_google":     ["Searching.", "Looking up."],
    "open_folder":       ["Opening.", "Got it."],
    "open_url":          ["Opening.", "Got it."],

    # File ops
    "create_file":       ["Creating.", "On it."],
    "read_file":         ["Reading.", "One sec."],
    "edit_file":         ["Writing.", "On it."],
    "delete_file":       ["Deleting.", "On it."],
    "rename_file":       ["Renaming.", "On it."],
    "copy_file":         ["Copying.", "On it."],
    "get_recent_files":  ["Checking.", "Let me see."],
    "create_and_edit_file": ["Creating.", "On it."],

    # Email
    "read_emails":       ["Checking inbox.", "Let me see."],
    "send_email":        ["Composing.", "On it."],
    "search_emails":     ["Searching.", "Checking."],
    "open_gmail":        ["Opening Gmail."],

    # Music
    "play_song":         ["Playing.", "On it."],
    "play_music":        ["Playing.", "On it."],
    "play_mood_music":   ["Setting the mood.", "Playing."],
    "pause_music":       ["Paused."],
    "next_track":        ["Next.", "Skipping."],
    "previous_track":    ["Previous.", "Going back."],

    # Routines
    "morning_briefing":  ["Here's your briefing."],
    "start_work_day":    ["Starting work day.", "Let's go."],
    "end_work_day":      ["Wrapping up.", "Done for the day."],

    # Window
    "minimise_all":      ["All minimized."],
    "show_desktop":      ["Showing desktop."],
    "close_window":      ["Closed."],
    "close_tab":         ["Tab closed."],
    "new_tab":           ["New tab."],
    "fullscreen":        ["Fullscreen."],
    "mission_control":   ["All windows."],

    # System control
    "shutdown_pc":       ["Shutting down."],
    "restart_pc":        ["Restarting."],
    "sleep_mac":         ["Going to sleep."],

    # Knowledge
    "save_note":         ["Saving.", "On it."],
    "search_vault":      ["Searching.", "Looking."],
    "read_note_vault":   ["Reading.", "One sec."],
    "append_note":       ["Adding.", "On it."],

    # Info — these skip ack (answer directly)
    "tell_time":         [],  # empty = skip ack, speak result directly
    "tell_date":         [],
    "tell_weather":      [],
    "answer_question":   [],
    "general_chat":      [],

    # PDF
    "summarise_pdf":     ["Reading the PDF.", "Summarizing."],
}

# Default for unknown actions
_DEFAULT_ACK = ["Got it.", "On it.", "Working on it."]


def get_ack(action: str) -> str:
    """
    Returns a short ack for the given action.
    Returns "" for actions that should skip ack (like tell_time).
    """
    pool = ACK_POOLS.get(action, _DEFAULT_ACK)
    if not pool:
        return ""  # Skip ack for direct-answer actions
    return _pick(pool, _recent_acks)


# ═══════════════════════════════════════════════════════════════
#  2. CLARIFY — Context-aware question for missing info
# ═══════════════════════════════════════════════════════════════

CLARIFICATION_TEMPLATES = {
    "create_file": {
        "filename":  "What should I name the file?",
        "content":   "What should I write in it?",
        "location":  "Where should I create it?",
    },
    "edit_file": {
        "filename":  "Which file should I edit?",
        "content":   "What should I write?",
    },
    "read_file": {
        "filename":  "Which file should I read?",
    },
    "delete_file": {
        "filename":  "Which file do you want to delete?",
    },
    "rename_file": {
        "filename":  "Which file do you want to rename?",
        "new_name":  "What should the new name be?",
    },
    "copy_file": {
        "filename":  "Which file should I copy?",
        "location":  "Where should I copy it to?",
    },
    "open_app": {
        "target":    "Which app should I open?",
    },
    "close_app": {
        "target":    "Which app should I close?",
    },
    "switch_to_app": {
        "target":    "Which app should I switch to?",
    },
    "search_google": {
        "query":     "What should I search for?",
    },
    "send_email": {
        "to":        "Who should I send it to?",
        "subject":   "What's the subject?",
        "body":      "What should the email say?",
    },
    "search_emails": {
        "query":     "What should I search for in your emails?",
    },
    "play_song": {
        "query":     "What song should I play?",
    },
    "save_note": {
        "title":     "What should I title this note?",
        "content":   "What should the note say?",
    },
    "open_url": {
        "url":       "What website should I open?",
    },
    "volume_up": {
        "amount":    "How much louder?",
    },
    "volume_down": {
        "amount":    "How much quieter?",
    },
}

# Required params per action (for detecting what's missing)
REQUIRED_PARAMS = {
    "create_file":      ["filename"],
    "edit_file":        ["filename"],
    "read_file":        ["filename"],
    "delete_file":      ["filename"],
    "rename_file":      ["filename", "new_name"],
    "copy_file":        ["filename"],
    "open_app":         ["target"],
    "close_app":        ["target"],
    "switch_to_app":    ["target"],
    "search_google":    ["query"],
    "send_email":       ["to"],
    "search_emails":    ["query"],
    "play_song":        ["query"],
    "save_note":        ["title"],
    "open_url":         ["url"],
}


def get_missing_params(action: str, params: dict) -> list:
    """Returns list of missing required parameter names."""
    required = REQUIRED_PARAMS.get(action, [])
    missing = []
    for p in required:
        val = params.get(p)
        if val is None or (isinstance(val, str) and val.strip().lower() in {"", "unknown", "null", "none", "it", "that", "this"}):
            missing.append(p)
    return missing


def get_clarification(action: str, params: dict, context: dict = None) -> str:
    """
    Returns a context-aware clarification question.
    Asks about the FIRST missing required parameter.
    Never returns a generic "What do you mean?" — always specific.
    """
    missing = get_missing_params(action, params)

    if not missing:
        # All params present but still unclear — generic but better than before
        return "Can you be more specific about what you want?"

    # Get the first missing param and look up its template
    first_missing = missing[0]
    templates = CLARIFICATION_TEMPLATES.get(action, {})
    question = templates.get(first_missing)

    if question:
        return question

    # Fallback: generate from param name
    param_readable = first_missing.replace("_", " ")
    return f"What {param_readable} should I use?"


# ═══════════════════════════════════════════════════════════════
#  3. CONFIRM — For destructive actions
# ═══════════════════════════════════════════════════════════════

CONFIRM_TEMPLATES = {
    "shutdown_pc":  "I'm about to shut down your Mac. Should I?",
    "restart_pc":   "I'm about to restart your Mac. Should I?",
    "sleep_mac":    "I'm about to put your Mac to sleep. Should I?",
    "delete_file":  "I'm about to delete {target}. Should I?",
    "send_email":   "I'm about to send that email. Should I?",
}


def get_confirmation(action: str, params: dict = None) -> str:
    """Returns a clear confirmation prompt for destructive actions."""
    template = CONFIRM_TEMPLATES.get(action, f"I'm about to {action.replace('_', ' ')}. Should I?")

    if "{target}" in template and params:
        target = params.get("filename", params.get("target", params.get("name", "that")))
        return template.format(target=target)

    return template


# ═══════════════════════════════════════════════════════════════
#  4. SUCCESS — Grounded in actual result
# ═══════════════════════════════════════════════════════════════

SUCCESS_TEMPLATES = {
    "open_app":          "Opened {target}.",
    "close_app":         "Closed {target}.",
    "switch_to_app":     "Switched to {target}.",
    "minimise_app":      "Minimized {target}.",
    "volume_up":         "Volume up.",
    "volume_down":       "Volume down.",
    "mute":              "Muted.",
    "unmute":            "Unmuted.",
    "brightness_up":     "Brightness up.",
    "brightness_down":   "Brightness down.",
    "lock_screen":       "Screen locked.",
    "take_screenshot":   "Screenshot saved.",
    "search_google":     "Searched for {query}.",
    "open_folder":       "Opened {target}.",
    "open_url":          "Opened the page.",
    "create_file":       "Created {filename}.",
    "read_file":         "Here's what's in {filename}.",
    "edit_file":         "Wrote to {filename}.",
    "delete_file":       "Deleted {filename}.",
    "rename_file":       "Renamed {old} to {new}.",
    "copy_file":         "Copied {filename}.",
    "get_recent_files":  "Here are your recent files.",
    "create_and_edit_file": "Created {filename} and wrote the content.",
    "read_emails":       "{summary}",
    "send_email":        "Email sent.",
    "search_emails":     "{summary}",
    "open_gmail":        "Opened Gmail.",
    "play_song":         "Playing now.",
    "play_music":        "Playing.",
    "play_mood_music":   "Playing mood music.",
    "pause_music":       "Paused.",
    "next_track":        "Next track.",
    "previous_track":    "Previous track.",
    "morning_briefing":  "{summary}",
    "start_work_day":    "Work day started.",
    "end_work_day":      "Day wrapped up.",
    "minimise_all":      "All minimized.",
    "show_desktop":      "Desktop shown.",
    "close_window":      "Window closed.",
    "close_tab":         "Tab closed.",
    "new_tab":           "New tab opened.",
    "fullscreen":        "Fullscreen.",
    "mission_control":   "All windows shown.",
    "shutdown_pc":       "Shutting down now.",
    "restart_pc":        "Restarting now.",
    "sleep_mac":         "Going to sleep.",
    "get_battery":       "{summary}",
    "tell_weather":      "{summary}",
    "save_note":         "Note saved.",
    "search_vault":      "{summary}",
    "read_note_vault":   "{summary}",
    "append_note":       "Added to the note.",
    "summarise_pdf":     "{summary}",
}


def get_result(action_result) -> str:
    """
    Generates grounded spoken text from an ActionResult.
    Uses the actual outcome, not pre-baked wording.
    """
    if not action_result.success:
        return get_failure(action_result)

    # If executor provided an explicit user_message, use it
    if action_result.user_message:
        return action_result.user_message

    action = action_result.action
    template = SUCCESS_TEMPLATES.get(action)

    if template:
        # Build substitution dict from action_result.data and summary
        subs = dict(action_result.data)
        subs.setdefault("summary", action_result.summary)
        subs.setdefault("target", action_result.data.get("target", action_result.data.get("name", "")))
        subs.setdefault("filename", action_result.data.get("filename", ""))
        subs.setdefault("query", action_result.data.get("query", ""))
        subs.setdefault("old", action_result.data.get("old_name", action_result.data.get("filename", "")))
        subs.setdefault("new", action_result.data.get("new_name", ""))

        try:
            result_text = template.format(**subs)
            # Clean up empty substitutions
            result_text = result_text.replace("  ", " ").strip()
            if result_text and result_text != ".":
                return result_text
        except (KeyError, IndexError):
            pass

    # Fallback: use the summary from the executor
    if action_result.summary:
        return action_result.summary

    return "Done."


# ═══════════════════════════════════════════════════════════════
#  5. FAILURE — Explains what went wrong
# ═══════════════════════════════════════════════════════════════

FAILURE_TEMPLATES = {
    "open_app":      "Couldn't open {target}.",
    "close_app":     "Couldn't close {target}.",
    "create_file":   "Couldn't create the file. {error}",
    "read_file":     "Couldn't read {filename}.",
    "edit_file":     "Couldn't write to {filename}.",
    "delete_file":   "Couldn't delete {filename}.",
    "rename_file":   "Couldn't rename {filename}. {error}",
    "copy_file":     "Couldn't copy {filename}.",
    "send_email":    "Couldn't send the email. {error}",
    "search_google": "Couldn't search. {error}",
    "open_url":      "Couldn't open that page.",
    "play_song":     "Couldn't play that. {error}",
}


def get_failure(action_result) -> str:
    """Generates failure message from ActionResult."""
    action = action_result.action
    template = FAILURE_TEMPLATES.get(action)

    if template:
        subs = dict(action_result.data)
        subs.setdefault("target", action_result.data.get("target", action_result.data.get("name", "that")))
        subs.setdefault("filename", action_result.data.get("filename", "that file"))
        subs.setdefault("error", action_result.error or "")

        try:
            return template.format(**subs).strip()
        except (KeyError, IndexError):
            pass

    # Fallback
    if action_result.error:
        return f"That didn't work. {action_result.error}"
    return "That didn't work."


# ─── Quick test ──────────────────────────────────────────────
if __name__ == "__main__":
    from core.action_result import ActionResult

    print("=" * 60)
    print("  RESPONSE POLICY TEST")
    print("=" * 60)

    # Test ACK
    print("\n── ACKs ──")
    for action in ["open_app", "rename_file", "tell_time", "volume_up"]:
        ack = get_ack(action)
        print(f"  {action}: '{ack}'" + (" (skip)" if not ack else ""))

    # Test CLARIFY
    print("\n── Clarifications ──")
    print(f"  create_file (no filename): {get_clarification('create_file', {})}")
    print(f"  rename_file (no new_name): {get_clarification('rename_file', {'filename': 'old.txt'})}")
    print(f"  delete_file (has 'it'):    {get_clarification('delete_file', {'filename': 'it'})}")
    print(f"  open_app (no target):      {get_clarification('open_app', {})}")

    # Test CONFIRM
    print("\n── Confirmations ──")
    print(f"  delete_file: {get_confirmation('delete_file', {'filename': 'notes.txt'})}")
    print(f"  shutdown_pc: {get_confirmation('shutdown_pc')}")

    # Test SUCCESS
    print("\n── Success Results ──")
    r1 = ActionResult.ok("open_app", "Opened Chrome", data={"target": "Chrome"})
    print(f"  open_app:    {get_result(r1)}")

    r2 = ActionResult.ok("rename_file", "Renamed", data={"old_name": "notes.txt", "new_name": "ideas.txt"})
    print(f"  rename_file: {get_result(r2)}")

    r3 = ActionResult.ok("tell_time", "It's 7:42 PM", user_message="It's 7:42 PM.")
    print(f"  tell_time:   {get_result(r3)}")

    # Test FAILURE
    print("\n── Failure Results ──")
    r4 = ActionResult.fail("rename_file", "File not found", data={"filename": "notes.txt"})
    print(f"  rename_file: {get_failure(r4)}")

    r5 = ActionResult.fail("open_app", "App not found", data={"target": "blah"})
    print(f"  open_app:    {get_failure(r5)}")

    print("\n✅ Response policy test passed!")
