"""
Structured interpretation layer — bridges fast intent / LLM into InterpretedCommand.

Wire this into intent_router as the single place that produces action/target/params.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, List, Optional

from core.command_schema import InterpretedCommand, MachineContext, RequiredState
from core.perception_engine import PerceptionState

# ── Phase 1: Target-Type Inference ───────────────────────────
# Classifies what the user is referring to so the pipeline doesn't
# misroute (e.g., "youtube" as app vs. browser search).

# Known app names for target-type inference
_APP_NAMES = {
    "vscode", "chrome", "safari", "firefox", "terminal", "finder",
    "spotify", "slack", "discord", "zoom", "notes", "music",
    "edge", "brave", "sublime", "pycharm", "intellij", "xcode",
    "cmd", "powershell", "word", "excel", "powerpoint",
    "photoshop", "illustrator", "figma", "sketch", "gimp",
    "calculator", "calendar", "preview", "pages", "numbers",
    "keynote", "iterm", "warp", "obs", "vlc", "steam",
}

# Website patterns — if these appear, the target is a website/browser action
_WEBSITE_PATTERNS = [
    r'\b(?:youtube|google|reddit|twitter|facebook|instagram|github|stackoverflow)\b',
    r'\b(?:netflix|amazon|linkedin|pinterest|twitch|tiktok|wikipedia|medium)\b',
    r'\bhttps?://',
    r'\b\w+\.(?:com|org|net|io|dev|co|app)\b',
]

# Keywords that indicate different target types
_TARGET_TYPE_SIGNALS = {
    "file": ["file", "pdf", "txt", "docx", "csv", "json", "script", "readme"],
    "folder": ["folder", "directory", "downloads folder", "documents folder",
              "desktop folder", "open downloads", "open documents", "open my"],
    "email": ["email", "mail", "inbox", "send to", "compose", "reply to"],
    "tab": ["tab", "browser tab", "this tab", "that tab", "current tab"],
    "note": ["note", "vault", "obsidian", "brain", "remember", "memo", "jot"],
    "website": ["website", "webpage", "web page", "site", "url", "browse to",
               "go to", "visit", "navigate to"],
    "browser_search": ["search for", "look up", "google", "find online",
                       "search online", "search how", "find "],
}

# Verb+context patterns that override simple name matching
_VIDEO_WATCH_PATTERNS = [
    r'\bwatch\b.*\byoutube\b',
    r'\byoutube\b.*\bvideo\b',
    r'\bwatch\b.*\bvideo\b',
    r'\bstream\b',
    r'\bplay\b.*\bon\s+(?:youtube|twitch|netflix)\b',
    r'\bwatch\b.*\b(?:youtube|netflix|twitch|hulu)\b',
]


def infer_target_type(text: str, action: str = "") -> str:
    """
    Infer what kind of target the user is referring to.

    Returns one of: app, file, folder, website, browser_search, tab, email, note, unknown

    Examples:
        "open chrome"                    → app
        "create a file called notes"     → file
        "watch videos on youtube"        → website (not app!)
        "search for python tutorials"    → browser_search
        "send this to john"              → email
        "that tab"                       → tab
    """
    text_lower = text.lower()

    # 1. Check video/watch patterns first — these override app detection
    for pattern in _VIDEO_WATCH_PATTERNS:
        if re.search(pattern, text_lower):
            return "website"

    # 2. Action-based inference (if we already know the action)
    action_type_map = {
        "create_file": "file", "edit_file": "file", "read_file": "file",
        "delete_file": "file", "rename_file": "file", "copy_file": "file",
        "create_folder": "folder", "open_folder": "folder",
        "search_google": "browser_search",
        "open_url": "website",
        "send_email": "email", "read_emails": "email", "search_emails": "email",
        "save_note": "note", "search_vault": "note", "append_note": "note",
        "open_app": "app", "close_app": "app", "switch_to_app": "app",
        "close_tab": "tab", "new_tab": "tab",
    }
    if action in action_type_map:
        return action_type_map[action]

    # 3. File extension check — if a filename with extension is present,
    #    it's definitely a file operation (overrides keyword signals like "note")
    if re.search(r'\b\w+\.(?:py|txt|md|json|js|ts|html|css|yaml|yml|xml|csv|sql|sh|bat|log|cfg|ini|toml|rs|go|java|c|h|cpp|rb)\b', text_lower):
        return "file"

    # 4. Keyword-based inference from text
    for target_type, keywords in _TARGET_TYPE_SIGNALS.items():
        for kw in keywords:
            if kw in text_lower:
                return target_type

    # 4. Website pattern matching
    for pattern in _WEBSITE_PATTERNS:
        if re.search(pattern, text_lower):
            # But only if it's not clearly an app-open command
            if not any(v in text_lower for v in ["open", "launch", "start"]):
                return "website"
            # "open youtube" could be app OR website — check context
            for app in _APP_NAMES:
                if app in text_lower:
                    return "app"
            return "website"

    # 5. Check if it's a known app name
    for app in _APP_NAMES:
        if app in text_lower:
            return "app"

    return "unknown"


def build_machine_context(
    perception: Optional[PerceptionState] = None,
    *,
    last_file: Optional[str] = None,
    recent_actions: Optional[List[str]] = None,
    browser_url: Optional[str] = None,
    browser_title: Optional[str] = None,
    visual_summary: Optional[str] = None,
) -> MachineContext:
    """Fold live perception + memory hooks into one interpreter input."""
    if perception is None:
        ctx = MachineContext(
            last_file=last_file,
            recent_actions=list(recent_actions or []),
            browser_url=browser_url,
            browser_title=browser_title,
            visual_summary=visual_summary,
        )
    else:
        ctx = MachineContext(
            active_app=perception.active_app,
            active_window=perception.active_window,
            idle_seconds=perception.idle_seconds,
            system_state=perception.system_state,
            last_file=last_file,
            recent_actions=list(recent_actions or []),
            browser_url=browser_url,
            browser_title=browser_title,
            visual_summary=visual_summary,
        )
    if not ctx.browser_url or not ctx.browser_title:
        try:
            from perception.browser_state import get_browser_tabs

            tabs = get_browser_tabs()
            if tabs:
                cur = next((t for t in tabs if t.active), tabs[0])
                if not ctx.browser_url:
                    ctx.browser_url = cur.url or None
                if not ctx.browser_title:
                    ctx.browser_title = cur.title or None
        except Exception:
            pass
    return ctx


STRUCTURED_JSON_INSTRUCTIONS = """
Return ONLY one JSON object (no markdown) with keys:
  "action" (string),
  "target" (string or null),
  "params" (object),
  "required_state" (object with optional "preconditions" and "postconditions" objects),
  "confidence" (number 0-1),
  "ambiguities" (array of short strings, empty if none),
  "natural_response" (short string the assistant may speak).

