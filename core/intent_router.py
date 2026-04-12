from core.llm_brain import ask_gemini
from core.logger import log_interaction
from core.voice_response import speak


def route(command: str, actions: dict) -> bool:
    """
    Single Gemini call — understands intent + generates response.
    Returns True if completed, False if user interrupted mid-speech.
    """
    if not command or not command.strip():
        print("⚠️  Empty command received")
        return True

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
        completed = speak(response_text)
        log_interaction(
            you_said=command,
            action_taken="chat_response",
            was_understood=True,
            sent_to_gemini=True,
            gemini_response=response_text
        )
        return completed   # False if interrupted

    # ── Action command ───────────────────────────────────────
    if result["type"] == "action":
        print(f"⚡ Action: {action} | Target: {target} | Query: {query}")

        # ── Answer question ──────────────────────────────────
        if action == "answer_question":
            completed = speak(response_text)
            log_interaction(you_said=command, action_taken="answer_question",
                          was_understood=True, sent_to_gemini=True,
                          gemini_response=response_text)
            return completed

        # ── Speak first, then execute ────────────────────────
        # For all actions: speak the response then do the action
        # If interrupted during speech → skip action, return False
        completed = speak(response_text)
        if not completed:
            log_interaction(you_said=command, action_taken=action or "interrupted",
                          was_understood=True, sent_to_gemini=True)
            return False   # user interrupted — main loop will listen again

        # ── Open app ─────────────────────────────────────────
        if action == "open_app" and target:
            func_name = f"open_{target.lower().replace(' ', '_')}"
            speak(response_text)
            if func_name in actions:
                actions[func_name]()
            else:
                # Try opening any app by name
                from control.mac.open_apps import open_any_app
                open_any_app(target)
            log_interaction(...)
            return

        # ── Search Google ─────────────────────────────────────
        if action == "search_google":
            if query and "search_google" in actions:
                actions["search_google"](query)
                log_interaction(you_said=command, action_taken="search_google",
                              was_understood=True, sent_to_gemini=True)
            else:
                speak("What would you like me to search for?")
            return True

        # ── Folder control ────────────────────────────────────
        if action == "open_folder":
            if "open_folder" in actions and target:
                actions["open_folder"](target)
                log_interaction(you_said=command, action_taken="open_folder",
                              was_understood=True, sent_to_gemini=True)
            return True

        if action == "create_folder":
            if "create_folder" in actions and target:
                actions["create_folder"](target)
                log_interaction(you_said=command, action_taken="create_folder",
                              was_understood=True, sent_to_gemini=True)
            return True

        if action == "search_file":
            if "search_file" in actions and query:
                actions["search_file"](query)
                log_interaction(you_said=command, action_taken="search_file",
                              was_understood=True, sent_to_gemini=True)
            return True

        # ── Email ─────────────────────────────────────────────
        if action == "search_emails":
            if "search_emails" in actions and query:
                actions["search_emails"](query)
                log_interaction(you_said=command, action_taken="search_emails",
                              was_understood=True, sent_to_gemini=True)
            return True

        if action == "send_email":
            if "send_email" in actions:
                actions["send_email"](
                    result.get("to", ""),
                    result.get("subject", ""),
                    result.get("body", "")
                )
                log_interaction(you_said=command, action_taken="send_email",
                              was_understood=True, sent_to_gemini=True)
            return True

        # ── Volume with amount ────────────────────────────────
        if action == "volume_up":
            amount = int(result.get("amount", 10))
            if "volume_up" in actions:
                actions["volume_up"](amount)
            log_interaction(you_said=command, action_taken="volume_up",
                          was_understood=True, sent_to_gemini=True)
            return True

        if action == "volume_down":
            amount = int(result.get("amount", 10))
            if "volume_down" in actions:
                actions["volume_down"](amount)
            log_interaction(you_said=command, action_taken="volume_down",
                          was_understood=True, sent_to_gemini=True)
            return True

        # ── Minimise/close specific app ───────────────────────
        if action == "minimise_app":
            if "minimise_app" in actions and target:
                actions["minimise_app"](target)
                log_interaction(you_said=command, action_taken="minimise_app",
                              was_understood=True, sent_to_gemini=True)
            return True

        if action == "close_app":
            if "close_app" in actions and target:
                actions["close_app"](target)
                log_interaction(you_said=command, action_taken="close_app",
                              was_understood=True, sent_to_gemini=True)
            return True

        if action == "switch_to_app":
            if "switch_to_app" in actions and target:
                actions["switch_to_app"](target)
                log_interaction(you_said=command, action_taken="switch_to_app",
                              was_understood=True, sent_to_gemini=True)
            return True
        
        if action == "read_file":
            speak(response_text)
            filename = result.get("filename", "")
            location = result.get("location")
            if filename and "read_file" in actions:
                actions["read_file"](filename, location)
            log_interaction(you_said=command, action_taken="read_file",
                        was_understood=True, sent_to_gemini=True)
            return

        if action == "create_file":
            speak(response_text)
            filename = result.get("filename", "")
            location = result.get("location", "desktop")
            if filename and "create_file" in actions:
                actions["create_file"](filename, location)
            log_interaction(you_said=command, action_taken="create_file",
                        was_understood=True, sent_to_gemini=True)
            return

        if action == "delete_file":
            speak(response_text)
            filename = result.get("filename", "")
            location = result.get("location")
            if filename and "delete_file" in actions:
                actions["delete_file"](filename, location)
            log_interaction(you_said=command, action_taken="delete_file",
                        was_understood=True, sent_to_gemini=True)
            return

        if action == "rename_file":
            speak(response_text)
            filename = result.get("filename", "")
            new_name = result.get("new_name", "")
            location = result.get("location")
            if filename and new_name and "rename_file" in actions:
                actions["rename_file"](filename, new_name, location)
            log_interaction(you_said=command, action_taken="rename_file",
                        was_understood=True, sent_to_gemini=True)
            return

        if action == "copy_file":
            speak(response_text)
            filename = result.get("filename", "")
            location = result.get("location", "desktop")
            if filename and "copy_file" in actions:
                actions["copy_file"](filename, location)
            log_interaction(you_said=command, action_taken="copy_file",
                        was_understood=True, sent_to_gemini=True)
            return

        # ── Everything else ───────────────────────────────────
        if action in actions:
            actions[action]()
            log_interaction(you_said=command, action_taken=action,
                          was_understood=True, sent_to_gemini=True)
        else:
            speak("I understood but can't do that yet.")
            log_interaction(you_said=command, action_taken=action or "unknown",
                          was_understood=False, sent_to_gemini=True,
                          gemini_response=str(result))

    return True