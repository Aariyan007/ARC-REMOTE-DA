"""
Fast Intent Engine — embedding-based intent classification.

Replaces the static INSTANT_CACHE with a semantic similarity engine.
Uses sentence-transformers (all-MiniLM-L6-v2) for embeddings.
Runs in ~5-15ms on CPU. No LLM call needed.

Pipeline:
    normalized_text → embed → cosine_similarity(all_intents) → best_match
"""

import os
import sys
import json
import warnings
import numpy as np
from typing import Optional
from dataclasses import dataclass

# Suppress torchcodec FFmpeg errors (not needed for embeddings)
os.environ.setdefault("TORCHCODEC_DISABLE_LOAD", "1")
warnings.filterwarnings("ignore", message=".*torchcodec.*")
warnings.filterwarnings("ignore", message=".*FFmpeg.*")

# Lazy load to avoid slow import at startup
_model = None
_intent_embeddings = None   # { action: np.array of shape (N, dim) }
_intent_examples   = None   # { action: [example1, example2, ...] }


@dataclass
class IntentResult:
    """Result from the fast intent engine."""
    action:     str              # Resolved action name
    confidence: float            # 0.0 - 1.0 cosine similarity
    source:     str              # "builtin" | "learned" | "none"
    matched_example: str = ""    # Which example it matched against


