"""
Intent Router — the core speed-first pipeline.

Pipeline:
    listen() → normalize() → resolve_context() → fast_intent()
    → safety_check() → execute + instant_response
                                    ↓ (background)
                              gemini_enhance()

If fast engine fails → Gemini fallback → learn from result.
"""

import time
from core.normalizer import normalize
from core.fast_intent import classify, IntentResult
from core.param_extractors import (
    extract_app_name, extract_amount, extract_query,
    extract_filename, extract_email_params, extract_folder_target,
    extract_file_edit_params, is_compound_file_command,
    extract_compound_file_params,
)
from core.instant_responses import get_instant_response, get_confirmation_prompt
from core.safety import check_safety, SafetyDecision, ask_voice_confirmation, DESTRUCTIVE_ACTIONS
from core.learned_intents import learn, find_exact_match
from core.background_gemini import generate_followup, should_enhance
from core.memory import (
    has_context_reference, resolve_context, update_context, save_exchange,
    update_file_context, get_last_file,
)
from core.logger import log_interaction
from core.voice_response import speak, speak_instant
from core.speech_to_text import listen as stt_listen
from core.llm_brain import ask_gemini
from mood.mood_engine import get_current_mood
from core.reinforcement import track_action, boost_confidence, get_penalty, get_boost

# ── Format Keywords → Extensions ───────────────────────────────
FORMAT_MAP = {
    "text": ".txt", "txt": ".txt", "plain text": ".txt",
    "document": ".docx", "doc": ".docx", "docx": ".docx",
    "word": ".docx", "word document": ".docx",
    "pdf": ".pdf",
    "markdown": ".md", "md": ".md",
    "python": ".py", "python file": ".py", "script": ".py",
    "html": ".html", "webpage": ".html", "web page": ".html",
    "csv": ".csv", "spreadsheet": ".csv",
    "json": ".json",
    "rtf": ".rtf", "rich text": ".rtf",
    "pages": ".pages",
    "numbers": ".numbers",
    "keynote": ".key", "presentation": ".key",
    "xml": ".xml", "yaml": ".yaml",
    "swift": ".swift", "java": ".java",
    "javascript": ".js", "js": ".js",
    "css": ".css", "sql": ".sql", "log": ".log",
}


def _detect_format_from_context(text: str) -> str:
    """
    Tries to detect file format from the original command text.
    Returns extension string like '.docx' or None if no format detected.
    """
    text_lower = text.lower()
    # Check longest-first to match 'word document' before 'word'
    for keyword, ext in sorted(FORMAT_MAP.items(), key=lambda x: len(x[0]), reverse=True):
        if keyword in text_lower:
            return ext
    return None


def _resolve_format(spoken_format: str) -> str:
    """
    Resolves a spoken format response to a file extension.
    e.g. 'text' → '.txt', 'word document' → '.docx', 'python' → '.py'
    Falls back to .txt if not recognized.
    """
    spoken = spoken_format.lower().strip()
    # Check longest-first
    for keyword, ext in sorted(FORMAT_MAP.items(), key=lambda x: len(x[0]), reverse=True):
        if keyword in spoken:
            return ext
    return ".txt"



def _extract_params(action: str, text: str) -> dict:
    """
    Extracts parameters for the given action from the command text.
    Uses lightweight regex/keyword extractors — no LLM.
    """
    params = {}

    if action in ("open_app", "close_app", "switch_to_app", "minimise_app"):
        app = extract_app_name(text)
        if app:
            params["name"] = app
            params["target"] = app

    elif action in ("volume_up", "volume_down", "brightness_up", "brightness_down"):
        params["amount"] = extract_amount(text)

    elif action == "search_google":
        query = extract_query(text)
        if query:
            params["query"] = query

    elif action in ("open_folder", "create_folder"):
        target = extract_folder_target(text)
        if target:
            params["target"] = target

    elif action == "search_file":
        query = extract_query(text)
        if query:
            params["query"] = query

    elif action == "search_emails":
        query = extract_query(text)
        if query:
            params["query"] = query

    elif action == "send_email":
        params.update(extract_email_params(text))

    elif action in ("read_file", "create_file", "delete_file", "rename_file", "copy_file"):
        params.update(extract_filename(text))

    elif action == "edit_file":
        params.update(extract_file_edit_params(text))

    elif action == "create_and_edit_file":
        params.update(extract_compound_file_params(text))

    # Auto-fill missing filename from file context cache
    if action in ("edit_file", "read_file", "delete_file", "rename_file", "copy_file"):
        if not params.get("filename"):
            last = get_last_file()
            if last:
                params["filename"] = last["filename"]
                if last.get("path"):
                    params.setdefault("location", None)
                print(f"📎 Auto-filled filename from context: {last['filename']}")

    return params


