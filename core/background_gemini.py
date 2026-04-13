"""
Background Gemini Enhancement — optional smart follow-up responses.

After the fast engine executes + instant response is spoken,
this module can optionally call Gemini in a background thread
to produce a richer, more personalized follow-up.

Only triggers when the follow-up would ADD VALUE (not repeat
what was already said).
"""

import threading
from typing import Callable, Optional
from concurrent.futures import Future


# ─── Enhancement Triggers ────────────────────────────────────
# Actions where a smart Gemini follow-up adds value.
ENHANCE_ACTIONS = {
    "read_emails":       "Summarize the emails briefly",
    "get_battery":       "Comment on battery level",
    "tell_weather":      "Add a natural comment about the weather",
    "morning_briefing":  "Add personalized context",
    "search_emails":     "Summarize findings",
    "get_recent_files":  "Comment on recent activity",
    "summarise_pdf":     "Give a concise summary",
    "read_file":         "Comment on file contents",
}

# Actions where a follow-up has NO value (don't waste API calls)
SKIP_ACTIONS = {
    "open_app", "close_app", "switch_to_app",
    "volume_up", "volume_down", "mute", "unmute",
    "brightness_up", "brightness_down",
    "lock_screen", "take_screenshot",
    "open_folder", "create_folder",
    "open_gmail", "show_desktop",
    "minimise_all", "close_window", "close_tab", "new_tab",
    "fullscreen", "mission_control", "minimise_app",
    "start_work_day", "end_work_day",
    "create_file", "rename_file", "copy_file",  "delete_file",
}


def should_enhance(action: str, action_result: str = None) -> bool:
    """
    Decides whether a background Gemini follow-up is worth it.

    Args:
        action:        The action that was just executed
        action_result: The result/output of the action (if any)

    Returns:
        True if a smart follow-up would add value
    """
    if action in SKIP_ACTIONS:
        return False

    if action in ENHANCE_ACTIONS:
        return True

    # If the action produced interesting output, enhance
    if action_result and len(str(action_result)) > 50:
        return True

    return False


def generate_followup(
    action: str,
    command: str,
    action_result: str,
    instant_response: str,
    speak_func: Callable,
    use_elevenlabs: bool = True,
) -> Optional[Future]:
    """
    Fires a background Gemini call to generate a smart follow-up.
    If worth saying, queues it for speech after the instant response.

    Args:
        action:            The action that was executed
        command:           The original user command
        action_result:     What the action returned
        instant_response:  What was already spoken
        speak_func:        Function to call to speak the follow-up
        use_elevenlabs:    Whether to use ElevenLabs for the follow-up

    Returns:
        Future if enhancement was triggered, None otherwise
    """
    if not should_enhance(action, action_result):
        return None

    from core.concurrency import run_background

    def _do_enhance():
        try:
            import json
            import os
            from google import genai
            from dotenv import load_dotenv
            from mood.mood_engine import get_mood_for_prompt
            from core.memory import get_context_for_gemini

            load_dotenv()
            client = genai.Client(api_key=os.getenv("API_KEY"))

            context_hint = ENHANCE_ACTIONS.get(action, "Add helpful context")
            mood_context = get_mood_for_prompt()

            prompt = f"""
You are Jarvis, a personal AI assistant.

{mood_context}
{get_context_for_gemini()}

The user said: "{command}"
Action taken: {action}
Action result: {action_result}
Already spoken: "{instant_response}"

Generate a SHORT follow-up response that ADDS VALUE.
Rules:
- DO NOT repeat what was already spoken
- DO NOT just describe what happened
- ADD useful information, context, or personality
- Max 1-2 sentences
- If there's nothing useful to add, respond with exactly: SKIP
- Sound natural and conversational

Just return the response text. Nothing else.
"""

            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt
            )

            text = response.text.strip().strip('"')

            # Don't speak if Gemini says skip or response is too similar
            if text.upper() == "SKIP":
                print("🔇 Gemini follow-up: SKIP (nothing to add)")
                return

            if text.lower() == instant_response.lower():
                print("🔇 Gemini follow-up: duplicate, skipping")
                return

            # Speak the follow-up (using ElevenLabs for richer voice)
            print(f"🧠 Gemini follow-up: {text}")
            speak_func(text)

        except Exception as e:
            print(f"⚠️ Background Gemini error: {e}")

    return run_background(_do_enhance)


# ─── Quick test ──────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("  BACKGROUND GEMINI ENHANCEMENT TEST")
    print("=" * 60)

    # Test should_enhance
    tests = [
        ("open_app",     None),       # Skip
        ("read_emails",  "3 unread"), # Enhance
        ("volume_up",    None),       # Skip
        ("get_battery",  "45%"),      # Enhance
        ("tell_weather", "72°F"),     # Enhance
        ("close_tab",    None),       # Skip
    ]

    for action, result in tests:
        should = should_enhance(action, result)
        print(f"  {action:<20} result={str(result):<15} → enhance={should}")
