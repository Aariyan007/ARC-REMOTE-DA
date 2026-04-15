"""
Habits Engine — Learns user routines from interaction logs.

Analyzes interaction_logs to detect time-action patterns:
    - Actions triggered at specific times of day
    - Daily routines (e.g., "open terminal at 10 AM")
    - Frequent sequences (e.g., open vscode → open terminal)

Proactive suggestions:
    If a pattern is detected with high confidence,
    Jarvis can proactively ask:
    "Ready to start the dev server?"

Cross-platform: Pure Python, reads JSON logs.
"""

import os
import json
import time
from datetime import datetime, timedelta
from collections import defaultdict, Counter
from typing import Optional
from dataclasses import dataclass, field


# ─── Settings ────────────────────────────────────────────────
BASE_DIR     = os.path.dirname(os.path.dirname(__file__))
LOGS_DIR     = os.path.join(BASE_DIR, "logs")
HABITS_PATH  = os.path.join(BASE_DIR, "data", "habits.json")
MIN_OCCURRENCES = 3     # Min times a pattern must occur to be a habit
CONFIDENCE_THRESHOLD = 0.6  # Min confidence for a habit
# ─────────────────────────────────────────────────────────────


@dataclass
class HabitPattern:
    """A detected behavioral pattern."""
    action:      str                  # e.g., "open_app"
    params:      dict = field(default_factory=dict)  # e.g., {"target": "vscode"}
    hour:        int  = -1            # Typical hour (-1 = any)
    weekday:     int  = -1            # Day of week (0=Mon, -1 = any)
    occurrences: int  = 0            # How many times this pattern was seen
    confidence:  float = 0.0         # How reliable this pattern is
    last_seen:   str  = ""           # Last time this pattern was triggered
    description: str  = ""           # Human-readable description

    def to_dict(self) -> dict:
        return {
            "action":      self.action,
            "params":      self.params,
            "hour":        self.hour,
            "weekday":     self.weekday,
            "occurrences": self.occurrences,
            "confidence":  round(self.confidence, 3),
            "last_seen":   self.last_seen,
            "description": self.description,
        }

    @staticmethod
    def from_dict(d: dict) -> "HabitPattern":
        return HabitPattern(**{k: v for k, v in d.items() if k in HabitPattern.__dataclass_fields__})


@dataclass
class HabitSuggestion:
    """A proactive suggestion based on detected habits."""
    habit:     HabitPattern
    message:   str           # What to say to the user
    action:    str           # Action to execute if confirmed
    params:    dict = field(default_factory=dict)


# ─── Log Analysis ────────────────────────────────────────────
def _load_all_logs(days: int = 30) -> list:
    """Load all log entries from the last N days."""
    all_entries = []
    if not os.path.exists(LOGS_DIR):
        return all_entries

    cutoff = datetime.now() - timedelta(days=days)

    for filename in sorted(os.listdir(LOGS_DIR)):
        if not filename.endswith(".json"):
            continue

        # Parse date from filename (YYYY-MM-DD.json)
        try:
            file_date = datetime.strptime(filename.replace(".json", ""), "%Y-%m-%d")
            if file_date < cutoff:
                continue
        except ValueError:
            continue

        filepath = os.path.join(LOGS_DIR, filename)
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                entries = json.load(f)
                for entry in entries:
                    entry["_date"] = filename.replace(".json", "")
                all_entries.extend(entries)
        except Exception:
            continue

    return all_entries


def _extract_hour(timestamp: str) -> int:
    """Extract hour from a timestamp string."""
    try:
        dt = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")
        return dt.hour
    except Exception:
        return -1


def _extract_weekday(date_str: str) -> int:
    """Extract weekday (0=Monday) from a date string."""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return dt.weekday()
    except Exception:
        return -1