def _execute_action(action: str, params: dict, actions: dict) -> str:
    """
    Executes an action with extracted params.
    Returns result string for logging and context.
    """
    try:
        # ── Open app ────────────────────────────────────────
        if action == "open_app":
            target = params.get("target", params.get("name", ""))
            func_name = f"open_{target.lower().replace(' ', '_')}"
            if func_name in actions:
                actions[func_name]()
                return f"Opened {target}"
            else:
                from control import open_any_app
                open_any_app(target)
                return f"Opened {target}"

        # ── Close app ───────────────────────────────────────
        if action == "close_app":
            target = params.get("target", params.get("name", ""))
            if "close_app" in actions and target:
                actions["close_app"](target)
                return f"Closed {target}"

        # ── Switch app ──────────────────────────────────────
        if action == "switch_to_app":
            target = params.get("target", params.get("name", ""))
            if "switch_to_app" in actions and target:
                actions["switch_to_app"](target)
                return f"Switched to {target}"

        # ── Minimize app ────────────────────────────────────
        if action == "minimise_app":
            target = params.get("target", params.get("name", ""))
            if "minimise_app" in actions and target:
                actions["minimise_app"](target)
                return f"Minimized {target}"

        # ── Volume ──────────────────────────────────────────
        if action == "volume_up":
            amount = params.get("amount", 10)
            if "volume_up" in actions:
                actions["volume_up"](amount)
                return f"Volume up by {amount}"

        if action == "volume_down":
            amount = params.get("amount", 10)
            if "volume_down" in actions:
                actions["volume_down"](amount)
                return f"Volume down by {amount}"

        # ── Search Google ───────────────────────────────────
        if action == "search_google":
            query = params.get("query", "")
            if query and "search_google" in actions:
                actions["search_google"](query)
                return f"Searched for {query}"

        # ── Folders ─────────────────────────────────────────
        if action == "open_folder":
            target = params.get("target", "")
            if target and "open_folder" in actions:
                actions["open_folder"](target)
                return f"Opened {target}"

        if action == "create_folder":
            target = params.get("target", "")
            if target and "create_folder" in actions:
                actions["create_folder"](target)
                return f"Created folder {target}"

        if action == "search_file":
            query = params.get("query", "")
            if query and "search_file" in actions:
                actions["search_file"](query)
                return f"Searched for file {query}"

        # ── Email ───────────────────────────────────────────
        if action == "search_emails":
            query = params.get("query", "")
            if query and "search_emails" in actions:
                actions["search_emails"](query)
                return f"Searched emails for {query}"

        if action == "send_email":
            if "send_email" in actions:
                actions["send_email"](
                    params.get("to", ""),
                    params.get("subject", ""),
                    params.get("body", "")
                )
                return "Email composed"

        # ── File operations ─────────────────────────────────
        if action == "read_file":
            filename = params.get("filename", "")
            location = params.get("location")
            if filename and "read_file" in actions:
                actions["read_file"](filename, location)
                update_file_context(filename, action="read_file")
                return f"Read {filename}"
            return f"Couldn't read — no filename extracted"

        if action == "create_file":
            filename = params.get("filename", "")
            location = params.get("location") or "desktop"

            # ── Smart format detection ────────────────────────
            # If filename has no extension, ask the user or infer
            if filename and "." not in filename:
                detected_fmt = _detect_format_from_context(text)
                if detected_fmt:
                    filename = filename + detected_fmt
                    print(f"📄 Auto-detected format: {detected_fmt}")
                else:
                    # Ask the user what format they want

                    speak(f"What format should {filename} be? Like text, document, python, or something else?")
                    fmt_response = stt_listen()
                    if fmt_response:
                        ext = _resolve_format(fmt_response)
                        filename = filename + ext
                        print(f"📄 User chose format: {ext}")
                    else:
                        filename = filename + ".txt"
                        print(f"📄 No response — defaulting to .txt")
                params["filename"] = filename

            if filename and "create_file" in actions:
                actions["create_file"](filename, location)
                update_file_context(filename, action="create_file")
                return f"Created {filename}"
            return f"Couldn't create — no filename extracted"

        # ── edit_file — asks for content when missing, then listens ──
        if action == "edit_file":
            filename = params.get("filename", "")
            content  = params.get("content", "")
            location = params.get("location")
            if filename and content and "edit_file" in actions:
                actions["edit_file"](filename, content, location)
                update_file_context(filename, action="edit_file")
                return f"Appended text to {filename}"
            elif filename and not content:
                # Ask for content and actually LISTEN for the answer

                speak("What do you want me to write in that file?")
                content_response = stt_listen()
                if content_response and content_response.strip():
                    actions["edit_file"](filename, content_response.strip(), location)
                    update_file_context(filename, action="edit_file")
                    return f"Appended text to {filename}"
                else:
                    speak("I didn't catch that. Try telling me again.")
                    return "No content provided after asking"
            return "Couldn't edit — missing filename or content"

        if action == "delete_file":
            filename = params.get("filename", "")
            location = params.get("location")
            if filename and "delete_file" in actions:
                actions["delete_file"](filename, location)
                update_file_context(filename, action="delete_file")
                return f"Deleted {filename}"
            return f"Couldn't delete — no filename extracted"

        if action == "rename_file":
            filename = params.get("filename", "")
            new_name = params.get("new_name", "")
            location = params.get("location")
            if filename and new_name and "rename_file" in actions:
                actions["rename_file"](filename, new_name, location)
                update_file_context(new_name, action="rename_file")
                return f"Renamed {filename} to {new_name}"
            return f"Couldn't rename — need both old and new names"

        if action == "copy_file":
            filename = params.get("filename", "")
            location = params.get("location") or "desktop"
            if filename and "copy_file" in actions:
                actions["copy_file"](filename, location)
                return f"Copied {filename}"
            return f"Couldn't copy — no filename extracted"

        if action == "get_recent_files":
            if "get_recent_files" in actions:
                actions["get_recent_files"]()
                return "Showed recent files"

        # ── Compound create + edit (from Gemini fallback) ────
        if action == "create_and_edit_file":
            filename = params.get("filename", "")
            content  = params.get("content", "")
            location = params.get("location") or "desktop"
            if filename:
                if "create_file" in actions:
                    actions["create_file"](filename, location)
                    update_file_context(filename, action="create_file")
                if content and "edit_file" in actions:
                    actions["edit_file"](filename, content, location)
                    update_file_context(filename, action="edit_file")
                    return f"Created {filename} and wrote content"
                elif not content:

                    speak("What do you want me to write in it?")
                    content_response = stt_listen()
                    if content_response and content_response.strip():
                        actions["edit_file"](filename, content_response.strip(), location)
                        update_file_context(filename, action="edit_file")
                        return f"Created {filename} and wrote content"
                    return f"Created {filename} (no content specified)"
            return "Couldn't create — no filename"

        # ── Generic action ──────────────────────────────────
        # ── Conversational intents → Gemini for answer ─────────
        if action in ("answer_question", "general_chat"):
            try:
                result = ask_gemini(text)
                response_text = result.get("response", "I'm not sure about that.")
                speak(response_text)
                return f"Chat: {response_text[:50]}"
            except Exception as e:
                speak("I'd answer that but my brain is a bit slow right now.")
                return f"Chat error: {e}"

        if action in actions:
            result = actions[action]()
            return f"Executed {action}" + (f": {result}" if result else "")

        return f"Unknown action: {action}"

    except Exception as e:
        return f"Error: {str(e)}"


