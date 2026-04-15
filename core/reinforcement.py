"""
Reinforcement Learning — learns from mistakes + corrections.

Three mechanisms:
1. Correction Loop    — user says "no/wrong" → asks what they meant → learns
2. Negative Examples  — misclassified commands become anti-examples for that intent
3. Confidence Boost   — successful commands get boosted in the embedding space

Storage: data/negative_examples.json, data/confidence_boosts.json
"""

import json
import os
from datetime import datetime
from typing import Optional

from core.learned_intents import learn
from core.voice_response import speak
from core.speech_to_text import listen as stt_listen


# ─── Settings ────────────────────────────────────────────────
BASE_DIR       = os.path.dirname(os.path.dirname(__file__))
NEGATIVES_PATH = os.path.join(BASE_DIR, "data", "negative_examples.json")
BOOSTS_PATH    = os.path.join(BASE_DIR, "data", "confidence_boosts.json")
MAX_NEGATIVES  = 200
MAX_BOOSTS     = 300
# ─────────────────────────────────────────────────────────────


# ── Last action tracking for corrections ─────────────────────
_last_action_context = {
    "command":    None,    # what the user said
    "action":     None,    # what intent we resolved
    "confidence": 0.0,     # how confident we were
    "params":     {},      # extracted params
    "source":     None,    # "builtin" | "learned" | "gemini"
}


def track_action(command: str, action: str, confidence: float,
                 params: dict = None, source: str = "builtin") -> None:
    """Called after every successful action — tracks for potential correction."""
    global _last_action_context
    _last_action_context = {
        "command":    command,
        "action":     action,
        "confidence": confidence,
        "params":     params or {},
        "source":     source,
    }


def get_last_action() -> dict:
    """Returns the last action context for corrections."""
    return _last_action_context.copy()


# ═══════════════════════════════════════════════════════════════
# 1. NEGATIVE EXAMPLES — "this command is NOT <intent>"
# ═══════════════════════════════════════════════════════════════

