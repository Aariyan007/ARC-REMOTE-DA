import json
import os
from datetime import datetime

# ─── Mood Definitions ────────────────────────────────────────
MOODS = {
    "focused": {
        "description": "Professional and sharp. Short responses. No jokes.",
        "style": "Keep it brief and professional. No humor. Just get things done.",
        "emoji": "🎯"
    },
    "casual": {
        "description": "Friendly and relaxed. Light humor. Like a friend.",
        "style": "Be friendly and casual. Light jokes are fine. Talk like a close friend.",
        "emoji": "😊"
    },
    "sarcastic": {
        "description": "Witty and sarcastic. Roast the user lightly. Still helpful.",
        "style": "Be witty and sarcastic. Light roasts are welcome. Still get the job done.",
        "emoji": "😏"
    },
    "night": {
        "description": "Chill and low energy. Late night vibes. Minimal responses.",
        "style": "Chill late night energy. Keep it short. Acknowledge the late hour sometimes.",
        "emoji": "🌙"
    }
}

# ─── State File ───────────────────────────────────────────────
# Stores current mood so it persists across function calls
STATE_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'mood_state.json')
# ─────────────────────────────────────────────────────────────


def _get_time_based_mood() -> str:
    """Returns mood based on current time of day."""
    hour = datetime.now().hour

    if 6 <= hour < 12:
        return "focused"     # morning — work mode
    elif 12 <= hour < 18:
        return "casual"      # afternoon — relaxed
    elif 18 <= hour < 24:
        return "sarcastic"   # evening — playful
    else:
        return "night"       # midnight to 6am — chill


def get_current_mood() -> dict:
    """
    Returns the current mood.
    Uses manual override if set, otherwise time-based.
    """
    # Check if manual override is set
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH, "r") as f:
            state = json.load(f)
            if state.get("override"):
                mood_name = state["mood"]
                return {"name": mood_name, **MOODS[mood_name]}

    # Fall back to time-based mood
    mood_name = _get_time_based_mood()
    return {"name": mood_name, **MOODS[mood_name]}


def set_mood(mood_name: str) -> str:
    """
    Manually sets Jarvis mood. Overrides time-based detection.
    Call with: set_mood("sarcastic")
    """
    if mood_name not in MOODS:
        return f"Unknown mood '{mood_name}'. Options: {', '.join(MOODS.keys())}"

    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, "w") as f:
        json.dump({"mood": mood_name, "override": True}, f)

    print(f"{MOODS[mood_name]['emoji']} Mood set to: {mood_name}")
    return mood_name


def clear_mood_override() -> None:
    """Clears manual override — goes back to time-based mood."""
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH, "w") as f:
            json.dump({"mood": None, "override": False}, f)
    print("🔄 Mood override cleared — back to time-based")


def get_mood_for_prompt() -> str:
    """
    Returns a mood instruction string ready to inject into Gemini prompt.
    Used by responder.py
    """
    mood = get_current_mood()
    hour = datetime.now().hour

    # Time of day string
    if 6 <= hour < 12:
        time_of_day = "morning"
    elif 12 <= hour < 17:
        time_of_day = "afternoon"
    elif 17 <= hour < 21:
        time_of_day = "evening"
    else:
        time_of_day = "late night"

    return f"""
Current mood: {mood['name']} {mood['emoji']}
Mood instruction: {mood['style']}
Time of day: {time_of_day}
"""


# ─── Quick test ──────────────────────────────────────────────
if __name__ == "__main__":
    print("Current mood:", get_current_mood()["name"])
    print("\nMood for prompt:")
    print(get_mood_for_prompt())

    print("\nSetting mood to sarcastic...")
    set_mood("sarcastic")
    print("Current mood:", get_current_mood()["name"])

    print("\nClearing override...")
    clear_mood_override()
    print("Current mood:", get_current_mood()["name"])