def route(command: str, actions: dict) -> bool:
    """
    Speed-first intent routing pipeline.

    1. Normalize text
    2. Resolve context ("it", "that")
    3. Try fast intent engine (embedding similarity)
    4. Safety check (confidence + destructive action guard)
    5. Execute + instant response
    6. Optionally enhance with background Gemini

    Returns True if completed, False if user interrupted.
    """
    start_time = time.time()

    if not command or not command.strip():
        print("⚠️  Empty command received")
        return True

    command = command.strip().lower()
    print(f"\n🔍 Routing: '{command}'")

    # ── Step 1: Normalize ────────────────────────────────────
    normalized = normalize(command)
    cleaned    = normalized.cleaned
    print(f"📋 Normalized: '{cleaned}'")

    # ── Step 2: Compound command? (create + write in one) ────
    if is_compound_file_command(cleaned):
        print(f"⚙️  Compound file command detected")
        return _handle_compound_file(command, cleaned, actions, start_time)

    # ── Step 3: Check learned intents (exact match) ──────────
    learned = find_exact_match(cleaned)
    if learned:
        intent = IntentResult(
            action=learned["action"],
            confidence=0.95,
            source="learned",
            matched_example=cleaned,
        )
        params = learned.get("params", {})
        fresh_params = _extract_params(intent.action, cleaned)
        if fresh_params:
            params.update(fresh_params)
    else:
        # ── Step 3: Fast intent engine ───────────────────────
        intent = classify(cleaned)
        params = _extract_params(intent.action, cleaned)
        print(f"⚡ Fast intent: {intent.action} (conf={intent.confidence:.2f}, source={intent.source}, match='{intent.matched_example}')")

    # ── Step 4: Context resolution ───────────────────────────
    # FIX 1: After resolving "that file" → "superman.txt", DON'T re-classify.
    # Re-classifying on the resolved text (which now contains the filename)
    # causes the embedding to flip from edit_file → create_file.
    # Keep the original intent; just refresh params with the resolved text.
    has_ctx = has_context_reference(cleaned)
    if has_ctx:
        resolved, was_resolved = resolve_context(cleaned, intent.confidence)
        if was_resolved:
            cleaned = resolved
            fresh_params = _extract_params(intent.action, cleaned)
            if fresh_params:
                params.update(fresh_params)
            print(f"🔗 Context resolved → '{cleaned}' keeping intent={intent.action} (conf={intent.confidence:.2f})")

    # ── Step 5: Safety check ─────────────────────────────────
    safety = check_safety(intent.action, intent.confidence, has_ctx, word_count=len(cleaned.split()))
    print(f"🛡️  Safety: {safety.decision} — {safety.reason}")

    mood = get_current_mood().get("name", "casual")
    latency_ms = (time.time() - start_time) * 1000

    # ── DECISION: EXECUTE ────────────────────────────────────
    if safety.decision == SafetyDecision.EXECUTE:
        response_text = get_instant_response(intent.action, mood)
        completed = speak_instant(response_text)

        if not completed:
            log_interaction(
                you_said=command, action_taken=intent.action,
                was_understood=True, intent_source=intent.source,
                confidence=intent.confidence, latency_ms=latency_ms,
                normalized_text=cleaned,
            )
            return False

        result = _execute_action(intent.action, params, actions)
        print(f"✅ Result: {result}")

        update_context(
            action=intent.action,
            target=params.get("target", params.get("name", params.get("query", ""))),
            result=result,
            command=cleaned,
        )

        latency_ms = (time.time() - start_time) * 1000
        log_interaction(
            you_said=command, action_taken=intent.action,
            was_understood=True, intent_source=intent.source,
            confidence=intent.confidence, latency_ms=latency_ms,
            normalized_text=cleaned, params=params,
        )

        save_exchange(command, response_text)

        # ── Reinforcement: track + boost successful action ───
        track_action(cleaned, intent.action, intent.confidence, params, intent.source)
        if not result.startswith("Error"):
            boost_confidence(cleaned, intent.action)

        if should_enhance(intent.action, result):
            generate_followup(
                action=intent.action,
                command=command,
                action_result=result,
                instant_response=response_text,
                speak_func=speak,
                use_elevenlabs=True,
            )

        return True

    # ── DECISION: CONFIRM (destructive action) ───────────────
    elif safety.decision == SafetyDecision.CONFIRM:
        prompt = get_confirmation_prompt(intent.action, mood)
        confirmed = ask_voice_confirmation(prompt)

        if confirmed:
            response_text = get_instant_response(intent.action, mood)
            speak_instant(response_text)
            result = _execute_action(intent.action, params, actions)
            print(f"✅ Confirmed & executed: {result}")

            update_context(
                action=intent.action,
                target=params.get("target", params.get("name", "")),
                result=result,
                command=cleaned,
            )

            latency_ms = (time.time() - start_time) * 1000
            log_interaction(
                you_said=command, action_taken=intent.action,
                was_understood=True, intent_source=intent.source,
                confidence=intent.confidence, latency_ms=latency_ms,
                normalized_text=cleaned, params=params,
            )
            save_exchange(command, response_text)
        else:
            latency_ms = (time.time() - start_time) * 1000
            log_interaction(
                you_said=command, action_taken=f"{intent.action}_cancelled",
                was_understood=True, intent_source=intent.source,
                confidence=intent.confidence, latency_ms=latency_ms,
                normalized_text=cleaned,
            )
        return True

    # ── DECISION: CONTEXT_ASK ────────────────────────────────
    elif safety.decision == SafetyDecision.CONTEXT_ASK:
        speak("What do you mean by that? Can you be more specific?")
        log_interaction(
            you_said=command, action_taken="context_ask",
            was_understood=False, intent_source=intent.source,
            confidence=intent.confidence, latency_ms=latency_ms,
            normalized_text=cleaned,
        )
        return True

    # ── DECISION: GEMINI FALLBACK ────────────────────────────
    elif safety.decision == SafetyDecision.GEMINI:
        print(f"🤖 Falling back to Gemini (confidence={intent.confidence:.2f})")
        return _gemini_fallback(command, cleaned, actions, start_time, mood)

    return True