# ─── Built-in Intent Registry ───────────────────────────────
# These are the seed examples for each action.
# The more examples, the better the matching accuracy.
INTENT_REGISTRY = {
    # ── Apps ─────────────────────────────────────────────────
    "open_app": [
        "open vscode", "launch vscode", "start vscode", "fire up vscode",
        "open safari", "launch safari", "start safari", "open browser",
        "open terminal", "launch terminal", "start terminal", "open shell",
        "open chrome", "launch chrome", "start chrome",
        "open finder", "launch finder",
        "open notes", "open music", "open spotify",
        "open slack", "open discord", "open zoom",
        "open an app", "launch an application",
    ],
    "close_app": [
        "close vscode", "quit vscode", "exit vscode",
        "close safari", "quit safari", "exit safari",
        "close terminal", "quit terminal", "exit terminal",
        "close chrome", "quit chrome",
        "close the app", "quit the application", "kill the app",
    ],
    "switch_to_app": [
        "switch to vscode", "go to vscode", "bring up vscode",
        "switch to safari", "go to safari", "bring up safari",
        "switch to terminal", "go to terminal",
        "switch to chrome", "go to chrome",
        "switch app", "go to an app", "bring up another app",
    ],

    # ── Volume ───────────────────────────────────────────────
    "volume_up": [
        "volume up", "turn up the volume", "increase volume",
        "make it louder", "louder", "crank it up",
        "volume up by 20", "raise the volume",
    ],
    "volume_down": [
        "volume down", "turn down the volume", "decrease volume",
        "make it quieter", "quieter", "lower the volume",
        "volume down by 20", "reduce volume",
    ],
    "mute": [
        "mute", "mute the sound", "silence", "mute audio",
        "turn off sound", "mute everything",
    ],
    "unmute": [
        "unmute", "unmute the sound", "turn on sound",
        "enable audio", "unmute audio",
    ],
    "get_volume": [
        "what's the volume", "current volume", "volume level",
        "how loud is it", "get volume",
    ],

    # ── Brightness ────────────────────────────────────────────
    "brightness_up": [
        "brightness up", "increase brightness", "brighter",
        "make it brighter", "screen brighter", "more brightness",
    ],
    "brightness_down": [
        "brightness down", "decrease brightness", "dimmer",
        "make it dimmer", "screen dimmer", "less brightness",
    ],

    # ── System ───────────────────────────────────────────────
    "lock_screen": [
        "lock screen", "lock the screen", "lock my screen",
        "lock my mac", "lock computer",
    ],
    "shutdown_pc": [
        "shutdown", "shut down", "turn off", "power off",
        "shutdown my mac", "turn off computer",
    ],
    "restart_pc": [
        "restart", "reboot", "restart my mac",
        "restart computer", "reboot system",
    ],
    "sleep_mac": [
        "sleep", "sleep mode", "put to sleep",
        "sleep my mac", "nap mode", "go to sleep",
    ],
    "take_screenshot": [
        "take screenshot", "screenshot", "capture screen",
        "screen capture", "take a snap", "snapshot",
    ],
    "get_battery": [
        "battery", "battery level", "how much battery",
        "check battery", "battery percentage", "power level",
    ],

    # ── Time & Date ──────────────────────────────────────────
    "tell_time": [
        "what time is it", "current time", "what's the time",
        "time please", "tell me the time", "what time",
    ],
    "tell_date": [
        "what's the date", "what is the date", "today's date",
        "current date", "tell me the date", "what day is it",
    ],

    # ── Weather ──────────────────────────────────────────────
    "tell_weather": [
        "weather", "what's the weather", "how's the weather",
        "temperature", "is it hot", "is it cold",
        "weather outside", "what's it like outside",
    ],

    # ── Web Search ───────────────────────────────────────────
    "search_google": [
        "search google", "google search", "search for",
        "look up", "search the web", "google",
        "search online", "browse for", "find online",
    ],

    # ── Folders ──────────────────────────────────────────────
    "open_folder": [
        "open downloads", "open desktop", "open documents",
        "open folder", "open my files", "show folder",
        "go to downloads", "go to desktop",
    ],
    "create_folder": [
        "create folder", "make folder", "new folder",
        "create a directory", "make a new folder",
    ],
    "search_file": [
        "search file", "find file", "look for file",
        "where is my file", "locate file", "find my",
    ],

    # ── Email ────────────────────────────────────────────────
    "read_emails": [
        "read my emails", "check my emails", "check inbox",
        "any new emails", "read emails", "show my emails",
        "check my inbox", "any emails",
    ],
    "search_emails": [
        "search emails", "find emails", "emails from",
        "any emails about", "search my inbox",
    ],
    "send_email": [
        "send email", "compose email", "write email",
        "email to", "send a message", "compose mail",
    ],
    "open_gmail": [
        "open gmail", "open my email", "open mail",
        "go to gmail", "launch gmail",
    ],

    # ── Window Management ────────────────────────────────────
    "minimise_all": [
        "minimize all", "minimize everything", "hide all windows",
        "minimize all windows", "clear windows",
    ],
    "show_desktop": [
        "show desktop", "go to desktop", "reveal desktop",
        "clear desktop", "desktop",
    ],
    "close_window": [
        "close window", "close this window", "shut window",
    ],
    "close_tab": [
        "close tab", "close this tab", "shut tab",
    ],
    "new_tab": [
        "new tab", "open new tab", "open tab",
    ],
    "fullscreen": [
        "fullscreen", "full screen", "make it fullscreen",
        "maximize", "go fullscreen",
    ],
    "mission_control": [
        "mission control", "show all windows",
        "expose", "all windows", "overview",
    ],
    "minimise_app": [
        "minimize safari", "minimize vscode", "minimize terminal",
        "hide safari", "hide vscode", "hide app",
        "minimize an app", "minimize this app",
    ],

    # ── Routines ─────────────────────────────────────────────
    "start_work_day": [
        "start my day", "work mode", "begin work",
        "start work", "work time", "let's work",
    ],
    "end_work_day": [
        "end my day", "finish work", "wrap up",
        "end work", "done working", "stop working",
    ],
    "morning_briefing": [
        "morning briefing", "brief me", "what's today like",
        "give me a briefing", "daily brief", "what's happening today",
    ],

    # ── PDF ───────────────────────────────────────────────────
    "summarise_pdf": [
        "summarize pdf", "summarise pdf", "read pdf",
        "read this pdf", "what does this pdf say",
        "pdf summary", "analyze pdf",
    ],

    # ── File Operations ──────────────────────────────────────
    "read_file": [
        "read file", "read notes", "open and read",
        "what's in this file", "show file contents",
        "read notes.txt", "read the file",
    ],
    "create_file": [
        "create file", "make file", "new file",
        "create a file called", "make a new file",
    ],
    "delete_file": [
        "delete file", "remove file", "trash file",
        "delete this file", "remove that file",
    ],
    "rename_file": [
        "rename file", "rename this", "change name",
        "rename to", "rename file to",
    ],
    "copy_file": [
        "copy file", "copy this file", "duplicate file",
        "copy to desktop", "copy to downloads",
    ],
    "get_recent_files": [
        "recent files", "what files did i work on",
        "what did i edit today", "show recent files",
        "my recent files", "lately edited files",
    ],
}