Ground your answer in the MACHINE CONTEXT block; if unsure, lower confidence and list ambiguities.
"""


def interpret_from_fast_intent(
    action: str,
    confidence: float,
    *,
    source: str = "fast_intent",
    target: Optional[str] = None,
    params: Optional[dict[str, Any]] = None,
    ambiguities: Optional[list[str]] = None,
    text: str = "",
) -> InterpretedCommand:
    """Map embedding / cross-encoder output into the shared schema."""
    target_type = infer_target_type(text, action) if text else None
    return InterpretedCommand(
        action=action,
        target=target,
        params=dict(params or {}),
        required_state=RequiredState(),
        confidence=float(confidence),
        ambiguities=list(ambiguities or []),
        natural_response=None,
        source=source,
        target_type=target_type,
    )


def _parse_json_object(text: str) -> dict[str, Any]:
    clean = text.strip()
    clean = re.sub(r"^```(?:json)?\s*", "", clean, flags=re.IGNORECASE)
    clean = re.sub(r"\s*```$", "", clean)
    data = json.loads(clean)
    if not isinstance(data, dict):
        raise ValueError("LLM output is not a JSON object")
    return data


def _mapping_to_interpreted(data: dict[str, Any], *, source: str) -> InterpretedCommand:
    rs = data.get("required_state") or {}
    if not isinstance(rs, dict):
        rs = {}
    pre = rs.get("preconditions") if isinstance(rs.get("preconditions"), dict) else {}
    post = rs.get("postconditions") if isinstance(rs.get("postconditions"), dict) else {}
    params = data.get("params") if isinstance(data.get("params"), dict) else {}
    amb = data.get("ambiguities")
    if amb is None:
        amb_list: list[str] = []
    elif isinstance(amb, list):
        amb_list = [str(x) for x in amb]
    else:
        amb_list = [str(amb)]
    conf = float(data.get("confidence", 0.5))
    return InterpretedCommand(
        action=str(data.get("action", "general_chat")),
        target=data.get("target") if data.get("target") is not None else None,
        params=params,
        required_state=RequiredState(preconditions=dict(pre or {}), postconditions=dict(post or {})),
        confidence=conf,
        ambiguities=amb_list,
        natural_response=data.get("natural_response"),
        source=source,
    )


def interpret_with_structured_llm(
    user_text: str,
    context: MachineContext,
    *,
    model: Optional[str] = None,
) -> InterpretedCommand:
    """
    Optional Gemini path: produces InterpretedCommand from strict JSON.
    Requires API_KEY in environment (same as core.llm_brain).
    """
    api_key = os.getenv("API_KEY")
    if not api_key:
        return InterpretedCommand(
            action="general_chat",
            target=None,
            params={"reason": "no API_KEY"},
            confidence=0.0,
            ambiguities=["LLM interpreter unavailable (missing API_KEY)."],
            natural_response="I can't run the structured interpreter without an API key.",
            source="llm_structured_unavailable",
        )

    from google import genai

    client = genai.Client(api_key=api_key)
    model_name = model or os.getenv("GEMINI_STRUCTURED_MODEL", "gemini-2.0-flash")

    prompt = (
        STRUCTURED_JSON_INSTRUCTIONS
        + "\n\nMACHINE CONTEXT:\n"
        + context.to_prompt_block()
        + "\n\nUSER:\n"
        + user_text.strip()
    )

    try:
        response = client.models.generate_content(model=model_name, contents=prompt)
        text = (response.text or "").strip()
        data = _parse_json_object(text)
        return _mapping_to_interpreted(data, source="llm_structured")
    except Exception as e:
        return InterpretedCommand(
            action="general_chat",
            target=None,
            params={"error": str(e)},
            confidence=0.0,
            ambiguities=["Structured LLM parse failed."],
            natural_response=None,
            source="llm_structured_error",
        )


def interpret_command(
    normalized_text: str,
    context: MachineContext,
    *,
    fast_action: Optional[str] = None,
    fast_confidence: float = 0.0,
    fast_target: Optional[str] = None,
    fast_params: Optional[dict[str, Any]] = None,
    ambiguities: Optional[list[str]] = None,
    use_llm: bool = False,
) -> InterpretedCommand:
    """
    Default entry: use fast path mapping when provided; optionally augment with LLM.
    """
    if use_llm:
        return interpret_with_structured_llm(normalized_text, context)
    if fast_action:
        return interpret_from_fast_intent(
            fast_action,
            fast_confidence,
            source="fast_intent",
            target=fast_target,
            params=fast_params,
            ambiguities=ambiguities,
            text=normalized_text,
        )
    return InterpretedCommand(
        action="unknown",
        confidence=0.0,
        ambiguities=["No fast intent and LLM disabled."],
        source="none",
    )
