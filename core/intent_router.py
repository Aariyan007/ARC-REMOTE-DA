from core.llm_brain import ask_gemini
from core.logger import log_interaction
from core.voice_response import speak


def route(command: str, actions: dict) -> None:
    """
    Single Gemini call — understands intent + generates response.
    """
    if not command or not command.strip():
        print("⚠️  Empty command received")
        return

    command       = command.strip().lower()
    print(f"\n🔍 Routing: '{command}'")

    result        = ask_gemini(command)
    response_text = result.get("response", "On it.")
    action        = result.get("action")
    target        = result.get("target")
    query         = result.get("query")

    print(f"🤖 Gemini understood: {result}")

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
        print(f"⚡ Action: {action} | Target: {target} | Query: {query}")

        # ── Answer question directly ─────────────────────────
        if action == "answer_question":
            speak(response_text)
            log_interaction(you_said=command, action_taken="answer_question",
                          was_understood=True, sent_to_gemini=True,
                          gemini_response=response_text)
            return

        # ── Open app ─────────────────────────────────────────
        if action == "open_app" and target:
            func_name = f"open_{target}"
            speak(response_text)
            if func_name in actions:
                actions[func_name]()
                log_interaction(you_said=command, action_taken=func_name,
                              was_understood=True, sent_to_gemini=True)
            else:
                speak(f"I don't know how to open {target} yet.")
            return

        # ── Search Google ─────────────────────────────────────
        if action == "search_google":
            speak(response_text)
            if query and "search_google" in actions:
                actions["search_google"](query)
                log_interaction(you_said=command, action_taken="search_google",
                              was_understood=True, sent_to_gemini=True)
            else:
                speak("What would you like me to search for?")
            return

        # ── Folder control ────────────────────────────────────
        if action == "open_folder":
            speak(response_text)
            if "open_folder" in actions and target:
                actions["open_folder"](target)
                log_interaction(you_said=command, action_taken="open_folder",
                              was_understood=True, sent_to_gemini=True)
            return

        if action == "create_folder":
            speak(response_text)
            if "create_folder" in actions and target:
                actions["create_folder"](target)
                log_interaction(you_said=command, action_taken="create_folder",
                              was_understood=True, sent_to_gemini=True)
            return

        if action == "search_file":
            speak(response_text)
            if "search_file" in actions and query:
                actions["search_file"](query)
                log_interaction(you_said=command, action_taken="search_file",
                              was_understood=True, sent_to_gemini=True)
            return

        # ── Email ─────────────────────────────────────────────
        if action == "search_emails":
            speak(response_text)
            if "search_emails" in actions and query:
                actions["search_emails"](query)
                log_interaction(you_said=command, action_taken="search_emails",
                              was_understood=True, sent_to_gemini=True)
            return

        if action == "send_email":
            speak(response_text)
            if "send_email" in actions:
                to     = result.get("to", "")
                subject= result.get("subject", "")
                body   = result.get("body", "")
                actions["send_email"](to, subject, body)
                log_interaction(you_said=command, action_taken="send_email",
                              was_understood=True, sent_to_gemini=True)
            return

        # ── Everything else (tell_time, lock_screen, etc) ────
        if action in actions:
            speak(response_text)
            actions[action]()
            log_interaction(you_said=command, action_taken=action,
                          was_understood=True, sent_to_gemini=True)
        else:
            speak("I understood but can't do that yet.")
            log_interaction(you_said=command, action_taken=action or "unknown",
                          was_understood=False, sent_to_gemini=True,
                          gemini_response=str(result))


# ─── Quick test ──────────────────────────────────────────────
if __name__ == "__main__":

    def fake_open_vscode():      print("🖥️  Opening VS Code")
    def fake_open_safari():      print("🌐  Opening Safari")
    def fake_open_terminal():    print("💻  Opening Terminal")
    def fake_tell_time():        print("🕐  Telling time")
    def fake_tell_date():        print("📅  Telling date")
    def fake_lock_screen():      print("🔒  Locking screen")
    def fake_search(query):      print(f"🔍  Searching: '{query}'")
    def fake_open_folder(t):     print(f"📁  Opening folder: '{t}'")
    def fake_create_folder(t):   print(f"📁  Creating folder: '{t}'")
    def fake_search_file(q):     print(f"🔍  Searching file: '{q}'")
    def fake_read_emails():      print("📧  Reading emails")
    def fake_search_emails(q):   print(f"📧  Searching emails: '{q}'")
    def fake_summarise_pdf():    print("📄  Summarising PDF")

    test_actions = {
        "open_vscode":    fake_open_vscode,
        "open_safari":    fake_open_safari,
        "open_terminal":  fake_open_terminal,
        "tell_time":      fake_tell_time,
        "tell_date":      fake_tell_date,
        "lock_screen":    fake_lock_screen,
        "search_google":  fake_search,
        "open_folder":    fake_open_folder,
        "create_folder":  fake_create_folder,
        "search_file":    fake_search_file,
        "read_emails":    fake_read_emails,
        "search_emails":  fake_search_emails,
        "summarise_pdf":  fake_summarise_pdf,
    }

    test_commands = [
        "open my downloads folder",
        "create a folder called ML Project",
        "search for jarvis.py",
        "read my emails",
        "any emails from professor",
        "summarise the latest pdf",
        "what time is it",
        "how are you",
    ]

    print("=" * 50)
    print("  ROUTER TEST")
    print("=" * 50)

    for cmd in test_commands:
        route(cmd, test_actions)
        print("-" * 40)