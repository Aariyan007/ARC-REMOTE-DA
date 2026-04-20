"""
Ambiguity Resolver — single-slot clarification with priority ordering.

When confidence is medium or params are missing, prefer a short
focused clarification over a wrong guess.

Phase 1 upgrade:
- build_single_slot_question(): asks about the ONE most critical missing param
- Priority ordering per action (e.g., filename > location > content)
- Never asks generic "what do you mean?" — always action+slot specific
- Returns both question text AND which param it's asking about (for task_state)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from core.command_schema import InterpretedCommand


@dataclass
class DisambiguationPrompt:
    """One question the user can answer (voice or text)."""

    question: str
    options: list[str]


# ── Phase 1: Param Priority Ordering ────────────────────────
# For each action, which missing param should be asked FIRST.
# The first item in the list is the most critical.
PARAM_PRIORITY = {
    "create_file":      ["filename", "location", "content"],
    "edit_file":        ["filename", "content"],
    "read_file":        ["filename"],
    "delete_file":      ["filename"],
    "rename_file":      ["filename", "new_name"],
    "copy_file":        ["filename", "location"],
    "open_app":         ["target"],
    "close_app":        ["target"],
    "switch_to_app":    ["target"],
    "minimise_app":     ["target"],
    "search_google":    ["query"],
    "send_email":       ["to", "subject", "body"],
    "search_emails":    ["query"],
    "play_song":        ["query"],
    "save_note":        ["title", "content"],
    "append_note":      ["title", "content"],
    "open_url":         ["url"],
    "create_folder":    ["target"],
    "open_folder":      ["target"],
}

# ── Phase 1: Clarification Templates ────────────────────────
# Focused, never-generic questions for each action+param combo.
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
    "minimise_app": {
        "target":    "Which app should I minimize?",
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
    "append_note": {
        "title":     "Which note should I add to?",
        "content":   "What should I add?",
    },
    "open_url": {
        "url":       "What website should I open?",
    },
    "create_folder": {
        "target":    "What should I name the folder?",
    },
    "open_folder": {
        "target":    "Which folder should I open?",
    },
    "volume_up": {
        "amount":    "How much louder?",
    },
    "volume_down": {
        "amount":    "How much quieter?",
    },
}


def should_disambiguate(
    cmd: InterpretedCommand,
    *,
    low: float = 0.40,
    high: float = 0.72,
) -> bool:
    """True if confidence sits in the 'uncertain' band or explicit ambiguities exist."""
    if cmd.ambiguities:
        return True
    return low <= cmd.confidence < high


def build_disambiguation_prompt(cmd: InterpretedCommand) -> Optional[DisambiguationPrompt]:
    """
    Produce a minimal clarification from structured fields.
    Extend with domain-specific templates as the schema grows.
    """
    action = (cmd.action or "").lower()
    target = (cmd.target or "").strip()

    if cmd.ambiguities:
        opts = []
        for line in cmd.ambiguities[:4]:
            if ":" in line:
                opts.append(line.split(":", 1)[-1].strip())
            else:
                opts.append(line.strip())
        opts = [o for o in opts if o] or ["cancel"]
        return DisambiguationPrompt(
            question="I need a quick clarification — which did you mean?",
            options=opts[:6],
        )

    if action in ("open_app", "switch_to_app") and target in (
        "chrome",
        "google chrome",
        "safari",
        "firefox",
        "edge",
        "brave",
    ):
        return DisambiguationPrompt(
            question=f"For {target}: open a new window, or switch to an existing one?",
            options=["open", "switch", "cancel"],
        )

    if action in ("open_app",) and not target:
        return DisambiguationPrompt(
            question="Which app should I open?",
            options=["cancel"],
        )

    return None


# ── Phase 1: Single-Slot Clarification ──────────────────────

def get_most_critical_missing(action: str, params: dict, missing_params: list) -> Optional[str]:
    """
    Given a list of missing params, return the single most critical one
    to ask about, based on the priority ordering for this action.

    Returns the param name, or None if nothing is missing.
    """
    if not missing_params:
        return None

    priority = PARAM_PRIORITY.get(action, [])

    # Return the first missing param that appears in priority order
    for param in priority:
        if param in missing_params:
            return param

    # If action isn't in priority map, just return the first missing
    return missing_params[0]


def build_single_slot_question(
    action: str,
    params: dict,
    missing_params: list,
    grounding_context: dict | None = None,
) -> Tuple[Optional[str], Optional[str]]:
    """
    Build a single focused clarification question for the most critical
    missing parameter.

    Args:
        action:            The action to ask about
        params:            Already-known params
        missing_params:    List of param names that are missing
        grounding_context: Optional dict with keys like 'parent_target',
                           'parent_action' from a prior step in a task chain.
                           Used to generate grounded questions like
                           "What should I name the file inside my_projects?"

    Returns:
        (question_text, param_name) -- the question to ask and which param it fills.
        (None, None) if nothing is missing.

    This is the Phase 1 "one-question clarification policy":
    - Ask only the smallest next question
    - Never ask generic "what do you mean?"
    - Always ask about the most critical missing slot first
    - When grounding_context is present, reference the prior result
    """
    param_name = get_most_critical_missing(action, params, missing_params)
    if param_name is None:
        return None, None

    # Look up the template
    templates = CLARIFICATION_TEMPLATES.get(action, {})
    question = templates.get(param_name)

    # If we have grounding context from a prior step, make the question
    # reference it so the user knows what ARC is talking about.
    if grounding_context and question:
        parent_target = grounding_context.get("parent_target", "")
        parent_action = grounding_context.get("parent_action", "")
        if parent_target:
            # Map parent action to a readable location descriptor
            _LOCATION_WORDS = {
                "create_folder": "inside",
                "open_folder":   "in",
                "create_file":   "for",
            }
            location_word = _LOCATION_WORDS.get(parent_action, "in")
            question = f"{question.rstrip('?')} {location_word} {parent_target}?"

    if question:
        return question, param_name

    # Fallback: generate from param name (still specific, never generic)
    param_readable = param_name.replace("_", " ")
    parent_target = (grounding_context or {}).get("parent_target", "")
    if parent_target:
        return f"What {param_readable} should I use for {parent_target}?", param_name
    return f"What {param_readable} should I use?", param_name


# ─── Quick Test ──────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')

    print("=" * 60)
    print("  AMBIGUITY RESOLVER TEST")
    print("=" * 60)

    # Test 1: Single slot question
    print("\n-- Single Slot Questions --")
    test_cases = [
        ("create_file", {}, ["filename", "location"]),
        ("rename_file", {"filename": "old.txt"}, ["new_name"]),
        ("send_email", {}, ["to", "subject", "body"]),
        ("edit_file", {"filename": "notes.txt"}, ["content"]),
        ("open_app", {}, ["target"]),
        ("search_google", {}, ["query"]),
        ("create_folder", {}, ["target"]),
    ]

    for action, params, missing in test_cases:
        question, param = build_single_slot_question(action, params, missing)
        print(f"  {action} (missing: {missing})")
        print(f"    → Asks about: {param}")
        print(f"    → Question: \"{question}\"")
        print()

    # Test 2: Priority ordering
    print("-- Priority Ordering --")
    param = get_most_critical_missing("send_email", {}, ["body", "to", "subject"])
    assert param == "to", f"Expected 'to' first, got '{param}'"
    print(f"  send_email missing [body, to, subject] -> asks about '{param}' first [PASS]")

    param = get_most_critical_missing("create_file", {}, ["content", "filename"])
    assert param == "filename", f"Expected 'filename' first, got '{param}'"
    print(f"  create_file missing [content, filename] -> asks about '{param}' first [PASS]")

    print("\n[PASS] Ambiguity resolver test passed!")
