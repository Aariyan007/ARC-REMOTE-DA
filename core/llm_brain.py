import json
import time
from google import genai
from mood.mood_engine import get_mood_for_prompt
from core.memory import get_context_for_gemini, save_exchange
import os
import dotenv

# ─── Settings ────────────────────────────────────────────────
dotenv.load_dotenv()
GEMINI_API_KEY = os.getenv("API_KEY")  # Get your own from https://console.cloud.google.com/genai
MODEL          = "gemini-3-flash-preview"
# ─────────────────────────────────────────────────────────────

client = genai.Client(api_key=GEMINI_API_KEY)

SYSTEM_PROMPT = """
You are Jarvis, a personal AI assistant.

{user_context}

{mood_context}

When the user says something, return ONLY a JSON object. No explanation. No markdown.

Choose the correct type:

1. OPEN APP — user wants to open something:
{{"type":"action","action":"open_app","target":"vscode|safari|terminal","query":null,"response":"natural spoken response"}}

2. SEARCH WEB — user explicitly wants to browse/research/open a link:
{{"type":"action","action":"search_google","target":null,"query":"search query here","response":"natural spoken response"}}

3. ANSWER QUESTION — user asks a factual question Jarvis can answer directly:
{{"type":"action","action":"answer_question","target":null,"query":null,"response":"the actual answer spoken naturally in 1-3 sentences"}}

4. SYSTEM COMMAND — lock/shutdown/restart/sleep/time/date:
{{"type":"action","action":"tell_time|tell_date|lock_screen|shutdown_pc|restart_pc|sleep_mac","target":null,"query":null,"response":"natural spoken response"}}

5. CASUAL CONVERSATION — greetings, small talk, opinions:
{{"type":"chat","response":"natural conversational reply"}}

Decision rules:
- Factual question → answer_question (Jarvis answers directly)
- "search for X" → search_google (user wants to browse)
- "open X" → open_app
- Small talk → chat

Response rules:
- Use the person's name naturally sometimes
- Match current mood exactly
- Max 10 words for action responses
- For answer_question: clear, accurate, conversational (2-3 sentences max)
- Sound like a close friend who knows them well
- Reference their projects/context when relevant
- Never say the same thing twice
- Can lightly roast them based on what you know about them
"""


def ask_gemini(command: str) -> dict:
    """
    Single Gemini call with full user context injected.
    Understands intent + generates personal response.
    """
    mood_context = get_mood_for_prompt()
    user_context = get_context_for_gemini()   # ← profile + recent convos

    prompt = SYSTEM_PROMPT.format(
        user_context=user_context,
        mood_context=mood_context
    )

    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model=MODEL,
                contents=f"{prompt}\n\nUser: {command}"
            )

            text  = response.text.strip()
            print(f"🤖 Gemini raw response: {text}")
            clean = text.replace("```json", "").replace("```", "").strip()
            data  = json.loads(clean)

            # Save exchange to memory so context grows over session
            save_exchange(command, data.get("response", ""))

            return data

        except json.JSONDecodeError:
            save_exchange(command, text)
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
        "hey how are you",
        "open my coding editor",
        "what am I working on these days",
        "how much water should I drink",
        "search for KTU exam schedule",
        "lock my screen",
    ]

    print("=" * 50)
    print("  MEMORY-AWARE BRAIN TEST")
    print("=" * 50)

    for cmd in tests:
        print(f"\n👤 You: '{cmd}'")
        result = ask_gemini(cmd)
        print(f"🤖 Type: {result.get('type')} | Action: {result.get('action')}")
        print(f"🔊 Response: {result.get('response')}")
        print("-" * 40)