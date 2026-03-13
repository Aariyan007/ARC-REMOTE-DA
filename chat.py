import json
import os
import time
from datetime import datetime
from google import genai
from dotenv import load_dotenv

# ─── Settings ────────────────────────────────────────────────
load_dotenv()
GEMINI_API_KEY = os.getenv("API_KEY")
MODEL          = "gemini-3-flash-preview"
DATA_DIR       = os.path.join(os.path.dirname(__file__), "data", "users")
# ─────────────────────────────────────────────────────────────

client       = genai.Client(api_key=GEMINI_API_KEY)
session_start = None


# ── Timer ─────────────────────────────────────────────────────

def session_time() -> str:
    elapsed = int(time.time() - session_start)
    return f"{elapsed // 60:02d}:{elapsed % 60:02d}"


# ── Single File Per User ──────────────────────────────────────

def get_user_path(name: str) -> str:
    os.makedirs(DATA_DIR, exist_ok=True)
    return os.path.join(DATA_DIR, f"{name.lower()}.json")


def load_user(name: str) -> dict:
    """Loads user data or returns empty structure."""
    path = get_user_path(name)
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return None


def save_user(data: dict) -> None:
    """Saves everything back to the single user file."""
    path = get_user_path(data["profile"]["name"])
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def setup_new_user(name: str) -> dict:
    """Runs first-time setup for a new user."""
    print(f"\n👋 Hey {name}! First time here. Quick setup:\n")

    role     = input("What do you do? (developer/student/designer/etc): ").strip()
    works    = input("What do you work with? (Python, JS, design, etc): ").strip()
    projects = input("Any current projects?: ").strip()
    style    = input("How should Jarvis talk to you? (casual/professional/funny): ").strip()

    data = {
        "profile": {
            "name":          name,
            "role":          role,
            "works_with":    [w.strip() for w in works.split(",")],
            "projects":      [projects] if projects else [],
            "style":         style,
            "joined":        datetime.now().strftime("%Y-%m-%d"),
            "notes":         [],
            "learned_facts": []
        },
        "conversations": []
    }

    save_user(data)
    print(f"\n✅ Profile created! Let's talk, {name}.\n")
    return data


# ── Gemini Chat ───────────────────────────────────────────────

def build_system_prompt(profile: dict) -> str:
    return f"""
You are Jarvis, a personal AI assistant and close friend.

Talking to: {profile['name']}
Role: {profile['role']}
Works with: {', '.join(profile['works_with'])}
Projects: {', '.join(profile['projects']) if profile['projects'] else 'not mentioned yet'}
Talk style: {profile['style']}

Rules:
- Talk like a close friend, not a robot
- Keep responses short — 1-3 sentences max
- Remember everything said earlier in this conversation
- Ask natural follow up questions
- Be witty, sarcastic, or funny when appropriate
- If they share something personal, respond warmly
- Never repeat the same response twice
"""


def chat_with_gemini(profile: dict, session_history: list, user_message: str) -> str | None:
    """Sends message to Gemini, returns response or None if failed."""
    messages = build_system_prompt(profile) + "\n\nConversation:\n"

    for turn in session_history:
        if turn["jarvis"]:
            messages += f"{profile['name']}: {turn['user']}\nJarvis: {turn['jarvis']}\n"

    messages += f"{profile['name']}: {user_message}\nJarvis:"

    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model=MODEL,
                contents=messages
            )
            return response.text.strip()

        except Exception as e:
            if "429" in str(e):
                wait = 15 * (attempt + 1)
                print(f"  ⏳ Rate limited — waiting {wait}s... [{session_time()}]")
                time.sleep(wait)
            else:
                print(f"  ❌ Error: {e}")
                return None

    return None


# ── Main Chat Loop ────────────────────────────────────────────

def main():
    global session_start
    session_start = time.time()

    print("\n" + "=" * 50)
    print("  JARVIS CHAT")
    print("  Type 'bye' to exit")
    print("=" * 50)

    name = input("\nWhat's your name? ").strip()
    if not name:
        print("Need a name to continue.")
        return

    # Load or create user
    user_data = load_user(name)
    if user_data:
        print(f"\n✅ Welcome back, {name}!")
    else:
        user_data = setup_new_user(name)

    profile         = user_data["profile"]
    session_history = []   # just this session's turns

    print(f"\nJarvis: Hey {profile['name']}! What's on your mind?  [{session_time()}]\n")

    while True:
        try:
            user_input = input(f"{profile['name']}: ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if not user_input:
            continue

        if any(w in user_input.lower() for w in ["bye", "goodbye", "exit", "quit", "that's enough"]):
            print(f"\nJarvis: Talk later, {profile['name']}. Take care! 👋  [{session_time()}]")
            break

        # Get Gemini response
        response = chat_with_gemini(profile, session_history, user_input)

        if response:
            print(f"\nJarvis: {response}  [{session_time()}]\n")
        else:
            print(f"\nJarvis: [couldn't respond — saved your message anyway]  [{session_time()}]\n")

        session_history.append({
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "user":      user_input,
            "jarvis":    response
        })

    # Append this session to the single user file
    if session_history:
        clean = [e for e in session_history if e["jarvis"]]
        if clean:
            user_data["conversations"].append({
                "session_date": datetime.now().strftime("%Y-%m-%d"),
                "session_time": session_time(),
                "exchanges":    clean
            })
            save_user(user_data)

            print(f"\n💾 Saved to data/users/{name.lower()}.json")
            print(f"📊 {len(clean)}/{len(session_history)} exchanges recorded")
            print(f"⏱  Session time: {session_time()}")
            print(f"📁 Total sessions stored: {len(user_data['conversations'])}")


if __name__ == "__main__":
    main()