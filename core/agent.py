import json
import os
from datetime import datetime
from google import genai
from dotenv import load_dotenv

load_dotenv()

# ─── Settings ────────────────────────────────────────────────
GEMINI_API_KEY = os.getenv("API_KEY")
MODEL          = "gemini-3-flash-preview"
MAX_STEPS      = 5   # max actions before giving up
# ─────────────────────────────────────────────────────────────

client = genai.Client(api_key=GEMINI_API_KEY)
LAST_AGENT_RESULT = {}

# ── Available Tools Description ──────────────────────────────
TOOLS_DESCRIPTION = """
Available actions you can take:

FILE OPERATIONS:
- search_file(name) → finds files matching name, returns list of paths
- open_file(path) → opens a specific file
- read_file(path) → reads and returns file contents (text files only)
- create_file(name, location) → creates a new file
- delete_file(path) → moves file to trash
- rename_file(old_path, new_name) → renames a file
- recent_files() → returns list of recently modified files

FOLDER OPERATIONS:
- open_folder(name) → opens a folder in Finder
- create_folder(name, location) → creates a new folder

EMAIL:
- read_emails() → returns list of unread emails
- search_emails(query) → searches emails, returns matches with subjects + bodies
- send_email(to, subject, body) → opens Gmail compose

SYSTEM:
- get_battery() → returns battery percentage
- get_volume() → returns current volume
- take_screenshot() → takes screenshot, returns saved path
- get_recent_files() → returns recently modified files

APPS:
- open_app(name) → opens an app (vscode, safari, terminal)
- close_app(name) → closes an app

WEB:
- search_google(query) → opens Google search
- answer_question(question) → answers a factual question directly

SPEAK:
- speak(text) → speaks text to user (use for updates + final answer)
"""


# ── Agent Prompt ─────────────────────────────────────────────
def _build_agent_prompt(
    command: str,
    history: list,
    observation: str,
    user_context: str,
    mood_context: str
) -> str:

    history_text = ""
    if history:
        history_text = "\nSteps taken so far:\n"
        for i, step in enumerate(history, 1):
            history_text += f"Step {i}: Action={step['action']} Params={step['params']}\n"
            history_text += f"        Result={step['observation'][:200]}\n"

    obs_text = f"\nLast observation: {observation}" if observation else ""

    return f"""
You are Jarvis, an intelligent AI agent assistant.

{user_context}
{mood_context}

{TOOLS_DESCRIPTION}

{history_text}
{obs_text}

User's request: "{command}"

Think step by step. Decide what single action to take next.

If you need more information → take an action to get it.
If you have enough information → give the final answer.
If the task is complete → respond with done.

Return ONLY a JSON object. No explanation. No markdown.

To take an action:
{{"type": "act", "action": "action_name", "params": {{"key": "value"}}, "thinking": "why I'm doing this"}}

To give final answer (task complete):
{{"type": "done", "response": "natural spoken response to user"}}

Examples:
User: "find my latest resume"
→ {{"type": "act", "action": "search_file", "params": {{"name": "resume"}}, "thinking": "need to find resume files first"}}

After seeing files found:
→ {{"type": "act", "action": "open_file", "params": {{"path": "/Users/lynux/Downloads/Latest_resume.pdf"}}, "thinking": "Latest_resume.pdf is clearly the newest one"}}

After opening:
→ {{"type": "done", "response": "Opened your latest resume. Good luck if you're applying somewhere."}}
"""


# ── Execute Action ────────────────────────────────────────────
def _execute_action(action: str, params: dict, actions: dict) -> str:
    """
    Executes an action and returns a string observation.
    The observation is fed back to Gemini for next step.
    """
    try:
        # ── File operations ──────────────────────────────────
        if action == "search_file":
            name   = params.get("name", "")
            result = _spotlight_search(name)
            if result:
                files_text = "\n".join([
                    f"{i+1}. {os.path.basename(f)} at {f}"
                    for i, f in enumerate(result[:8])
                ])
                return f"Found {len(result)} files:\n{files_text}"
            return f"No files found matching '{name}'"

        if action == "open_file":
            path = params.get("path", "")
            if os.path.exists(path):
                import subprocess
                subprocess.Popen(["open", path])
                return f"Opened {os.path.basename(path)} successfully"
            return f"File not found: {path}"

        if action == "read_file":
            path = params.get("path", "")
            if os.path.exists(path):
                with open(path, "r", errors="ignore") as f:
                    content = f.read()[:2000]
                return f"File contents:\n{content}"
            return f"File not found: {path}"

        if action == "recent_files":
            import subprocess
            result = subprocess.run(
                ["mdfind", "-onlyin", os.path.expanduser("~"),
                 "kMDItemContentModificationDate >= $time.today(-1)"],
                capture_output=True, text=True, timeout=10
            )
            files = [
                f for f in result.stdout.strip().split("\n")
                if f and not any(s in f for s in ["venv", ".git", "Library", "cache"])
            ][:10]
            return f"Recent files: {', '.join([os.path.basename(f) for f in files])}"

        # ── Email ────────────────────────────────────────────
        if action == "search_emails":
            query = params.get("query", "")
            if "search_emails" in actions:
                # Capture email results
                return _search_emails_for_agent(query)
            return "Email search not available"

        if action == "read_emails":
            return _read_emails_for_agent()

        # ── App control ──────────────────────────────────────
        if action == "open_app":
            name = params.get("name", "")
            func = f"open_{name.lower().replace(' ', '_')}"
            if func in actions:
                actions[func]()
                return f"Opened {name}"
            return f"Don't know how to open {name}"

        # ── System ───────────────────────────────────────────
        if action == "get_battery":
            import subprocess, re
            result = subprocess.run(["pmset", "-g", "batt"],
                                   capture_output=True, text=True)
            match = re.search(r'(\d+)%', result.stdout)
            if match:
                return f"Battery is at {match.group(1)}%"
            return "Couldn't read battery"

        if action == "take_screenshot":
            if "take_screenshot" in actions:
                actions["take_screenshot"]()
                return "Screenshot taken and saved to Desktop"
            return "Screenshot action not available"

        # ── Answer question ──────────────────────────────────
        if action == "answer_question":
            question = params.get("question", "")
            return f"question_to_answer:{question}"

        # ── Speak update ─────────────────────────────────────
        if action == "speak":
            text = params.get("text", "")
            from core.voice_response import speak as _speak
            _speak(text)
            return f"Spoke: {text}"

        # ── Generic actions from ACTIONS dict ────────────────
        if action in actions:
            actions[action]()
            return f"Executed {action} successfully"

        return f"Unknown action: {action}"

    except Exception as e:
        return f"Error executing {action}: {str(e)}"


