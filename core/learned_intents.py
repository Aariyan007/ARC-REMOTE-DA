"""
Self-Learning Intent DB — stores Gemini-resolved commands so the
fast intent engine can handle them next time without Gemini.

Features:
- Max 500 entries (LRU pruning)
- Deduplication (same normalized input → update, don't duplicate)
- Persistent storage in data/learned_intents.json
"""

import json
import os
from datetime import datetime
from typing import Optional


# ─── Settings ────────────────────────────────────────────────
BASE_DIR    = os.path.dirname(os.path.dirname(__file__))
DB_PATH     = os.path.join(BASE_DIR, "data", "learned_intents.json")
MAX_ENTRIES = 500
# ─────────────────────────────────────────────────────────────


def _load_db() -> list:
    """Loads the learned intents database."""
    if not os.path.exists(DB_PATH):
        return []
    try:
        with open(DB_PATH, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return []


def _save_db(entries: list) -> None:
    """Saves the database with LRU pruning."""
    # Sort by last_matched (most recent last) for LRU
    entries.sort(key=lambda e: e.get("last_matched", e.get("created", "")))

    # Prune to MAX_ENTRIES (keep most recently matched)
    if len(entries) > MAX_ENTRIES:
        entries = entries[-MAX_ENTRIES:]

    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with open(DB_PATH, "w") as f:
        json.dump(entries, f, indent=2)


def learn(
    normalized_input: str,
    action: str,
    params: dict,
    confidence: float = 1.0,
    source: str = "gemini"
) -> None:
    """
    Saves a learned command→intent mapping.
    If the same normalized input exists, updates instead of duplicating.

    Args:
        normalized_input:  The cleaned/normalized command text
        action:            The resolved action name
        params:            The resolved parameters
        confidence:        Confidence of the original resolution
        source:            Where this was learned from ("gemini", "correction")
    """
    entries = _load_db()
    now     = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Deduplication: check if this normalized input already exists
    for entry in entries:
        if entry["normalized_input"] == normalized_input:
            # Update existing entry
            entry["action"]       = action
            entry["params"]       = params
            entry["confidence"]   = confidence
            entry["last_matched"] = now
            entry["match_count"]  = entry.get("match_count", 0) + 1
            entry["source"]       = source
            print(f"📚 Updated learned intent: '{normalized_input}' → {action}")
            _save_db(entries)
            return

    # New entry
    entry = {
        "normalized_input": normalized_input,
        "action":           action,
        "params":           params,
        "confidence":       confidence,
        "source":           source,
        "created":          now,
        "last_matched":     now,
        "match_count":      1,
    }

    entries.append(entry)
    print(f"📚 Learned new intent: '{normalized_input}' → {action}")
    _save_db(entries)


def get_learned_examples() -> dict:
    """
    Returns learned intents grouped by action.
    Used by the fast intent engine to add learned examples
    to its embedding space.

    Returns:
        { action: [normalized_input_1, normalized_input_2, ...] }
    """
    entries = _load_db()
    grouped = {}

    for entry in entries:
        action = entry["action"]
        if action not in grouped:
            grouped[action] = []
        grouped[action].append(entry["normalized_input"])

    return grouped


def find_exact_match(normalized_input: str) -> Optional[dict]:
    """
    Checks if this exact normalized input was learned before.
    If found, updates last_matched and returns the entry.
    """
    entries = _load_db()

    for entry in entries:
        if entry["normalized_input"] == normalized_input:
            # Update LRU tracking
            entry["last_matched"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            entry["match_count"]  = entry.get("match_count", 0) + 1
            _save_db(entries)
            print(f"⚡ Learned intent hit: '{normalized_input}' → {entry['action']}")
            return entry

    return None


def get_stats() -> dict:
    """Returns stats about the learned intents DB."""
    entries = _load_db()
    if not entries:
        return {"total": 0}

    actions = [e["action"] for e in entries]
    return {
        "total":           len(entries),
        "unique_actions":  len(set(actions)),
        "most_common":     max(set(actions), key=actions.count) if actions else None,
        "total_matches":   sum(e.get("match_count", 0) for e in entries),
        "from_gemini":     sum(1 for e in entries if e.get("source") == "gemini"),
        "from_correction": sum(1 for e in entries if e.get("source") == "correction"),
    }


def clear_db() -> None:
    """Clears the entire learned intents database."""
    _save_db([])
    print("🗑️  Learned intents database cleared")


# ─── Quick test ──────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("  LEARNED INTENTS DB TEST")
    print("=" * 60)

    # Learn some commands
    learn("open spotify", "open_app", {"name": "spotify"}, source="gemini")
    learn("play music", "open_app", {"name": "music"}, source="gemini")
    learn("open spotify", "open_app", {"name": "spotify"}, source="gemini")  # dedup test

    # Check stats
    stats = get_stats()
    print(f"\n📊 Stats: {stats}")

    # Check exact match
    match = find_exact_match("open spotify")
    print(f"\n🔍 Exact match: {match}")

    # Check grouped examples
    examples = get_learned_examples()
    print(f"\n📖 Grouped examples: {examples}")
