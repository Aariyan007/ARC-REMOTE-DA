from core.llm_brain import ask_gemini
from core.logger import log_interaction
from core.voice_response import speak

# ─────────────────────────────────────────────────────────────

def route(command: str, actions: dict) -> None:
    """
    Single Gemini call — understands intent + generates response.
    Speaks response then executes action.
    """
    if not command or not command.strip():
        print("⚠️  Empty command received")
        return

    command = command.strip().lower()
    print(f"\n🔍 Routing: '{command}'")

    # ── Single Gemini call ───────────────────────────────────
    result = ask_gemini(command)
    response_text = result.get("response", "On it.")

    # ── Casual conversation ──────────────────────────────────
    if result["type"] == "chat":
        speak(response_text)
        log_interaction(
            you_said=command,
            action_taken="chat_response",
            was_understood=True,
            sent_to_gemini=True,
            gemini_response=response_text
        )
        return

    # ── Action command ───────────────────────────────────────
    if result["type"] == "action":
        action = result.get("action")
        target = result.get("target")
        query  = result.get("query")

        print(f"⚡ Action: {action} | Target: {target} | Query: {query}")

        # Speak FIRST then execute
        speak(response_text)

        # open_app
        if action == "open_app" and target:
            func_name = f"open_{target}"
            if func_name in actions:
                actions[func_name]()
                log_interaction(
                    you_said=command,
                    action_taken=func_name,
                    was_understood=True,
                    sent_to_gemini=True
                )
            else:
                speak(f"I don't know how to open {target} yet.")
            return

        # search_google
        if action == "search_google":
            if query and "search_google" in actions:
                actions["search_google"](query)
                log_interaction(
                    you_said=command,
                    action_taken="search_google",
                    was_understood=True,
                    sent_to_gemini=True
                )
            else:
                speak("What would you like me to search for?")
            return

        # everything else
        if action in actions:
            actions[action]()
            log_interaction(
                you_said=command,
                action_taken=action,
                was_understood=True,
                sent_to_gemini=True
            )
        else:
            speak("I understood but can't do that yet.")
            log_interaction(
                you_said=command,
                action_taken=action or "unknown",
                was_understood=False,
                sent_to_gemini=True,
                gemini_response=str(result)
            )


# ─── Quick test ──────────────────────────────────────────────
if __name__ == "__main__":

    def fake_open_vscode():   print("🖥️  Opening VS Code")
    def fake_open_safari():   print("🌐  Opening Safari")
    def fake_open_terminal(): print("💻  Opening Terminal")
    def fake_tell_time():     print("🕐  Telling time")
    def fake_tell_date():     print("📅  Telling date")
    def fake_lock_screen():   print("🔒  Locking screen")
    def fake_search(query):   print(f"🔍  Searching: '{query}'")

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
        "yo open my browser",
        "what time is it bro",
        "search for python tutorials",
        "how are you doing",
        "lock my screen please",
    ]

    print("=" * 50)
    print("  ROUTER TEST")
    print("=" * 50)

    for cmd in test_commands:
        route(cmd, test_actions)
        print("-" * 40)