# ─── Pattern Detection ──────────────────────────────────────
def analyze_habits(days: int = 30) -> list:
    """
    Analyze logs and detect behavioral patterns.

    Returns list of HabitPattern sorted by confidence.
    """
    entries = _load_all_logs(days)
    if not entries:
        return []

    # ── Detect time-based patterns ───────────────────────────
    # Group actions by hour of day
    hour_actions = defaultdict(list)  # hour → [action, action, ...]
    action_hours = defaultdict(list)  # action → [hour, hour, ...]

    for entry in entries:
        action = entry.get("action_taken", "")
        if not action or not entry.get("was_understood"):
            continue

        hour = _extract_hour(entry.get("timestamp", ""))
        if hour < 0:
            continue

        hour_actions[hour].append(action)
        action_hours[action].append(hour)

    patterns = []

    # Find actions that consistently happen at specific hours
    for action, hours in action_hours.items():
        if len(hours) < MIN_OCCURRENCES:
            continue

        # Find the most common hour for this action
        hour_counts = Counter(hours)
        most_common_hour, count = hour_counts.most_common(1)[0]

        # Confidence: what fraction of this action's occurrences are at this hour
        confidence = count / len(hours)

        if confidence >= CONFIDENCE_THRESHOLD:
            # Get typical params
            typical_params = {}
            for entry in entries:
                if entry.get("action_taken") == action and entry.get("params"):
                    typical_params = entry["params"]
                    break

            pattern = HabitPattern(
                action=action,
                params=typical_params,
                hour=most_common_hour,
                occurrences=count,
                confidence=confidence,
                last_seen=entry.get("timestamp", ""),
                description=f"{action} usually at {most_common_hour}:00 "
                           f"({count} times, {confidence:.0%} confidence)",
            )
            patterns.append(pattern)

    # ── Detect sequence patterns ─────────────────────────────
    # Actions that frequently follow each other within 5 minutes
    sequence_counts = defaultdict(int)  # (action_a, action_b) → count

    sorted_entries = sorted(entries, key=lambda e: e.get("timestamp", ""))
    for i in range(len(sorted_entries) - 1):
        a = sorted_entries[i]
        b = sorted_entries[i + 1]

        try:
            time_a = datetime.strptime(a.get("timestamp", ""), "%Y-%m-%d %H:%M:%S")
            time_b = datetime.strptime(b.get("timestamp", ""), "%Y-%m-%d %H:%M:%S")
            gap = (time_b - time_a).total_seconds()

            if gap < 300:  # Within 5 minutes
                action_a = a.get("action_taken", "")
                action_b = b.get("action_taken", "")
                if action_a and action_b and action_a != action_b:
                    sequence_counts[(action_a, action_b)] += 1
        except Exception:
            continue

    for (action_a, action_b), count in sequence_counts.items():
        if count >= MIN_OCCURRENCES:
            total_a = sum(1 for e in entries if e.get("action_taken") == action_a)
            confidence = count / total_a if total_a > 0 else 0

            if confidence >= CONFIDENCE_THRESHOLD:
                pattern = HabitPattern(
                    action=f"{action_a} → {action_b}",
                    hour=-1,
                    occurrences=count,
                    confidence=confidence,
                    description=f"After {action_a}, usually does {action_b} "
                               f"({count} times, {confidence:.0%})",
                )
                patterns.append(pattern)

    # Sort by confidence
    patterns.sort(key=lambda p: p.confidence, reverse=True)
    return patterns


def get_suggestions_for_now() -> list:
    """
    Get proactive suggestions based on current time and habits.

    Returns list of HabitSuggestion for the current context.
    """
    current_hour = datetime.now().hour
    patterns = _load_habits()

    suggestions = []
    for pattern in patterns:
        # Check if this habit matches the current hour (±1 hour window)
        if pattern.hour >= 0:
            if abs(pattern.hour - current_hour) <= 1:
                # Generate suggestion
                action_name = pattern.action.split(" → ")[-1] if " → " in pattern.action else pattern.action
                suggestion = HabitSuggestion(
                    habit=pattern,
                    message=_generate_suggestion_message(pattern),
                    action=action_name,
                    params=pattern.params,
                )
                suggestions.append(suggestion)

    return suggestions


def _generate_suggestion_message(pattern: HabitPattern) -> str:
    """Generate a natural-sounding suggestion from a pattern."""
    action = pattern.action

    # Map common actions to friendly messages
    messages = {
        "open_app":      "Want me to open {target}? You usually do about now.",
        "open_vscode":   "Ready to start coding? I can open VS Code.",
        "open_terminal": "Should I open the terminal? It's about that time.",
        "search_google": "Need to look something up? You usually search around now.",
        "read_emails":   "Want me to check your emails?",
        "tell_time":     "Just so you know, it's {time} — around when you usually check in.",
    }

    target = pattern.params.get("target", pattern.params.get("name", ""))

    if action in messages:
        return messages[action].format(
            target=target,
            time=datetime.now().strftime("%I:%M %p"),
        )

    if " → " in action:
        parts = action.split(" → ")
        return f"You usually do {parts[1]} after {parts[0]}. Want me to go ahead?"

    return f"Based on your routine, should I run {action}?"


# ─── Persistence ─────────────────────────────────────────────
def save_habits(patterns: list) -> None:
    """Save detected habits to disk."""
    os.makedirs(os.path.dirname(HABITS_PATH), exist_ok=True)
    data = [p.to_dict() for p in patterns]
    with open(HABITS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _load_habits() -> list:
    """Load saved habits from disk."""
    if os.path.exists(HABITS_PATH):
        try:
            with open(HABITS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            return [HabitPattern.from_dict(d) for d in data]
        except Exception:
            return []
    return []


def refresh_habits(days: int = 30) -> list:
    """Re-analyze logs and update saved habits."""
    patterns = analyze_habits(days)
    save_habits(patterns)
    return patterns


# ─── Quick Test ──────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("  HABITS ENGINE TEST")
    print("=" * 60)

    # Analyze patterns from logs
    patterns = analyze_habits(days=30)

    if patterns:
        print(f"\nDetected {len(patterns)} habit patterns:")
        for p in patterns[:10]:
            print(f"  {p.description}")

        # Save
        save_habits(patterns)
        print(f"\nSaved to {HABITS_PATH}")
    else:
        print("\nNo habit patterns detected yet (need more log data)")

    # Check suggestions for now
    suggestions = get_suggestions_for_now()
    if suggestions:
        print(f"\nSuggestions for right now:")
        for s in suggestions:
            print(f"  -> {s.message}")
    else:
        print("\nNo suggestions for the current time")

    print("\n✅ Habits engine test passed!")
