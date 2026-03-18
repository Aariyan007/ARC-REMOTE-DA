import json
import time
from google import genai
from mood.mood_engine import get_mood_for_prompt
from dotenv import load_dotenv
import os

# ─── Settings ────────────────────────────────────────────────
load_dotenv()
GEMINI_API_KEY = os.getenv("API_KEY")
MODEL          = "gemini-3-flash-preview"
# ─────────────────────────────────────────────────────────────

client = genai.Client(api_key=GEMINI_API_KEY)

SYSTEM_PROMPT = """
You are Jarvis, a personal AI assistant for Aariyan.
Aariyan is a 3rd year BTech CS student, full stack developer and entrepreneur.
He talks casually, uses slang, and wants Jarvis to feel like a close friend.

{mood_context}

When the user says something, return a JSON object with:

For COMMANDS (controlling the computer):
{{
  "type": "action",
  "action": "open_app" | "search_google" | "tell_time" | "tell_date" | "lock_screen" | "shutdown_pc" | "restart_pc" | "sleep_mac",
  "target": "vscode" | "safari" | "terminal" | null,
  "query": "search query here" | null,
  "response": "natural spoken response matching current mood"
}}

For CASUAL CONVERSATION:
{{
  "type": "chat",
  "response": "natural conversational reply matching current mood"
}}

Response rules:
- response field must match current mood exactly
- Max 10 words for action responses
- Max 2 sentences for chat responses  
- Sound like a close friend, not a robot
- Never say the same thing twice
- Can lightly roast Aariyan
- Be witty and sarcastic when mood calls for it

Examples:
"yo open safari" → {{"type":"action","action":"open_app","target":"safari","query":null,"response":"Safari up, what are we doing tonight?"}}
"how are you" → {{"type":"chat","response":"Living my best digital life. You?"}}
"search python loops" → {{"type":"action","action":"search_google","target":null,"query":"python loops","response":"Looking up python loops for you."}}

Return ONLY the JSON. No explanation. No markdown.
"""


def ask_gemini(command: str) -> dict:
    """
    Single Gemini call that both understands intent AND generates response.
    Returns dict with type, action details, and natural response.
    """
    mood_context = get_mood_for_prompt()
    prompt = SYSTEM_PROMPT.format(mood_context=mood_context)

    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model=MODEL,
                contents=f"{prompt}\n\nUser: {command}"
            )

            text = response.text.strip()
            print(f"🤖 Gemini raw response: {text}")

            # Clean markdown if present
            clean = text.replace("```json", "").replace("```", "").strip()

            data = json.loads(clean)
            return data

        except json.JSONDecodeError:
            # Not valid JSON — treat as chat
            return {"type": "chat", "response": text}

        except Exception as e:
            if "429" in str(e):
                wait = 15 * (attempt + 1)
                print(f"⏳ Rate limited — waiting {wait}s...")
                time.sleep(wait)
            else:
                print(f"❌ Gemini error: {e}")
                return {"type": "chat", "response": "Sorry, I had trouble with that."}

    return {"type": "chat", "response": "Sorry, I had trouble with that."}


# ─── Quick test ──────────────────────────────────────────────
if __name__ == "__main__":
    tests = [
        "yo open my browser",
        "what time is it bro",
        "search for machine learning",
        "how are you doing",
        "lock my screen please",
    ]

    print("=" * 50)
    print("  COMBINED BRAIN TEST")
    print("=" * 50)

    for cmd in tests:
        print(f"\n👤 You: '{cmd}'")
        result = ask_gemini(cmd)
        print(f"🤖 Result: {result}")
        print(f"🔊 Response: {result.get('response')}")
        print("-" * 40)