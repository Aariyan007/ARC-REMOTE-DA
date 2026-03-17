from core.llm_brain import ask_gemini
from core.logger import log_interaction
from core.voice_response import speak

# ─── Action Map ──────────────────────────────────────────────
ACTION_MAP = {
    "open_vscode",
    "open_safari",
    "open_terminal",
    "search_google",
    "tell_time",
    "tell_date",
    "lock_screen",
    "shutdown_pc",
    "restart_pc",
    "sleep_mac",
}
# ─────────────────────────────────────────────────────────────


def route(command: str, actions: dict) -> None:
    """
    Sends every command to Gemini for understanding.
    Passes original command to each action for dynamic responses.
    """
    if not command or not command.strip():
        print("⚠️  Empty command received")
        return

    command = command.strip().lower()
    print(f"\n🔍 Routing: '{command}'")

    # ── Send to Gemini ───────────────────────────────────────
    result = ask_gemini(command)
    print(f"🤖 Gemini understood: {result}")

    # ── Casual conversation ──────────────────────────────────
    if result["type"] == "chat":
        speak(result["response"])
        log_interaction(
            you_said=command,
            action_taken="chat_response",
            was_understood=True,
            sent_to_gemini=True,
            gemini_response=result["response"]
        )
        return

    # ── Action command ───────────────────────────────────────
    if result["type"] == "action":
        action = result.get("action")
        target = result.get("target")
        query  = result.get("query")

        print(f"⚡ Action: {action} | Target: {target} | Query: {query}")

        # open_app → maps to open_vscode / open_safari / open_terminal
        if action == "open_app" and target:
            func_name = f"open_{target}"
            if func_name in actions:
                actions[func_name](command)          # ← pass command
                log_interaction(
                    you_said=command,
                    action_taken=func_name,
                    was_understood=True,
                    sent_to_gemini=True
                )
            else:
                speak(f"Sorry, I don't know how to open {target} yet.")
            return

        # search_google → needs query
        if action == "search_google":
            if query and "search_google" in actions:
                actions["search_google"](query, command)   # ← pass both
                log_interaction(
                    you_said=command,
                    action_taken="search_google",
                    was_understood=True,
                    sent_to_gemini=True
                )
            else:
                speak("What would you like me to search for?")
            return

        # All other actions — tell_time, lock_screen, etc
        if action in actions:
            actions[action](command)                 # ← pass command
            log_interaction(
                you_said=command,
                action_taken=action,
                was_understood=True,
                sent_to_gemini=True
            )
        else:
            speak("I understood what you want but I can't do that yet.")
            log_interaction(
                you_said=command,
                action_taken=action or "unknown",
                was_understood=False,
                sent_to_gemini=True,
                gemini_response=str(result)
            )


# ─── Quick test ──────────────────────────────────────────────
if __name__ == "__main__":

    def fake_open_vscode(u):    print(f"🖥️  Opening VS Code | user said: '{u}'")
    def fake_open_safari(u):    print(f"🌐  Opening Safari | user said: '{u}'")
    def fake_open_terminal(u):  print(f"💻  Opening Terminal | user said: '{u}'")
    def fake_tell_time(u):      print(f"🕐  Telling time | user said: '{u}'")
    def fake_tell_date(u):      print(f"📅  Telling date | user said: '{u}'")
    def fake_lock_screen(u):    print(f"🔒  Locking screen | user said: '{u}'")
    def fake_search(q, u):      print(f"🔍  Searching: '{q}' | user said: '{u}'")

    test_actions = {
        "open_vscode":    fake_open_vscode,
        "open_safari":    fake_open_safari,
        "open_terminal":  fake_open_terminal,
        "tell_time":      fake_tell_time,
        "tell_date":      fake_tell_date,
        "lock_screen":    fake_lock_screen,
        "search_google":  fake_search,
    }

    test_commands = [
        "hey could you pull up my coding editor",
        "yo open my browser",
        "what time is it bro",
        "search for python tutorials",
        "how are you doing today",
        "lock my screen please",
    ]

    print("=" * 50)
    print("  GEMINI-FIRST ROUTER TEST")
    print("=" * 50)

    for cmd in test_commands:
        route(cmd, test_actions)
        print("-" * 40)