def _load_negatives() -> dict:
    """Loads negative example database. Format: { action: [text1, text2, ...] }"""
    if not os.path.exists(NEGATIVES_PATH):
        return {}
    try:
        with open(NEGATIVES_PATH, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def _save_negatives(data: dict) -> None:
    """Saves negative examples with pruning."""
    # Prune each action's negatives to max count
    for action in data:
        if len(data[action]) > MAX_NEGATIVES:
            data[action] = data[action][-MAX_NEGATIVES:]
    os.makedirs(os.path.dirname(NEGATIVES_PATH), exist_ok=True)
    with open(NEGATIVES_PATH, "w") as f:
        json.dump(data, f, indent=2)


def add_negative(text: str, wrong_action: str) -> None:
    """
    Records that `text` was wrongly classified as `wrong_action`.
    The fast intent engine uses these to penalize similarity scores.
    """
    negatives = _load_negatives()
    if wrong_action not in negatives:
        negatives[wrong_action] = []
    if text not in negatives[wrong_action]:
        negatives[wrong_action].append(text)
        print(f"🚫 Negative example: '{text}' is NOT {wrong_action}")
        _save_negatives(negatives)


def get_negatives() -> dict:
    """Returns all negative examples grouped by wrong action."""
    return _load_negatives()


def get_penalty(text_embedding, action: str) -> float:
    """
    Calculates a penalty score for an action based on negative examples.
    Higher penalty = more evidence this IS NOT the right action.

    Called by the fast intent engine during classification.
    Returns a value 0.0 - 0.3 to subtract from confidence.
    """
    negatives = _load_negatives()
    if action not in negatives or not negatives[action]:
        return 0.0

    try:
        from core.fast_intent import _get_model
        import numpy as np
        
        model = _get_model()
        neg_texts = negatives[action]
        neg_embeddings = model.encode(neg_texts, convert_to_numpy=True,
                                       normalize_embeddings=True)
        
        # Calculate max similarity to any negative example
        similarities = np.dot(neg_embeddings, text_embedding)
        max_neg_sim = float(np.max(similarities))
        
        # If very similar to a negative example → strong penalty
        if max_neg_sim > 0.85:
            return 0.25  # severe penalty
        elif max_neg_sim > 0.70:
            return 0.15  # moderate penalty
        elif max_neg_sim > 0.55:
            return 0.05  # light penalty
        return 0.0
    except Exception:
        return 0.0


# ═══════════════════════════════════════════════════════════════
# 2. CONFIDENCE BOOSTS — successful patterns get boosted
# ═══════════════════════════════════════════════════════════════

def _load_boosts() -> dict:
    """Loads confidence boost database. Format: { action: { text: boost_count } }"""
    if not os.path.exists(BOOSTS_PATH):
        return {}
    try:
        with open(BOOSTS_PATH, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def _save_boosts(data: dict) -> None:
    os.makedirs(os.path.dirname(BOOSTS_PATH), exist_ok=True)
    with open(BOOSTS_PATH, "w") as f:
        json.dump(data, f, indent=2)


def boost_confidence(text: str, action: str) -> None:
    """
    Records a successful command→action mapping.
    The more a pattern succeeds, the higher the confidence boost.
    """
    boosts = _load_boosts()
    if action not in boosts:
        boosts[action] = {}

    key = text.lower().strip()
    boosts[action][key] = boosts[action].get(key, 0) + 1

    # Prune if too many
    if len(boosts[action]) > MAX_BOOSTS:
        # Keep most frequently boosted
        sorted_items = sorted(boosts[action].items(),
                            key=lambda x: x[1], reverse=True)
        boosts[action] = dict(sorted_items[:MAX_BOOSTS])

    _save_boosts(boosts)


def get_boost(text: str, action: str) -> float:
    """
    Returns a confidence boost for a text→action pair.
    Returns 0.0 - 0.15 based on how many times this pattern succeeded.
    """
    boosts = _load_boosts()
    if action not in boosts:
        return 0.0

    key = text.lower().strip()
    count = boosts[action].get(key, 0)

    if count == 0:
        return 0.0
    elif count == 1:
        return 0.03
    elif count <= 3:
        return 0.06
    elif count <= 10:
        return 0.10
    else:
        return 0.15  # max boost


# ═══════════════════════════════════════════════════════════════
# 3. CORRECTION LOOP — "no, I meant X"
# ═══════════════════════════════════════════════════════════════

import re

CORRECTION_WORDS = {
    "no", "wrong", "not that", "that's wrong", "incorrect",
    "other", "different", "actually", "instead", "i meant",
    "that's not what i said", "not what i meant",
}


ACTION_VERBS_RE = re.compile(
    r'\b(?:open|close|delete|remove|create|make|write|add|search|play|send|read|rename|copy|find|launch|start|stop|shutdown|restart|lock|take|show|bring|switch|go)\b'
)

def is_correction(text: str) -> bool:
    """Checks if the user's response is a correction of the last action.

    Returns False if:
    - The text contains an action verb (it's a new command, not a correction)
    - The text is longer than 6 words (likely a full sentence/command)
    """
    text_lower = text.lower().strip()
    words = text_lower.split()

    # Ignore if it contains a real action verb — user is giving a new command
    if ACTION_VERBS_RE.search(text_lower):
        return False

    # Long sentences are commands, not corrections
    if len(words) > 7:
        return False

    for word in CORRECTION_WORDS:
        pattern = r'\b' + re.escape(word) + r'\b'
        if re.search(pattern, text_lower):
            return True
    return False


def handle_correction(correction_text: str, actions: dict) -> str:
    """
    Handles a user correction.

    Flow:
    1. Records the last action as a negative example
    2. Asks what the user actually meant
    3. Sends to Gemini for understanding
    4. Learns the correct mapping

    Returns result string.
    """


    last = get_last_action()

    if not last["command"] or not last["action"]:
        speak("I'm not sure what you want me to fix. Can you tell me again?")
        return "No previous action to correct"

    # Record the mistake as a negative example
    add_negative(last["command"], last["action"])

    # Ask what they actually wanted
    speak("Sorry about that. What did you actually want me to do?")
    response = stt_listen()

    if not response or not response.strip():
        speak("I didn't catch that. Try again from scratch.")
        return "No correction provided"

    # Try to resolve the correct intent via Gemini
    try:
        from core.llm_brain import ask_gemini
        result = ask_gemini(response)

        correct_action = result.get("action")
        response_text = result.get("response", "Got it.")

        if correct_action:
            # Learn the ORIGINAL command → correct action
            learn(
                normalized_input=last["command"],
                action=correct_action,
                params=result,
                confidence=1.0,
                source="correction",
            )
            speak(f"Got it. Next time I'll know. {response_text}")
            print(f"📚 Correction learned: '{last['command']}' → {correct_action} (was {last['action']})")
            return f"Corrected: {last['action']} → {correct_action}"
        else:
            speak(response_text)
            return "Correction understood as chat"

    except Exception as e:
        print(f"⚠️ Correction error: {e}")
        speak("Had trouble understanding the correction. Try again?")
        return f"Correction error: {e}"


# ─── Quick test ──────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("  REINFORCEMENT LEARNING TEST")
    print("=" * 60)

    # Test negative examples
    print("\n── Negative Examples ──")
    add_negative("are these all files going to be", "get_recent_files")
    add_negative("you", "shutdown_pc")
    print(f"Negatives: {get_negatives()}")

    # Test confidence boosts
    print("\n── Confidence Boosts ──")
    boost_confidence("open vscode", "open_app")
    boost_confidence("open vscode", "open_app")
    boost_confidence("open vscode", "open_app")
    print(f"Boost for 'open vscode' → open_app: {get_boost('open vscode', 'open_app')}")
    print(f"Boost for 'unknown' → open_app: {get_boost('unknown', 'open_app')}")

    # Test correction detection
    print("\n── Correction Detection ──")
    for text in ["no that's wrong", "yes do it", "not that", "open vscode"]:
        print(f"  '{text}' → is_correction={is_correction(text)}")
