import json
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from dotenv import load_dotenv
from google import genai
from mood.mood_engine import get_mood_for_prompt

# ─── Settings ────────────────────────────────────────────────
GEMINI_API_KEY = "YOUR_GEMINI_API_KEY"
MODEL          = "gemini-3.1-flash-lite-preview"
# ─────────────────────────────────────────────────────────────

load_dotenv()
client = genai.Client(api_key=os.getenv("API_KEY"))

# ─── Action Descriptions ─────────────────────────────────────
# Tells Gemini what just happened so it can respond naturally
ACTION_CONTEXT = {
    "open_vscode":    "Jarvis is opening Visual Studio Code",
    "open_safari":    "Jarvis is opening Safari browser",
    "open_terminal":  "Jarvis is opening Terminal",
    "search_google":  "Jarvis is searching Google",
    "tell_time":      "Jarvis is about to tell the current time",
    "tell_date":      "Jarvis is about to tell today's date",
    "lock_screen":    "Jarvis is locking the Mac screen",
    "shutdown_pc":    "Jarvis is shutting down the Mac",
    "restart_pc":     "Jarvis is restarting the Mac",
    "sleep_mac":      "Jarvis is putting the Mac to sleep",
    "chat_response":  "Jarvis is having a casual conversation",
}
# ─────────────────────────────────────────────────────────────


def generate_response(
    action: str,
    user_said: str,
    extra_info: str = None
) -> str:
    """
    Archived legacy dynamic responder.
    Replaced in the live pipeline by core.response_policy.
    """
    action_desc = ACTION_CONTEXT.get(action, f"Jarvis is performing: {action}")
    mood_context = get_mood_for_prompt()

    extra = f"\nExtra context: {extra_info}" if extra_info else ""

    prompt = f"""
You are Jarvis, a personal AI assistant for Aariyan.

{mood_context}

What just happened: {action_desc}
What Aariyan said: "{user_said}"{extra}

Generate ONE short natural spoken response (1 sentence max).
Rules:
- Match the mood exactly
- Never say the same thing twice
- Sound human, not robotic
- Don't explain what you're doing in technical terms
- If it's a search, mention what you're searching for
- If it's time/date, you'll speak the actual value separately — just acknowledge
- No emojis (this is spoken text)
- Max 10 words ideally

Just give the response text. Nothing else.
"""

    try:
        response = client.models.generate_content(
            model=MODEL,
            contents=prompt
        )
        return response.text.strip().strip('"')

    except Exception:
        fallbacks = {
            "open_vscode":   "Opening VS Code.",
            "open_safari":   "Opening Safari.",
            "open_terminal": "Opening Terminal.",
            "search_google": f"Searching for {extra_info or 'that'}.",
            "tell_time":     "The time is",
            "tell_date":     "Today is",
            "lock_screen":   "Locking the screen.",
            "shutdown_pc":   "Shutting down.",
            "restart_pc":    "Restarting.",
            "sleep_mac":     "Going to sleep.",
        }
        return fallbacks.get(action, "On it.")


if __name__ == "__main__":
    print("Archived responder smoke test...\n")

    tests = [
        ("open_safari",   "yo open my browser",           None),
        ("open_vscode",   "open my coding editor",        None),
        ("search_google", "search for python tutorials",  "python tutorials"),
        ("lock_screen",   "lock my screen bro",           None),
        ("tell_time",     "what time is it",              "1:05 AM"),
        ("sleep_mac",     "put my mac to sleep",          None),
    ]

    for action, user_said, extra in tests:
        print(f"User: '{user_said}'")
        response = generate_response(action, user_said, extra)
        print(f"Jarvis: {response}")
        print("-" * 40)
