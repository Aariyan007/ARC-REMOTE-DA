import json
import os
import time
from datetime import datetime
from google import genai
import dotenv

# ─── Settings ────────────────────────────────────────────────
dotenv.load_dotenv()
GEMINI_API_KEY = os.getenv("API_KEY")
MODEL          = "gemini-2.0-flash"
DATA_DIR       = os.path.join(os.path.dirname(__file__), '..', 'data', 'users')
# ─────────────────────────────────────────────────────────────

client = genai.Client(api_key=GEMINI_API_KEY)


def load_user(name: str) -> dict:
    path = os.path.join(DATA_DIR, f"{name.lower()}.json")
    if not os.path.exists(path):
        print(f"❌ No data found for {name}")
        return None
    with open(path, "r") as f:
        return json.load(f)


def save_user(data: dict) -> None:
    name = data["profile"]["name"]
    path = os.path.join(DATA_DIR, f"{name.lower()}.json")
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def extract_facts(name: str) -> None:
    """
    Reads all conversations for a user.
    Sends to Gemini to extract personal facts.
    Updates their profile with learned facts.
    """
    user_data = load_user(name)
    if not user_data:
        return

    conversations = user_data.get("conversations", [])
    if not conversations:
        print(f"⚠️  No conversations found for {name} yet.")
        print("    Use chat.py first to build up conversation data.")
        return

    # Build conversation text for Gemini
    convo_text = ""
    for session in conversations:
        convo_text += f"\n--- Session: {session['session_date']} ---\n"
        for exchange in session.get("exchanges", []):
            convo_text += f"{name}: {exchange['user']}\n"
            convo_text += f"Jarvis: {exchange['jarvis']}\n"

    print(f"📖 Reading {len(conversations)} sessions for {name}...")
    print(f"📊 Total exchanges: {sum(len(s.get('exchanges',[])) for s in conversations)}")

    prompt = f"""
Read these conversations between {name} and Jarvis.
Extract important personal facts about {name}.

Look for:
- Personal info (university, year, location)
- Work and projects
- Skills and what they work with
- Likes and dislikes
- Habits and routines
- Goals and ambitions
- Personality traits
- Common slang or phrases they use
- Relationships mentioned
- Opinions on things
- Anything memorable or unique about them

Conversations:
{convo_text}

Return a JSON array of facts. Each fact is a short string.
Example format:
["Aariyan studies at MITS under KTU", "Aariyan dislikes CSS", "Aariyan uses 'yo' and 'bro' frequently"]

Return ONLY the JSON array. No explanation. No markdown.
"""

    try:
        print("\n🧠 Sending to Gemini for extraction...")
        response = client.models.generate_content(
            model=MODEL,
            contents=prompt
        )

        text  = response.text.strip()
        clean = text.replace("```json", "").replace("```", "").strip()
        facts = json.loads(clean)

        print(f"\n✅ Extracted {len(facts)} facts about {name}:\n")
        for i, fact in enumerate(facts, 1):
            print(f"  {i}. {fact}")

        # Merge with existing facts (no duplicates)
        existing = user_data["profile"].get("learned_facts", [])
        combined = list(set(existing + facts))

        user_data["profile"]["learned_facts"] = combined
        user_data["profile"]["last_extracted"] = datetime.now().strftime("%Y-%m-%d %H:%M")

        save_user(user_data)
        print(f"\n💾 Profile updated — {len(combined)} total facts stored.")

    except json.JSONDecodeError:
        print(f"❌ Gemini returned unexpected format: {text}")
    except Exception as e:
        if "429" in str(e):
            print("⏳ Rate limited — wait a minute and try again.")
        else:
            print(f"❌ Error: {e}")


def list_users() -> list:
    """Returns list of all users with data files."""
    if not os.path.exists(DATA_DIR):
        return []
    return [f.replace(".json", "") for f in os.listdir(DATA_DIR) if f.endswith(".json")]


def main():
    print("=" * 50)
    print("  JARVIS FACT EXTRACTOR")
    print("=" * 50)

    users = list_users()

    if not users:
        print("❌ No user data found. Use chat.py first.")
        return

    print(f"\nUsers found: {', '.join(users)}")

    if len(users) == 1:
        name = users[0]
        print(f"Extracting facts for: {name}\n")
    else:
        name = input("Which user? ").strip().lower()
        if name not in users:
            print(f"❌ No data found for {name}")
            return

    extract_facts(name)


if __name__ == "__main__":
    main()