def _spotlight_search(name: str) -> list:
    """Searches for files using Spotlight, filters junk."""
    import subprocess
    result = subprocess.run(
        ["mdfind", "-name", name],
        capture_output=True, text=True, timeout=10
    )
    return [
        f for f in result.stdout.strip().split("\n")
        if f and not any(skip in f for skip in [
            "venv", ".git", "Library/Caches", ".pyc",
            "node_modules", "/System/", "/private/", "/usr/",
            "PrivateFrameworks", ".framework", ".app/Contents"
        ])
    ]


def _search_emails_for_agent(query: str) -> str:
    """Searches emails and returns results as text for agent."""
    try:
        import base64
        from control.email_control import get_gmail_service
        service = get_gmail_service()
        results = service.users().messages().list(
            userId="me", q=query, maxResults=3
        ).execute()
        messages = results.get("messages", [])
        if not messages:
            return f"No emails found for '{query}'"
        output = f"Found {len(messages)} emails:\n"
        for msg in messages:
            data = service.users().messages().get(
                userId="me", id=msg["id"], format="metadata",
                metadataHeaders=["Subject", "From"]
            ).execute()
            headers = {h["name"]: h["value"] for h in data["payload"]["headers"]}
            output += f"- From: {headers.get('From','?')} | Subject: {headers.get('Subject','?')}\n"
        return output
    except Exception as e:
        return f"Email error: {e}"


def _read_emails_for_agent() -> str:
    """Reads unread emails and returns as text for agent."""
    try:
        from control.email_control import get_gmail_service
        service  = get_gmail_service()
        results  = service.users().messages().list(
            userId="me", labelIds=["INBOX", "UNREAD"], maxResults=5
        ).execute()
        messages = results.get("messages", [])
        if not messages:
            return "No unread emails"
        output = f"{len(messages)} unread emails:\n"
        for msg in messages:
            data = service.users().messages().get(
                userId="me", id=msg["id"], format="metadata",
                metadataHeaders=["Subject", "From"]
            ).execute()
            headers = {h["name"]: h["value"] for h in data["payload"]["headers"]}
            output += f"- From: {headers.get('From','?')} | Subject: {headers.get('Subject','?')}\n"
        return output
    except Exception as e:
        return f"Email error: {e}"


# ── Main Agent Loop ──────────────────────────────────────────
def run_agent(command: str, actions: dict) -> None:
    global LAST_AGENT_RESULT
    """
    ReAct agent loop:
    Think → Act → Observe → Think again → repeat
    """
    from core.memory import get_context_for_gemini
    from mood.mood_engine import get_mood_for_prompt
    from core.voice_response import speak
    from core.logger import log_interaction

    print(f"\n🤖 Agent starting: '{command}'")

    history     = []
    observation = ""

    for step in range(MAX_STEPS):
        print(f"\n── Step {step + 1} ──────────────────")

        # Build prompt
        prompt = _build_agent_prompt(
            command        = command,
            history        = history,
            observation    = observation,
            user_context   = get_context_for_gemini(),
            mood_context   = get_mood_for_prompt()
        )

        # Think
        try:
            response = client.models.generate_content(
                model=MODEL,
                contents=prompt
            )
            text  = response.text.strip()
            clean = text.replace("```json", "").replace("```", "").strip()
            result = json.loads(clean)
            print(f"🧠 Thinking: {result.get('thinking', '')}")
            print(f"📋 Decision: {result}")

        except Exception as e:
            print(f"❌ Agent error: {e}")
            speak("Sorry, I had trouble with that.")
            return

        # Done — task complete
        if result.get("type") == "done":
            speak(result["response"])
            log_interaction(
                you_said=command,
                action_taken="agent_done",
                was_understood=True,
                sent_to_gemini=True,
                gemini_response=result["response"]
            )
            return
        LAST_AGENT_RESULT = {
        "command": command,
        "files_found": [step["observation"] for step in history],
        "last_action": history[-1] if history else {}
        }

        # Act
        if result.get("type") == "act":
            action = result.get("action", "")
            params = result.get("params", {})

            print(f"⚡ Acting: {action}({params})")

            # Execute and observe
            observation = _execute_action(action, params, actions)
            print(f"👁️  Observed: {observation[:150]}")

            history.append({
                "action":      action,
                "params":      params,
                "observation": observation
            })

        else:
            speak("Something went wrong. Try again.")
            return

    # Hit max steps
    speak("I tried my best but couldn't complete that fully.")


# ─── Quick test ──────────────────────────────────────────────
if __name__ == "__main__":
    print("Testing ReAct agent...\n")

    fake_actions = {
        "open_vscode":  lambda: print("Opening VS Code"),
        "open_safari":  lambda: print("Opening Safari"),
    }

    run_agent("find my latest resume and open it", fake_actions)