def _get_model():
    """Lazy-load the sentence transformer model."""
    global _model
    if _model is None:
        print("🧠 Loading sentence-transformer model...")
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer("all-MiniLM-L6-v2")
        print("✅ Model loaded")
    return _model


def _build_embeddings(extra_examples: dict = None):
    """
    Pre-compute embeddings for all intent examples.
    Called once on startup and when learned intents change.
    """
    global _intent_embeddings, _intent_examples

    model = _get_model()

    # Merge built-in + learned examples
    all_examples = {}
    for action, examples in INTENT_REGISTRY.items():
        all_examples[action] = list(examples)  # copy

    if extra_examples:
        for action, learned in extra_examples.items():
            if action in all_examples:
                all_examples[action].extend(learned)
            else:
                all_examples[action] = learned

    # Compute embeddings
    _intent_examples   = {}
    _intent_embeddings = {}

    for action, examples in all_examples.items():
        _intent_examples[action]   = examples
        embeddings = model.encode(examples, convert_to_numpy=True, normalize_embeddings=True)
        _intent_embeddings[action] = embeddings

    total = sum(len(e) for e in _intent_examples.values())
    print(f"📊 Indexed {total} examples across {len(_intent_examples)} intents")


def initialize(learned_examples: dict = None):
    """
    Initialize the fast intent engine.
    Should be called once on startup.

    Args:
        learned_examples: { action: [example1, ...] } from learned_intents DB
    """
    _build_embeddings(learned_examples)


def reload_learned(learned_examples: dict):
    """Reload with new learned examples (after a Gemini resolution)."""
    _build_embeddings(learned_examples)


def classify(text: str) -> IntentResult:
    """
    Classify a normalized command text into an intent.
    Uses cosine similarity against all pre-computed embeddings.

    Args:
        text: Normalized command text

    Returns:
        IntentResult with action, confidence, source, and matched_example
    """
    if not text or not text.strip():
        return IntentResult(action="", confidence=0.0, source="none")

    if _intent_embeddings is None:
        initialize()

    model = _get_model()

    # Embed the input
    input_embedding = model.encode([text], convert_to_numpy=True, normalize_embeddings=True)[0]

    best_action     = ""
    best_confidence = 0.0
    best_example    = ""
    best_source     = "builtin"

    for action, embeddings in _intent_embeddings.items():
        # Cosine similarity (embeddings are already normalized)
        similarities = np.dot(embeddings, input_embedding)
        max_idx      = np.argmax(similarities)
        max_sim      = float(similarities[max_idx])

        if max_sim > best_confidence:
            best_confidence = max_sim
            best_action     = action
            best_example    = _intent_examples[action][max_idx]

            # Determine source
            builtin_count = len(INTENT_REGISTRY.get(action, []))
            if max_idx >= builtin_count:
                best_source = "learned"
            else:
                best_source = "builtin"

    return IntentResult(
        action=best_action,
        confidence=best_confidence,
        source=best_source,
        matched_example=best_example
    )


# ─── Quick test ──────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("  FAST INTENT ENGINE TEST")
    print("=" * 60)

    # Initialize
    initialize()

    # Test commands
    tests = [
        "open vscode",
        "launch my editor",
        "fire up the browser",
        "crank up the volume",
        "what time is it bro",
        "check my inbox",
        "search for python tutorials",
        "take a screenshot",
        "put my mac to sleep",
        "show all windows",
        "read my recent files",
        "create file called notes",
        "how much battery do i have",
        "open downloads folder",
        "send an email",
        "close everything",            # should be lower confidence
        "make me a sandwich",          # should be very low confidence
    ]

    print(f"\n{'Command':<40} {'Action':<20} {'Conf':>6} {'Source':<10} {'Matched'}")
    print("-" * 110)

    for cmd in tests:
        result = classify(cmd)
        print(f"  {cmd:<38} {result.action:<20} {result.confidence:>5.2f}  {result.source:<10} {result.matched_example}")