def _handle_compound_file(
    raw_command: str,
    normalized_command: str,
    actions: dict,
    start_time: float,
) -> bool:
    """
    Handles compound create+write commands like:
    'create a file called notes.txt and write hello world in it'
    """
    from core.speech_to_text import listen as stt_listen

    params = extract_compound_file_params(normalized_command)
    filename = params.get("filename", "")
    location = params.get("location") or "desktop"
    content  = params.get("content")

    if not filename:
        speak("What do you want me to name the file?")
        name_response = stt_listen()
        if name_response and name_response.strip():
            # Use param extractor to clean up user's response like "name it hello"
            from core.param_extractors import extract_filename
            clean_name = extract_filename(name_response).get("filename")
            if clean_name:
                filename = clean_name
            else:
                filename = name_response.strip().split()[-1]
        else:
            speak("I didn't catch a name. Let's try again later.")
            return True

    # Handle format if no extension
    if "." not in filename:
        detected_fmt = _detect_format_from_context(normalized_command)
        if detected_fmt:
            filename = filename + detected_fmt
            print(f"📄 Auto-detected format: {detected_fmt}")
        else:
            speak(f"What format should {filename} be? Like text, document, python?")
            fmt_response = stt_listen()
            if fmt_response:
                ext = _resolve_format(fmt_response)
                filename = filename + ext
            else:
                filename = filename + ".txt"

    # Step 1: Create the file
    speak_instant("Creating and writing.")
    if "create_file" in actions:
        actions["create_file"](filename, location)
        update_file_context(filename, action="create_file")
        print(f"📄 Created: {filename}")

    # Step 2: Write content (or ask for it)
    if not content:
        speak("What do you want me to write in it?")
        content_response = stt_listen()
        if content_response and content_response.strip():
            # Check if user is rejecting / correcting
            response_lower = content_response.strip().lower()
            rejection_words = {"no", "nothing", "never mind", "nevermind", "cancel",
                               "stop", "forget it", "don't", "not", "skip", "nope"}
            if any(w in response_lower for w in rejection_words):
                speak("Alright, file created without content. Tell me if you need anything.")
                track_action(normalized_command, "create_file", 1.0,
                           {"filename": filename}, "compound")
                return True
            content = content_response.strip()
        else:
            speak("I didn't catch that. You can tell me later.")
            track_action(normalized_command, "create_file", 1.0,
                       {"filename": filename}, "compound")
            latency_ms = (time.time() - start_time) * 1000
            log_interaction(
                you_said=raw_command, action_taken="create_file",
                was_understood=True, intent_source="compound",
                confidence=1.0, latency_ms=latency_ms,
                normalized_text=normalized_command,
            )
            return True

    if "edit_file" in actions:
        actions["edit_file"](filename, content, location)
        update_file_context(filename, action="edit_file")
        print(f"✏️  Wrote to: {filename}")

    result = f"Created {filename} and wrote content"
    update_context(
        action="create_and_edit_file",
        target=filename,
        result=result,
        command=normalized_command,
    )

    # Track for correction system
    track_action(normalized_command, "create_and_edit_file", 1.0,
               {"filename": filename, "content": content}, "compound")
    boost_confidence(normalized_command, "create_and_edit_file")

    latency_ms = (time.time() - start_time) * 1000
    log_interaction(
        you_said=raw_command, action_taken="create_and_edit_file",
        was_understood=True, intent_source="compound",
        confidence=1.0, latency_ms=latency_ms,
        normalized_text=normalized_command,
    )
    save_exchange(raw_command, f"Created {filename} and wrote content")

    if should_enhance("create_file", result):
        generate_followup(
            action="create_file",
            command=raw_command,
            action_result=result,
            instant_response="Creating and writing.",
            speak_func=speak,
            use_elevenlabs=True,
        )

    return True


