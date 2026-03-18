import json
import os
from dotenv import load_dotenv
from google import genai

load_dotenv()
GEMINI_API_KEY = os.getenv("API_KEY")
client = genai.Client(api_key=GEMINI_API_KEY)
MODEL = "gemini-3-flash-preview"
# ─────────────────────────────────────────────────────────────

# This tells Gemini exactly who it is and how to respond
SYSTEM_PROMPT = """
You are Jarvis, a smart personal voice assistant running on a Mac.

When the user says something, you must decide if it's:

A) A COMMAND — something that controls the computer.
   Respond with ONLY a JSON object like this:
   {"action": "open_app", "target": "vscode"}
   {"action": "open_app", "target": "safari"}
   {"action": "open_app", "target": "terminal"}
   {"action": "search_google", "query": "python tutorial"}
   {"action": "tell_time"}
   {"action": "tell_date"}
   {"action": "lock_screen"}
   {"action": "shutdown_pc"}
   {"action": "restart_pc"}

B) CASUAL CONVERSATION — greetings, questions, small talk.
   Respond naturally like a helpful assistant. Keep it short — 1-2 sentences max.
   Do NOT return JSON for casual talk.

Examples:
User: "can you open my coding editor" → {"action": "open_app", "target": "vscode"}
User: "hey how are you" → "I'm doing great! What can I help you with?"
User: "search for python loops" → {"action": "search_google", "query": "python loops"}
User: "what's the weather like" → "I can't check weather yet, but I'm learning new skills!"
User: "open my browser" → {"action": "open_app", "target": "safari"}

Always be concise. Never explain your reasoning. Just respond.
"""


def ask_gemini(command: str) -> dict:
    """
    Sends unknown command to Gemini.
    Returns either:
        {"type": "action", "action": "open_app", "target": "vscode"}
        {"type": "chat", "response": "I'm doing great!"}
    """
    try:
        response = client.models.generate_content(
            model=MODEL,
            contents=f"{SYSTEM_PROMPT}\n\nUser: {command}"
        )

        text = response.text.strip()
        print(f"🤖 Gemini raw response: {text}")

        # Try to parse as JSON (it's a command)
        # Clean up common Gemini formatting
        clean = text.replace("```json", "").replace("```", "").strip()

        try:
            data = json.loads(clean)
            return {"type": "action", **data}
        except json.JSONDecodeError:
            # Not JSON — it's a casual reply
            return {"type": "chat", "response": text}

    except Exception as e:
        print(f"❌ Gemini error: {e}")
        return {"type": "chat", "response": "Sorry, I had trouble understanding that."}


# ─── Quick test ──────────────────────────────────────────────
if __name__ == "__main__":
    test_commands = [
        "hey how are you",
        "can you open my coding editor",
        "search for machine learning tutorials",
        "what's the meaning of life",
        "open my browser please",
    ]

    print("=" * 50)
    print("  GEMINI BRAIN TEST")
    print("=" * 50)

    for cmd in test_commands:
        print(f"\n👤 You: '{cmd}'")
        result = ask_gemini(cmd)
        print(f"🤖 Result: {result}")
        print("-" * 40)