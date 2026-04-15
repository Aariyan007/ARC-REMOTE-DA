"""
Background Gemini Enhancement — human-sounding follow-up for EVERY action.

Flow:
1. Instant response (Mac say) fires immediately → "On it."
2. Action executes
3. Background thread calls Gemini for a SHORT, witty, human follow-up
4. Follow-up speaks via ElevenLabs → "Superman, really? Bold choice."

Fires on EVERY action. Gemini responds "SKIP" when nothing cool to say.
"""

import threading
import time
from typing import Callable, Optional
from concurrent.futures import Future


# ─── Rate Limiting ───────────────────────────────────────────
# Prevent burning through free tier quota (20 reqs/min).
_last_call_time = 0.0
MIN_COOLDOWN    = 10.0   # seconds between background Gemini calls


# ─── Enhancement Hints ───────────────────────────────────────
# Optional hints that help Gemini make better comments per action.
ACTION_HINTS = {
    "read_emails":       "Comment on email situation briefly",
    "get_battery":       "React to battery level naturally",
    "tell_weather":      "Quick weather reaction",
    "morning_briefing":  "Comment on the day ahead",
    "search_emails":     "React to findings",
    "get_recent_files":  "Comment on recent activity",
    "summarise_pdf":     "React to the summary",
    "read_file":         "React to the file content",
    "create_file":       "React to the filename choice",
    "edit_file":         "React to what was written",
    "delete_file":       "React to deletion",
    "open_app":          "React to app choice",
    "close_app":         "Comment on closing",
    "volume_up":         "React to volume change",
    "volume_down":       "React to volume change",
    "take_screenshot":   "React to screenshot",
    "search_google":     "React to what they searched",
}


def should_enhance(action: str, action_result: str = None) -> bool:
    """
    Returns True for ALL actions — every command gets personality.
    Rate limited to prevent quota exhaustion.
    """
    global _last_call_time

    # Only skip if action is empty/unknown
    if not action or action == "unknown":
        return False

    # Rate limiting — skip if called too recently
    now = time.time()
    if now - _last_call_time < MIN_COOLDOWN:
        print(f"🔇 Background Gemini: cooldown ({MIN_COOLDOWN - (now - _last_call_time):.0f}s remaining)")
        return False

    return True


def _build_personality_prompt(
    action: str,
    command: str,
    action_result: str,
    instant_response: str,
    mood_context: str,
    user_context: str,
) -> str:
    """Builds the personality-heavy follow-up prompt."""
    hint = ACTION_HINTS.get(action, "React naturally to what just happened")

    return f"""You are Jarvis — not a formal assistant, more like a sharp, witty friend who happens to be an AI. Think Tony Stark's Jarvis meets a college best friend.

{user_context}
{mood_context}

The user said: "{command}"
Action taken: {action}
Result: {action_result}
Already spoken: "{instant_response}"
Hint: {hint}

Rules:
- Sound HUMAN. No corporate speak. No "certainly". No "I've done that for you."
- Max 8 words. Shorter = better. Sometimes just 2-3 words.
- Be witty, sarcastic, casual — like texting a friend
- Reference what they're doing naturally
- Sometimes be funny, sometimes be chill, sometimes just vibe
- If there's genuinely NOTHING cool to say → respond with exactly: SKIP
- NEVER repeat what was already spoken
- NEVER describe the action ("I opened...", "I created..."). React to it instead.
- Use contractions always. Talk like a real person.
- Can reference their projects, habits, or personality
- Light roasts welcome

Examples of GOOD responses:
- After opening VS Code: "Back to the grind, huh?"
- After creating superman.txt: "Superman, really? Bold choice."
- After muting: "Peace at last."
- After screenshot: "Evidence collected."
- After volume up: "Neighbors gonna love this."
- After creating a file: "Another masterpiece incoming."
- After editing a file: "Shakespeare would be proud."
- After reading a file: "Light reading, I see."

Examples of BAD responses (too formal/robotic — NEVER do this):
- "I've opened VS Code for you."
- "The file has been created successfully."
- "Volume has been increased."
- "Certainly, I'll do that right away."

Just return the response text. Nothing else. No quotes."""


def generate_followup(
    action: str,
    command: str,
    action_result: str,
    instant_response: str,
    speak_func: Callable,
    use_elevenlabs: bool = True,
) -> Optional[Future]:
    """
    Fires a background Gemini call to generate a human follow-up.
    Speaks it via ElevenLabs if worth saying.
    """
    if not should_enhance(action, action_result):
        return None

    from core.concurrency import run_background

    def _do_enhance():
        global _last_call_time
        try:
            import os
            from google import genai
            from dotenv import load_dotenv
            from mood.mood_engine import get_mood_for_prompt
            from core.memory import get_context_for_gemini

            load_dotenv()
            client = genai.Client(api_key=os.getenv("API_KEY"))

            mood_context = get_mood_for_prompt()

            prompt = _build_personality_prompt(
                action=action,
                command=command,
                action_result=action_result,
                instant_response=instant_response,
                mood_context=mood_context,
                user_context=get_context_for_gemini(),
            )

            _last_call_time = time.time()  # Mark call time BEFORE request

            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt
            )

            text = response.text.strip().strip('"').strip("'")

            # Don't speak if Gemini says skip or response is too similar
            if text.upper() == "SKIP" or not text:
                print("🔇 Gemini follow-up: SKIP (nothing to add)")
                return

            if text.lower() == instant_response.lower():
                print("🔇 Gemini follow-up: duplicate, skipping")
                return

            # Speak the follow-up (using ElevenLabs for richer voice)
            print(f"🧠 Gemini follow-up: {text}")
            speak_func(text)

        except Exception as e:
            err = str(e)
            if "429" in err or "RESOURCE_EXHAUSTED" in err:
                print("🔇 Background Gemini: rate limited, skipping")
            elif "503" in err or "UNAVAILABLE" in err:
                print("🔇 Background Gemini: service busy, skipping")
            else:
                print(f"⚠️ Background Gemini error: {e}")

    return run_background(_do_enhance)


# ─── Quick test ──────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("  BACKGROUND GEMINI ENHANCEMENT TEST")
    print("=" * 60)

    # Test should_enhance — now everything returns True
    tests = [
        ("open_app",     None),
        ("read_emails",  "3 unread"),
        ("volume_up",    None),
        ("get_battery",  "45%"),
        ("close_tab",    None),
        ("create_file",  "Created test.txt"),
        ("edit_file",    "Appended text"),
    ]

    for action, result in tests:
        should = should_enhance(action, result)
        print(f"  {action:<20} result={str(result):<20} → enhance={should}")