def _gemini_fallback(
    raw_command: str,
    normalized_command: str,
    actions: dict,
    start_time: float,
    mood: str,
) -> bool:
    """
    Gemini fallback path. Called when fast engine confidence is too low.
    Also learns from the result for future fast resolution.
    """
    result = ask_gemini(raw_command)
    response_text = result.get("response", "On it.")
    action        = result.get("action")
    target        = result.get("target")
    query         = result.get("query")

    print(f"🤖 Gemini understood: {result}")

    # ── Chat response (no action) ────────────────────────────
    if result["type"] == "chat":
        completed = speak(response_text)
        latency_ms = (time.time() - start_time) * 1000
        log_interaction(
            you_said=raw_command, action_taken="chat_response",
            was_understood=True, sent_to_gemini=True,
            gemini_response=response_text, intent_source="gemini",
            latency_ms=latency_ms, normalized_text=normalized_command,
        )
        return completed

    # ── Action response ──────────────────────────────────────
    if result["type"] == "action" and action:

        if action == "answer_question":
            completed = speak(response_text)
            latency_ms = (time.time() - start_time) * 1000
            log_interaction(
                you_said=raw_command, action_taken="answer_question",
                was_understood=True, sent_to_gemini=True,
                gemini_response=response_text, intent_source="gemini",
                latency_ms=latency_ms, normalized_text=normalized_command,
            )
            return completed

        if action in DESTRUCTIVE_ACTIONS:
            prompt = get_confirmation_prompt(action, mood)
            confirmed = ask_voice_confirmation(prompt)
            if not confirmed:
                latency_ms = (time.time() - start_time) * 1000
                log_interaction(
                    you_said=raw_command, action_taken=f"{action}_cancelled",
                    was_understood=True, sent_to_gemini=True,
                    intent_source="gemini", latency_ms=latency_ms,
                    normalized_text=normalized_command,
                )
                return True

        speak_instant(response_text)

        params = {}
        if target:
            params["target"] = target
            params["name"]   = target
        if query:
            params["query"] = query
        for key in ("filename", "location", "new_name", "to", "subject", "body", "amount", "content"):
            if key in result:
                params[key] = result[key]

        exec_result = _execute_action(action, params, actions)
        print(f"✅ Gemini action result: {exec_result}")

        update_context(
            action=action,
            target=target or query or "",
            result=exec_result,
            command=normalized_command,
        )

        if action not in ("answer_question", "chat_response"):
            learn(
                normalized_input=normalized_command,
                action=action,
                params=params,
                confidence=1.0,
                source="gemini",
            )

        latency_ms = (time.time() - start_time) * 1000
        log_interaction(
            you_said=raw_command, action_taken=action,
            was_understood=True, sent_to_gemini=True,
            gemini_response=response_text, intent_source="gemini",
            latency_ms=latency_ms, normalized_text=normalized_command,
            params=params,
        )
        save_exchange(raw_command, response_text)
        return True

    speak("I understood but can't do that yet.")
    latency_ms = (time.time() - start_time) * 1000
    log_interaction(
        you_said=raw_command, action_taken="unknown",
        was_understood=False, sent_to_gemini=True,
        gemini_response=str(result), intent_source="gemini",
        latency_ms=latency_ms, normalized_text=normalized_command,
    )
    return True