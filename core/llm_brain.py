"""
LLM Brain — Gemini fallback for commands the fast engine can't handle.

This is now the FALLBACK path. The fast intent engine handles most commands.
Gemini is only called when:
1. Fast engine confidence < 0.50
2. Command needs complex understanding
3. Chat/conversation (no action needed)

The INSTANT_CACHE has been removed — replaced by fast_intent.py
"""

import json
import time
from google import genai
from mood.mood_engine import get_mood_for_prompt
from core.memory import get_context_for_gemini, save_exchange
import os
import dotenv


dotenv.load_dotenv()
GEMINI_API_KEY = os.getenv("API_KEY")
MODEL          = "gemini-3-flash-preview"


client = genai.Client(api_key=GEMINI_API_KEY)

# Global session context
SESSION_CONTEXT = {}

def set_context(key: str, value) -> None:
    SESSION_CONTEXT[key] = value

def get_context() -> dict:
    return SESSION_CONTEXT


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

4. SYSTEM COMMAND — lock/shutdown/restart/sleep/time/date/weather:
{{"type":"action","action":"tell_time|tell_date|lock_screen|shutdown_pc|restart_pc|sleep_mac|tell_weather","target":null,"query":null,"response":"natural spoken response"}}

Triggers for tell_weather: "weather", "what's it like outside", "temperature outside"

5. CASUAL CONVERSATION — greetings, small talk, opinions:
{{"type":"chat","response":"natural conversational reply"}}
6. MORNING BRIEFING — user wants a daily summary:
{{"type":"action","action":"morning_briefing","target":null,"query":null,"response":"Sure, here's your briefing."}}

Triggers for morning_briefing: "morning briefing", "brief me", "what's today like", "give me a briefing"

7. FOLDER CONTROL:
{{"type":"action","action":"open_folder","target":"downloads|desktop|documents|projects","query":null,"response":"natural response"}}
{{"type":"action","action":"create_folder","target":"folder name","query":null,"response":"natural response"}}
{{"type":"action","action":"search_file","target":null,"query":"filename","response":"natural response"}}

8. EMAIL COMMANDS:
{{"type":"action","action":"read_emails","target":null,"query":null,"response":"natural response"}}
{{"type":"action","action":"search_emails","target":null,"query":"search term here","response":"natural response"}}
{{"type":"action","action":"send_email","target":null,"query":null,"to":"email","subject":"subject","body":"body","response":"natural response"}}
{{"type":"action","action":"open_gmail","target":null,"query":null,"response":"natural response"}}

Triggers:
- read_emails: "read my emails", "check my inbox", "any new emails"
- search_emails: "any emails from X", "find emails about X", "emails from professor"
- send_email: "send email to X saying Y"
- open_gmail: "open gmail", "open my email"

9. PDF:
{{"type":"action","action":"summarise_pdf","target":null,"query":null,"response":"natural response"}}
Triggers: "summarise pdf", "read this pdf", "what does this pdf say"

10. SYSTEM CONTROLS:
{{"type":"action","action":"volume_up","target":null,"query":null,"amount":10,"response":"natural response"}}
{{"type":"action","action":"volume_down","target":null,"query":null,"amount":10,"response":"natural response"}}
{{"type":"action","action":"close_tab|new_tab|mute|unmute|get_volume|brightness_up|brightness_down|take_screenshot|minimise_all|show_desktop|close_window|get_battery|start_work_day|end_work_day","target":null,"query":null,"response":"natural response"}}
{{"type":"action","action":"minimise_app","target":"safari|vscode|terminal|finder","query":null,"response":"natural response"}}
{{"type":"action","action":"close_app","target":"safari|vscode|terminal","query":null,"response":"natural response"}}
{{"type":"action","action":"switch_to_app","target":"safari|vscode|terminal","query":null,"response":"natural response"}}
{{"type":"action","action":"fullscreen","target":null,"query":null,"response":"natural response"}}
{{"type":"action","action":"mission_control","target":null,"query":null,"response":"natural response"}}


Triggers:
- volume_up: extract amount from sentence. "turn up by 50" → amount:50, "louder" → amount:10
- volume_down: extract amount from sentence. "turn down by 20" → amount:20, "quieter" → amount:10
- mute: "mute", "silence", "shut up"
- get_battery: "battery", "how much battery", "battery level"
- take_screenshot: "screenshot", "capture screen"
- start_work_day: "start my day", "work mode", "begin work"
- end_work_day: "end my day", "finish work", "wrap up"
- close_tab: "close tab", "close this tab"
- new_tab: "new tab", "open new tab"
- minimise_app: "minimise safari", "hide vscode", "minimise terminal"
- close_app: "close safari", "quit vscode", "exit terminal"
- switch_to_app: "switch to safari", "go to vscode", "bring up terminal"
- fullscreen: "fullscreen", "make it fullscreen", "maximise"
- mission_control: "show all windows", "mission control"

11. FILE OPERATIONS:
{{"type":"action","action":"read_file","target":null,"query":null,"filename":"filename.txt","location":"desktop|downloads|null","response":"natural response"}}
{{"type":"action","action":"create_file","target":null,"query":null,"filename":"name","location":"desktop","response":"natural response"}}
{{"type":"action","action":"delete_file","target":null,"query":null,"filename":"filename.txt","location":null,"response":"natural response"}}
{{"type":"action","action":"rename_file","target":null,"query":null,"filename":"old.txt","new_name":"new.txt","response":"natural response"}}
{{"type":"action","action":"get_recent_files","target":null,"query":null,"response":"natural response"}}
{{"type":"action","action":"copy_file","target":null,"query":null,"filename":"file.txt","location":"desktop","response":"natural response"}}

Triggers:
- read_file: "read notes.txt", "open and read jarvis.py", "what's in ideas.txt"
- create_file: "create a file called X", "make a new file named X"
- delete_file: "delete notes.txt", "remove that file", "trash jarvis_test.txt"
- rename_file: "rename notes.txt to ideas.txt"
- get_recent_files: "what files did I work on", "recent files", "what did I edit today"
- copy_file: "copy jarvis.py to desktop"



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
    Gemini fallback — called when fast intent engine can't resolve.
    Understands intent + generates personal response.
    """
    mood_context = get_mood_for_prompt()
    user_context = get_context_for_gemini()

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
    print("  GEMINI FALLBACK BRAIN TEST")
    print("=" * 50)

    for cmd in tests:
        print(f"\n👤 You: '{cmd}'")
        result = ask_gemini(cmd)
        print(f"🤖 Type: {result.get('type')} | Action: {result.get('action')}")
        print(f"🔊 Response: {result.get('response')}")
        print("-" * 40)