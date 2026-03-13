import json
import os
from datetime import datetime


# ─── Settings ────────────────────────────────────────────────
LOGS_DIR = os.path.join(os.path.dirname(__file__), '..', 'logs')
# ─────────────────────────────────────────────────────────────


def _get_log_file() -> str:
    """Returns today's log file path. Creates logs/ folder if needed."""
    os.makedirs(LOGS_DIR, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    return os.path.join(LOGS_DIR, f"{today}.json")


def _load_today() -> list:
    """Loads today's log file. Returns empty list if doesn't exist yet."""
    path = _get_log_file()
    if not os.path.exists(path):
        return []
    with open(path, "r") as f:
        return json.load(f)


def log_interaction(
    you_said: str,
    action_taken: str,
    was_understood: bool,
    sent_to_gemini: bool = False,
    gemini_response: str = None
):
    """
    Logs a single Jarvis interaction to today's JSON file.

    Args:
        you_said:        Raw text Whisper heard from you
        action_taken:    What Jarvis did ("open_vscode", "tell_time", etc)
        was_understood:  True if router matched it, False if unknown
        sent_to_gemini:  True if Gemini was used as fallback
        gemini_response: What Gemini returned (if used)
    """
    entry = {
        "timestamp":       datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "you_said":        you_said,
        "action_taken":    action_taken,
        "was_understood":  was_understood,
        "sent_to_gemini":  sent_to_gemini,
        "gemini_response": gemini_response,
    }

    entries = _load_today()
    entries.append(entry)

    with open(_get_log_file(), "w") as f:
        json.dump(entries, f, indent=2)

    print(f"📝 Logged: '{you_said}' → {action_taken}")


def get_todays_stats() -> dict:
    """
    Returns a quick summary of today's usage.
    Useful for seeing patterns over time.
    """
    entries = _load_today()
    if not entries:
        return {"total": 0}

    understood   = sum(1 for e in entries if e["was_understood"])
    used_gemini  = sum(1 for e in entries if e["sent_to_gemini"])
    actions      = [e["action_taken"] for e in entries]
    most_used    = max(set(actions), key=actions.count) if actions else None

    return {
        "total":           len(entries),
        "understood":      understood,
        "failed":          len(entries) - understood,
        "used_gemini":     used_gemini,
        "most_used":       most_used,
        "all_actions":     actions,
    }


def print_todays_summary():
    """Prints a readable summary of today's Jarvis usage."""
    stats = get_todays_stats()
    print("\n" + "=" * 40)
    print("  TODAY'S JARVIS SUMMARY")
    print("=" * 40)
    print(f"  Total commands:    {stats.get('total', 0)}")
    print(f"  Understood:        {stats.get('understood', 0)}")
    print(f"  Failed:            {stats.get('failed', 0)}")
    print(f"  Used Gemini:       {stats.get('used_gemini', 0)}")
    print(f"  Most used command: {stats.get('most_used', 'none')}")
    print("=" * 40 + "\n")


# ─── Quick test ──────────────────────────────────────────────
if __name__ == "__main__":
    print("Testing logger...\n")

    log_interaction(
        you_said="yo open my thing",
        action_taken="open_vscode",
        was_understood=True,
        sent_to_gemini=False
    )
    log_interaction(
        you_said="hey how are you",
        action_taken="chat_response",
        was_understood=False,
        sent_to_gemini=True,
        gemini_response="I'm doing great! What can I help you with?"
    )
    log_interaction(
        you_said="what time is it",
        action_taken="tell_time",
        was_understood=True,
        sent_to_gemini=False
    )

    print_todays_summary()