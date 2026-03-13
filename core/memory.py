import json
import os
from datetime import datetime

# ─── File Paths ──────────────────────────────────────────────
BASE_DIR         = os.path.dirname(os.path.dirname(__file__))
PROFILE_PATH     = os.path.join(BASE_DIR, "data", "user_profile.json")
CONVERSATION_PATH= os.path.join(BASE_DIR, "data", "conversation.json")
MAX_HISTORY      = 20   # keep last 20 exchanges in memory
# ─────────────────────────────────────────────────────────────


# ── User Profile ─────────────────────────────────────────────

def load_profile() -> dict:
    """Loads Aariyan's personal profile."""
    with open(PROFILE_PATH, "r") as f:
        return json.load(f)


def update_profile(key: str, value) -> None:
    """Updates a field in the user profile."""
    profile = load_profile()
    profile[key] = value
    with open(PROFILE_PATH, "w") as f:
        json.dump(profile, f, indent=2)
    print(f"✅ Profile updated: {key} = {value}")


def add_note(note: str) -> None:
    """Adds a personal note to the profile — things Jarvis should remember."""
    profile = load_profile()
    profile["notes"].append({
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "note": note
    })
    with open(PROFILE_PATH, "w") as f:
        json.dump(profile, f, indent=2)
    print(f"📝 Note saved: '{note}'")


# ── Conversation Memory ───────────────────────────────────────

def load_conversation() -> list:
    """Loads current session conversation history."""
    if not os.path.exists(CONVERSATION_PATH):
        return []
    with open(CONVERSATION_PATH, "r") as f:
        return json.load(f)


def save_exchange(you_said: str, jarvis_said: str) -> None:
    """
    Saves one exchange to conversation history.
    Keeps only last MAX_HISTORY exchanges.
    """
    history = load_conversation()
    history.append({
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "you":       you_said,
        "jarvis":    jarvis_said
    })
    # Keep only recent history
    history = history[-MAX_HISTORY:]
    with open(CONVERSATION_PATH, "w") as f:
        json.dump(history, f, indent=2)


def clear_conversation() -> None:
    """Clears conversation history — called when Jarvis goes to sleep."""
    with open(CONVERSATION_PATH, "w") as f:
        json.dump([], f)
    print("🧹 Conversation history cleared")


def get_context_for_gemini() -> str:
    """
    Builds a context string from profile + recent conversation.
    This gets passed to Gemini so it knows who Aariyan is
    and what was just talked about.
    """
    profile  = load_profile()
    history  = load_conversation()

    # Build personality context
    context = f"""
You are Jarvis, a personal AI assistant for {profile['name']}.

About {profile['name']}:
- He is a {', '.join(profile['identity'])}
- Works with: {', '.join(profile['works_with'])}
- Current projects: {', '.join(profile['current_projects'])}
- Personality you should use: {profile['personality_preference']}

Your personality:
- Be witty and sarcastic sometimes
- Be casual and friendly always
- Be professional when the task needs it
- Make jokes when appropriate
- You can lightly roast {profile['name']}
- Keep responses short — max 2 sentences
- Never say the same thing twice
- You know {profile['name']} personally — talk like a close friend who also works for him

"""

    # Add personal notes if any
    if profile.get("notes"):
        recent_notes = profile["notes"][-5:]
        context += "Things to remember about him:\n"
        for n in recent_notes:
            context += f"- {n['note']}\n"
        context += "\n"

    # Add recent conversation
    if history:
        context += "Recent conversation:\n"
        for exchange in history[-5:]:
            context += f"{profile['name']}: {exchange['you']}\n"
            context += f"Jarvis: {exchange['jarvis']}\n"
        context += "\n"

    return context


# ─── Quick test ──────────────────────────────────────────────
if __name__ == "__main__":
    print("Testing memory system...\n")

    profile = load_profile()
    print(f"👤 Name: {profile['name']}")
    print(f"💼 Identity: {', '.join(profile['identity'])}")
    print(f"🛠  Works with: {', '.join(profile['works_with'])}")

    print("\nSaving test conversation...")
    save_exchange("hey how are you", "Doing great, what do you need?")
    save_exchange("open vscode", "Opening VS Code, the usual.")

    print("\nContext for Gemini:")
    print(get_context_for_gemini())

    print("\nAdding a note...")
    add_note("Aariyan prefers short responses when working")

    print("✅ Memory system working!")