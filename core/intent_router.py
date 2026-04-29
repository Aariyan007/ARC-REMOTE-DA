"""
Intent Router — the core speed-first pipeline.

Pipeline:
    listen() → normalize() → resolve_context() → fast_intent()
    → safety_check() → ack → execute → verify → grounded result
                                    ↓ (background, gated)
                              gemini_enhance()

If fast engine fails → Gemini fallback → learn from result.
"""

import time
import os
import sys
import threading
import uuid
from core.normalizer import normalize
from core.fast_intent import classify, IntentResult
from core.param_extractors import (
    extract_app_name, extract_amount, extract_query,
    extract_filename, extract_email_params, extract_folder_target,
    extract_file_edit_params, is_compound_file_command,
    extract_compound_file_params,
    is_find_and_send_command, extract_find_and_send_params,
    extract_url,
)
from core.response_policy import (
    get_ack, get_clarification, get_confirmation, get_result as get_result_text,
    get_failure as get_failure_text, get_missing_params,
)
from core.action_result import ActionResult
from core.safety import check_safety, SafetyDecision, ask_voice_confirmation, DESTRUCTIVE_ACTIONS
from core.learned_intents import learn, find_exact_match
from core.background_gemini import generate_followup, should_enhance
from core.memory import (
    has_context_reference, resolve_context, update_context, save_exchange,
    update_file_context, get_last_file, get_last_context,
)
from core.logger import log_interaction
from core.voice_response import speak, speak_instant, speak_ack, speak_result, speak_chat
from core.speech_to_text import listen as stt_listen
from core.llm_brain import ask_gemini

from core.reinforcement import track_action, boost_confidence, get_penalty, get_boost
from core.thinking_ui import update_thinking
from core.interrupt_manager import is_interrupt, get_interrupt_manager
from core.confidence import evaluate_confidence, ConfidenceTier
from core.brain import get_brain, BrainDecision
from core.working_memory import get_working_memory
from core.continuous_memory import get_continuous_memory
from core.command_interpreter import build_machine_context, interpret_command
from core.action_verifier import (
    ExpectedDelta, verify_perception_delta,
    BeforeState, capture_before_state, verify_action, SAFE_TO_RETRY,
)
from core.perception_engine import get_perception_engine
# Phase 1: Task continuity
from core.task_state import (
    get_pending, set_pending, clear_pending, has_pending,
    is_pending_answer, resume_with_answer, PendingTask,
    detect_follow_up_intent,
)
from core.ambiguity_resolver import build_single_slot_question
from core.instant_responses import get_instant_response, get_confirmation_prompt

def _is_headless_source(source: str) -> bool:
    """
    Treat every non-voice caller as a remote/headless controller.
    """
    return (source or "").lower() != "voice"


REMOTE_DETERMINISTIC_ACTIONS = {
    "open_app", "close_app", "switch_to_app", "minimise_app",
    "open_folder", "create_folder", "search_file", "search_google", "open_url",
    "send_email", "search_emails", "tell_time", "tell_date", "read_news",
    "get_battery", "tell_weather", "volume_up", "volume_down",
    "brightness_up", "brightness_down", "mute", "unmute",
    "sleep_mac", "lock_screen", "take_screenshot",
}

def ask_user_input(prompt: str, source: str, request_id: str, event_type: str = "clarify") -> str:
    if _is_headless_source(source):
        try:
            from remote.job_store import ask_user
            return ask_user(request_id, prompt, event_type)
        except Exception as e:
            print(f"Warning: headless ask_user failed: {e}")
            return ""
    else:
        speak_result(prompt)
        res = stt_listen()
        return res if res else ""


def _apply_slot_reply(params: dict, action: str, slot: str, reply: str) -> dict:
    """Fill the clarified slot without re-routing the reply as a brand-new command."""
    updated = dict(params or {})
    value = (reply or "").strip()
    if not value:
        return updated

    updated[slot] = value

    if slot == "target":
        updated.setdefault("name", value)
    elif slot == "name":
        updated.setdefault("target", value)

    if action == "search_file" and slot in {"target", "filename", "query"}:
        updated["query"] = value
    elif action == "send_email" and slot in {"target", "recipient", "to"}:
        updated["to"] = value

    return updated


def _store_command_response(
    request_id: str,
    source: str,
    action: str,
    params: dict,
    result: ActionResult,
    spoken_text: str,
    start_time: float,
    ack_text: str = "",
) -> None:
    """Store one structured response for API/remote controllers."""
    try:
        from core.command_models import CommandResponse, ExecutionStatus
        from core.runtime import store_result

        data = dict(result.data or {})
        data.setdefault("params", dict(params or {}))
        if ack_text:
            data.setdefault("ack", ack_text)

        store_result(CommandResponse(
            request_id=request_id,
            status=ExecutionStatus.COMPLETED if result.success else ExecutionStatus.FAILED,
            interpreted_action=action,
            final_result=spoken_text,
            steps=[result.to_step_result()],
            data=data,
            errors=[spoken_text] if not result.success else [],
            elapsed_ms=(time.time() - start_time) * 1000,
            source=source,
        ))
    except Exception:
        pass


def _remote_confidence_floor(action: str, params: dict, missing_params: list) -> float:
    """Minimum confidence for deterministic remote actions that have usable params."""
    if action not in REMOTE_DETERMINISTIC_ACTIONS or missing_params:
        return 0.0
    if action in DESTRUCTIVE_ACTIONS:
        return 0.65
    if action in {"search_file", "send_email", "search_google", "open_url", "open_app"}:
        return 0.62
    return 0.60

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


def _is_missing_param_value(value) -> bool:
    """Treat empty or placeholder values as missing."""
    if value is None:
        return True
    if not isinstance(value, str):
        return False
    return value.strip().lower() in {"", "unknown", "unknown file", "null", "none", "n/a"}


def _is_filename_placeholder(value) -> bool:
    """File references like 'it' should fall back to local context."""
    if _is_missing_param_value(value):
        return True
    if not isinstance(value, str):
        return False
    return value.strip().lower() in {"it", "that", "this", "that file", "this file", "the file"}


def _merge_gemini_params(result: dict, fallback_params: dict | None = None) -> dict:
    """
    Merge Gemini params with locally resolved params.
    Local context wins when Gemini returns placeholders like 'unknown' or 'it'.
    """
    params = dict(fallback_params or {})

    target = result.get("target")
    if not _is_missing_param_value(target):
        params["target"] = target
        params["name"] = target

    query = result.get("query")
    if not _is_missing_param_value(query):
        params["query"] = query

    for key in ("filename", "location", "new_name", "to", "subject", "body", "amount", "content"):
        value = result.get(key)

        if key == "filename":
            if not _is_filename_placeholder(value):
                params["filename"] = value
            elif _is_filename_placeholder(params.get("filename")):
                last_file = get_last_file()
                if last_file.get("filename"):
                    params["filename"] = last_file["filename"]
            continue

        if not _is_missing_param_value(value):
            params[key] = value

    if _is_filename_placeholder(params.get("filename")):
        last_file = get_last_file()
        if last_file.get("filename"):
            params["filename"] = last_file["filename"]

    return params


def _capture_perception_state():
    """Returns a fresh perception snapshot when available."""
    try:
        engine = get_perception_engine()
        try:
            engine._update_state()
        except Exception:
            pass
        return engine.get_state()
    except Exception:
        return None


def _capture_before_state(action: str, params: dict) -> BeforeState:
    """Phase 2: Rich before-state for per-action verification."""
    try:
        return capture_before_state(action, params)
    except Exception:
        return BeforeState()


def _build_interpreter_context():
    """Collect current machine state for the structured interpreter."""
    last_file = get_last_file().get("filename")
    recent_actions: list[str] = []
    browser_url: str | None = None
    browser_title: str | None = None

    try:
        wm = get_working_memory()
        recent_actions = [entry.action for entry in wm.get_recent_actions(5)]
        # Phase 1 fix [P2]: Pull browser grounding from WorkingMemory
        grounding = wm.get_grounding_context()
        browser_url = grounding.get("last_browser_url")
        browser_title = grounding.get("last_browser_title")
        # If WorkingMemory has a more recent last_file, prefer it
        wm_file = grounding.get("last_file")
        if wm_file and not last_file:
            last_file = wm_file
    except Exception:
        recent_actions = []

    try:
        last_ctx = get_last_context()
        last_action = last_ctx.get("action")
        if last_action and last_action not in recent_actions:
            recent_actions.append(last_action)
    except Exception:
        pass

    return build_machine_context(
        _capture_perception_state(),
        last_file=last_file,
        recent_actions=recent_actions,
        browser_url=browser_url,
        browser_title=browser_title,
    )


def _pick_interpreter_target(params: dict) -> str | None:
    """Best-effort target passed into the structured fast path."""
    for key in ("target", "name", "filename", "url", "query", "title"):
        value = params.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _verify_action_result(
    action: str,
    params: dict,
    result: ActionResult,
    before_state: BeforeState,
    actions: dict | None = None,
    text: str = "",
) -> ActionResult:
    """
    Phase 2: Per-action deterministic verification.

    Flow:
      1. Run action-specific verifier
      2. If verified → mark result.verified = True
      3. If failed + action is safe → retry once → re-verify
      4. If still failed → grounded failure (never fake success)
    """
    if not result.success:
        return result

    verification = verify_action(action, params, result, before_state)
    result.data.setdefault("verification", verification.details)
    result.verified = verification.ok

    if verification.ok:
        print(f"  ✔ Verified: {verification.message}")
        return result

    # Verification failed — try retry for safe actions
    print(f"  ✘ Verification failed: {verification.message}")

    if action in SAFE_TO_RETRY and actions is not None:
        print(f"  🔄 Retrying {action} (safe to retry)...")
        try:
            retry_before = _capture_before_state(action, params)
            retry_result = _execute_action(action, params, actions, text=text)
            if retry_result.success:
                retry_verification = verify_action(action, params, retry_result, retry_before)
                retry_result.data.setdefault("verification", retry_verification.details)
                retry_result.verified = retry_verification.ok
                retry_result.data["retried"] = True

                if retry_verification.ok:
                    print(f"  ✔ Retry succeeded: {retry_verification.message}")
                    return retry_result
                else:
                    print(f"  ✘ Retry also failed: {retry_verification.message}")
        except Exception as e:
            print(f"  ⚠ Retry error: {e}")

    # Final failure — grounded, never fake
    result.success = False
    result.verified = False
    result.error = verification.message
    # Don't override user_message — let response_policy handle it via get_failure()
    return result



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

    elif action == "open_url":
        url = extract_url(text)
        if url:
            params["url"] = url

    elif action in ("open_folder", "create_folder"):
        target = extract_folder_target(text)
        if target:
            params["target"] = target

    elif action == "search_file":
        file_params = extract_filename(text)
        query = file_params.get("filename") or extract_query(text)
        if not query:
            # Last resort: strip common filler words and grab the last meaningful word
            import re as _re
            _noise = {"a", "an", "the", "my", "file", "find", "search", "for", "in",
                       "on", "this", "that", "laptop", "computer", "mac", "desktop",
                       "nono", "please", "can", "you", "i", "want", "to", "look",
                       "serach", "seach", "it", "me", "some"}
            words = [w for w in _re.findall(r'\w+', text.lower()) if w not in _noise and len(w) > 1]
            if words:
                query = words[-1]  # Use the last significant word
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


# ── Music Agent Access ───────────────────────────────────────
def _get_music_agent():
    """Access the MusicAgent from the main module's agent registry."""
    try:
        import main as main_module
        if hasattr(main_module, '_manager_agent') and main_module._manager_agent:
            return main_module._manager_agent.get_agent("music")
    except Exception:
        pass
    # Fallback: create a standalone instance
    try:
        from core.agents.music_agent import MusicAgent
        return MusicAgent()
    except Exception:
        return None


# ── Knowledge Agent Access ───────────────────────────────────
def _get_knowledge_agent():
    """Access the KnowledgeAgent from the main module's agent registry."""
    try:
        import main as main_module
        if hasattr(main_module, '_manager_agent') and main_module._manager_agent:
            return main_module._manager_agent.get_agent("knowledge")
    except Exception:
        pass
    try:
        from core.agents.knowledge_agent import KnowledgeAgent
        return KnowledgeAgent()
    except Exception:
        return None

def _auto_play_focus_music():
    """Background task: auto-plays focus music when opening productive apps."""
    import time
    time.sleep(3)  # Wait for the app to fully open
    try:
        agent = _get_music_agent()
        if agent and hasattr(agent, 'play_focus_music_silent'):
            agent.play_focus_music_silent()
    except Exception as e:
        print(f"⚠️  Auto-play failed: {e}")


def _execute_action(action: str, params: dict, actions: dict, text: str = "", _source: str = "voice", _request_id: str = "") -> ActionResult:
    """
    Executes an action with extracted params.
    Returns ActionResult — structured, never a loose string.
    """
    try:
        # ── Open app ────────────────────────────────────────
        if action == "open_app":
            target = params.get("target", params.get("name", ""))
            func_name = f"open_{target.lower().replace(' ', '_')}"
            if func_name in actions:
                actions[func_name]()
            else:
                from control import open_any_app
                open_any_app(target)

            # ── Auto-play focus music for productive apps ────
            PRODUCTIVE_APPS = {"vscode", "terminal", "xcode", "sublime", "pycharm", "intellij"}
            if target and target.lower() in PRODUCTIVE_APPS:
                threading.Thread(target=_auto_play_focus_music, daemon=True).start()

            return ActionResult.ok(action, f"Opened {target}", data={"target": target})

        # ── Close app ───────────────────────────────────────
        if action == "close_app":
            target = params.get("target", params.get("name", ""))
            if "close_app" in actions and target:
                actions["close_app"](target)
                return ActionResult.ok(action, f"Closed {target}", data={"target": target})

        # ── Switch app ──────────────────────────────────────
        if action == "switch_to_app":
            target = params.get("target", params.get("name", ""))
            if "switch_to_app" in actions and target:
                actions["switch_to_app"](target)
                return ActionResult.ok(action, f"Switched to {target}", data={"target": target})

        # ── Minimize app ────────────────────────────────────
        if action == "minimise_app":
            target = params.get("target", params.get("name", ""))
            if "minimise_app" in actions and target:
                actions["minimise_app"](target)
                return ActionResult.ok(action, f"Minimized {target}", data={"target": target})

        # ── Volume ──────────────────────────────────────────
        if action == "volume_up":
            amount = params.get("amount", 10)
            if "volume_up" in actions:
                actions["volume_up"](amount)
                return ActionResult.ok(action, f"Volume up by {amount}", data={"amount": amount})

        if action == "volume_down":
            amount = params.get("amount", 10)
            if "volume_down" in actions:
                actions["volume_down"](amount)
                return ActionResult.ok(action, f"Volume down by {amount}", data={"amount": amount})

        if action == "brightness_up":
            amount = params.get("amount") or 10
            if "brightness_up" in actions:
                steps = max(1, min(16, round(float(amount) / 10)))
                for _ in range(steps):
                    actions["brightness_up"]()
                message = f"Brightness up by {amount}"
                return ActionResult.ok(action, message, data={"amount": amount}, user_message=f"{message}.")

        if action == "brightness_down":
            amount = params.get("amount") or 10
            if "brightness_down" in actions:
                steps = max(1, min(16, round(float(amount) / 10)))
                for _ in range(steps):
                    actions["brightness_down"]()
                message = f"Brightness down by {amount}"
                return ActionResult.ok(action, message, data={"amount": amount}, user_message=f"{message}.")

        # ── Search Google ───────────────────────────────────
        if action == "search_google":
            query = params.get("query", "")
            if query and "search_google" in actions:
                actions["search_google"](query)
                return ActionResult.ok(action, f"Searched for {query}", data={"query": query})

        if action == "open_url":
            url = params.get("url") or extract_url(text)
            if not url:
                return ActionResult.fail(action, "No URL provided", user_message="What URL or website should I open?")
            try:
                from control.playwright_browser import navigate
                final = navigate(url)
                return ActionResult.ok(action, f"Opened {final}", data={"url": final})
            except Exception as e:
                return ActionResult.fail(action, str(e), user_message="I couldn't open that in the browser.")

        # ── Folders ─────────────────────────────────────────
        if action == "open_folder":
            target = params.get("target", "")
            if target and "open_folder" in actions:
                actions["open_folder"](target)
                return ActionResult.ok(action, f"Opened {target}", data={"target": target})

        if action == "create_folder":
            target = params.get("target", "")
            if target and "create_folder" in actions:
                actions["create_folder"](target)
                return ActionResult.ok(action, f"Created folder {target}", data={"target": target})

        if action == "search_file":
            query = params.get("query", "")
            if not query:
                # No filename extracted — ask the user
                return ActionResult.fail(
                    action, "No filename specified",
                    user_message="What file are you looking for? Tell me the name."
                )
            if query and "search_files_advanced" in actions:
                best_match = actions["search_files_advanced"](query)
                if best_match:
                    return ActionResult.ok(action, f"Found file: {os.path.basename(best_match)}", data={"filename": best_match, "path": best_match})
                return ActionResult.fail(action, f"Could not find a file matching '{query}'", data={"query": query},
                                         user_message=f"I couldn't find any file matching '{query}' on your Desktop, Documents, or Downloads.")
            # fallback to old search
            elif query and "search_file" in actions:
                actions["search_file"](query)
                return ActionResult.ok(action, f"Searched for file {query}", data={"query": query})

        # ── Email ───────────────────────────────────────────
        if action == "search_emails":
            query = params.get("query", "")
            if query and "search_emails" in actions:
                actions["search_emails"](query)
                return ActionResult.ok(action, f"Searched emails for {query}", data={"query": query})

        if action == "send_email":
            if "send_email" in actions:
                result_text = actions["send_email"](
                    params.get("to", ""),
                    params.get("subject", ""),
                    params.get("body", ""),
                    _source=_source,
                    _request_id=_request_id
                )
                result_text = (result_text or "Email composed").strip()
                if result_text.lower().startswith("cancelled"):
                    return ActionResult.fail(action, result_text, user_message=result_text)
                if result_text.lower().startswith("failed"):
                    return ActionResult.fail(action, result_text, user_message=result_text)
                return ActionResult.ok(action, result_text, user_message=result_text)

        if action == "tell_time":
            if "tell_time" in actions:
                result = actions["tell_time"]()
                message = (result or "I checked the time.").strip()
                return ActionResult.ok(action, message, data={"time": message}, user_message=message)

        if action == "tell_date":
            if "tell_date" in actions:
                result = actions["tell_date"]()
                message = (result or "I checked the date.").strip()
                return ActionResult.ok(action, message, data={"date": message}, user_message=message)

        if action == "read_news":
            if "read_news" in actions:
                result = actions["read_news"]()
                message = (result or "I checked the news.").strip()
                return ActionResult.ok(action, message, data={"news": message}, user_message=message)

        # ── File operations ─────────────────────────────────
        if action == "read_file":
            filename = params.get("filename", "")
            location = params.get("location")
            if filename and "read_file" in actions:
                actions["read_file"](filename, location)
                update_file_context(filename, action="read_file")
                return ActionResult.ok(action, f"Read {filename}", data={"filename": filename})
            return ActionResult.fail(action, "No filename extracted", data={"filename": ""})

        if action == "create_file":
            filename = params.get("filename", "")
            location = params.get("location") or "desktop"

            if not filename:
                name_resp = ask_user_input("What should I name the file?", _source, _request_id)
                if name_resp and name_resp.strip():
                    filename = name_resp.strip()
                    print(f"📄 User provided filename: {filename}")
                else:
                    return ActionResult.fail(action, "No filename provided")

            if filename and "." not in filename:
                detected_fmt = _detect_format_from_context(text)
                if detected_fmt:
                    filename = filename + detected_fmt
                    print(f"📄 Auto-detected format: {detected_fmt}")
                else:
                    fmt_response = ask_user_input(f"What format should {filename} be? Like text, document, python, or something else?", _source, _request_id)
                    if fmt_response:
                        ext = _resolve_format(fmt_response)
                        filename = filename + ext
                    else:
                        filename = filename + ".txt"
                params["filename"] = filename

            if filename and "create_file" in actions:
                actions["create_file"](filename, location)
                update_file_context(filename, action="create_file")
                return ActionResult.ok(action, f"Created {filename}", data={"filename": filename})
            return ActionResult.fail(action, "No filename extracted")

        if action == "edit_file":
            filename = params.get("filename", "")
            content  = params.get("content") or ""   # treat None as "" (meta-word cleared)
            location = params.get("location")
            if filename and content and "edit_file" in actions:
                actions["edit_file"](filename, content, location)
                update_file_context(filename, action="edit_file")
                return ActionResult.ok(action, f"Wrote to {filename}", data={"filename": filename})
            elif filename and not content:
                content_response = ask_user_input("What do you want me to write in that file?", _source, _request_id)
                if content_response and content_response.strip():
                    actions["edit_file"](filename, content_response.strip(), location)
                    update_file_context(filename, action="edit_file")
                    return ActionResult.ok(action, f"Wrote to {filename}", data={"filename": filename})
                else:
                    return ActionResult.fail(action, "No content provided")
            return ActionResult.fail(action, "Missing filename or content")

        if action == "delete_file":
            filename = params.get("filename", "")
            location = params.get("location")
            if filename and "delete_file" in actions:
                actions["delete_file"](filename, location)
                update_file_context(filename, action="delete_file")
                return ActionResult.ok(action, f"Deleted {filename}", data={"filename": filename})
            return ActionResult.fail(action, "No filename extracted", data={"filename": ""})

        if action == "rename_file":
            filename = params.get("filename", "")
            new_name = params.get("new_name", "")
            location = params.get("location")
            if filename and new_name and "rename_file" in actions:
                rename_result = actions["rename_file"](filename, new_name, location)
                if rename_result is False:
                    return ActionResult.fail(action, f"Couldn't rename {filename} to {new_name}", data={"filename": filename})
                if isinstance(rename_result, dict):
                    if not rename_result.get("success"):
                        error_text = rename_result.get("error") or f"Couldn't rename {filename} to {new_name}"
                        return ActionResult.fail(action, error_text, data={"filename": filename})
                    final_name = rename_result.get("new_name", new_name)
                    update_file_context(final_name, path=rename_result.get("path"), action="rename_file")
                    return ActionResult.ok(action, f"Renamed {filename} to {final_name}",
                                           data={"filename": filename, "old_name": filename, "new_name": final_name})
                update_file_context(new_name, action="rename_file")
                return ActionResult.ok(action, f"Renamed {filename} to {new_name}",
                                       data={"filename": filename, "old_name": filename, "new_name": new_name})
            return ActionResult.fail(action, "Need both old and new names", data={"filename": filename})

        if action == "copy_file":
            filename = params.get("filename", "")
            location = params.get("location") or "desktop"
            if filename and "copy_file" in actions:
                actions["copy_file"](filename, location)
                return ActionResult.ok(action, f"Copied {filename}", data={"filename": filename})
            return ActionResult.fail(action, "No filename extracted")

        if action == "get_recent_files":
            if "get_recent_files" in actions:
                actions["get_recent_files"]()
                return ActionResult.ok(action, "Showed recent files")

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
                    return ActionResult.ok(action, f"Created {filename} and wrote content", data={"filename": filename})
                elif not content:
                    content_response = ask_user_input("What do you want me to write in it?", _source, _request_id)
                    if content_response and content_response.strip():
                        actions["edit_file"](filename, content_response.strip(), location)
                        update_file_context(filename, action="edit_file")
                        return ActionResult.ok(action, f"Created {filename} and wrote content", data={"filename": filename})
                    return ActionResult.ok("create_file", f"Created {filename} (no content)", data={"filename": filename})
            return ActionResult.fail(action, "No filename")

        # ── Computer Use (OpenClaw) ──────────────────────────
        if action == "computer_use":
            try:
                import main as main_module
                if hasattr(main_module, '_manager_agent') and main_module._manager_agent:
                    cu_agent = main_module._manager_agent.get_agent("computer_use")
                    if cu_agent:
                        result = cu_agent.execute("computer_use", {"instruction": text, "announce": True})
                        if result.success:
                            return ActionResult.ok(action, result.result or "Task completed via computer use")
                        return ActionResult.fail(action, result.error or "Computer use failed")
            except Exception as e:
                pass
            return ActionResult.fail(action, "Computer use agent unavailable")

        # ── Knowledge Base ───────────────────────────────────
        if action in ("save_note", "append_note", "search_vault", "read_note_vault"):
            agent = _get_knowledge_agent()
            if agent:
                if action == "save_note":
                    title = params.get("title", params.get("target", ""))
                    content = params.get("content", text)
                    if not title:
                        title_res = ask_user_input("What should I title this note?", _source, _request_id)
                        title = title_res.strip() if title_res else text[:20].strip()
                    res = agent.execute("save_note", {"title": title, "content": content})
                    return ActionResult.from_agent_result(res)

                elif action == "append_note":
                    res = agent.execute("append_note", params)
                    return ActionResult.from_agent_result(res)

                elif action == "search_vault":
                    query = params.get("query", extract_query(text) or "")
                    res = agent.execute("search_vault", {"query": query})
                    if res.success and res.data.get("matches"):
                        matches = res.data["matches"]
                        msg = f"Found {len(matches)} notes. First one is from {matches[0]['title']}."
                        return ActionResult.ok(action, res.result, data=res.data, user_message=msg)
                    else:
                        return ActionResult.ok(action, res.result if res.success else "",
                                               user_message="Couldn't find anything about that in my brain.")

                elif action == "read_note_vault":
                    res = agent.execute("read_note", {"title": params.get("title", "")})
                    return ActionResult.from_agent_result(res)
            return ActionResult.fail(action, "Knowledge agent not available")

        # ── Music: play_song ─────────────────────────────────
        if action == "play_song":
            agent = _get_music_agent()
            if agent:
                song_query = params.get("query", "")
                if not song_query:
                    song_query = extract_query(text) or ""
                result = agent.execute("play_song", {"query": song_query})
                return ActionResult.from_agent_result(result)
            return ActionResult.fail(action, "Music agent not available")

        # ── Music: play_mood_music ───────────────────────────
        if action == "play_mood_music":
            agent = _get_music_agent()
            if agent:
                result = agent.execute("play_mood_music", params)
                return ActionResult.from_agent_result(result)
            return ActionResult.fail(action, "Music agent not available")

        # ── Conversational intents → Gemini for answer ─────────
        if action in ("answer_question", "general_chat"):
            try:
                result = ask_gemini(text)
                response_text = result.get("response", "I'm not sure about that.")
                return ActionResult.ok(action, response_text, user_message=response_text)
            except Exception as e:
                fallback = "I'm ARC — I can help control this laptop. Ask me to open apps, find files, or send emails."
                return ActionResult.ok(action, fallback, user_message=fallback)

        # ── Generic action ──────────────────────────────────
        if action in actions:
            result = actions[action]()
            if isinstance(result, str) and result.strip():
                message = result.strip()
                direct_answer_actions = {"tell_time", "tell_date", "tell_weather", "get_battery"}
                return ActionResult.ok(
                    action,
                    message,
                    user_message=message if action in direct_answer_actions else "",
                )

            summary = f"Executed {action}" + (f": {result}" if result else "")
            return ActionResult.ok(action, summary)

        return ActionResult.fail(action, f"Unknown action: {action}")

    except Exception as e:
        return ActionResult.fail(action, str(e))


def _handle_terminal_preroute(command: str, actions: dict, start_time: float) -> bool:
    """
    Hard-coded pre-routing for Windows terminal commands.
    Bypasses normalization and intent engine entirely.
    Returns True if handled, False if not a terminal command.
    """
    cmd_lower = command.lower()

    # ── Command Prompt / CMD ─────────────────────────────────
    if "command prompt" in cmd_lower or ("cmd" in cmd_lower and "cmd" in cmd_lower.split()):
        if "open_cmd" in actions:
            speak_instant("Opening Command Prompt.")
            actions["open_cmd"]()
        else:
            # Direct fallback
            import subprocess
            speak_instant("Opening Command Prompt.")
            subprocess.Popen(["cmd"])
        update_thinking(command=command, action="open_cmd", confidence=1.0, stage="Executed")
        log_interaction(
            you_said=command, action_taken="open_cmd",
            was_understood=True, intent_source="preroute",
            confidence=1.0, latency_ms=(time.time() - start_time) * 1000,
            normalized_text=command,
        )
        return True

    # ── PowerShell ───────────────────────────────────────────
    if "powershell" in cmd_lower or "power shell" in cmd_lower:
        if "open_powershell" in actions:
            speak_instant("Opening PowerShell.")
            actions["open_powershell"]()
        else:
            import subprocess, shutil
            speak_instant("Opening PowerShell.")
            if shutil.which("pwsh"):
                subprocess.Popen(["pwsh"])
            else:
                subprocess.Popen(["powershell"])
        update_thinking(command=command, action="open_powershell", confidence=1.0, stage="Executed")
        log_interaction(
            you_said=command, action_taken="open_powershell",
            was_understood=True, intent_source="preroute",
            confidence=1.0, latency_ms=(time.time() - start_time) * 1000,
            normalized_text=command,
        )
        return True

    # ── Windows Terminal ─────────────────────────────────────
    if "windows terminal" in cmd_lower:
        if "open_windows_terminal" in actions:
            speak_instant("Opening Windows Terminal.")
            actions["open_windows_terminal"]()
        else:
            import subprocess
            speak_instant("Opening Windows Terminal.")
            try:
                subprocess.Popen(["wt"])
            except FileNotFoundError:
                subprocess.Popen(["cmd"])
        update_thinking(command=command, action="open_windows_terminal", confidence=1.0, stage="Executed")
        log_interaction(
            you_said=command, action_taken="open_windows_terminal",
            was_understood=True, intent_source="preroute",
            confidence=1.0, latency_ms=(time.time() - start_time) * 1000,
            normalized_text=command,
        )
        return True

    return False


def _handle_find_and_send_command(command: str, cleaned: str, actions: dict, start_time: float, _source: str, _request_id: str) -> bool:
    """
    Handles the compound 'find X and send to Y' workflow.
    """
    from core.param_extractors import extract_find_and_send_params
    from control.email_control import find_and_send_file

    params = extract_find_and_send_params(cleaned)
    filename = params.get("filename")
    to_email = params.get("to")
    
    update_thinking(command=command, intent="find_and_send", stage="Compound Execution")
    
    # We call find_and_send_file which has its own ask_user logic
    result_text = find_and_send_file(filename=filename, to=to_email, _source=_source, _request_id=_request_id)
    
    latency_ms = (time.time() - start_time) * 1000
    
    # Log it
    log_interaction(
        you_said=command, action_taken="find_and_send",
        was_understood=True, intent_source="compound_rule",
        confidence=1.0, latency_ms=latency_ms,
        normalized_text=cleaned, params=params,
        spoken_text=result_text,
    )
    save_exchange(command, result_text)
    
    # Store API result
    try:
        from core.command_models import CommandResponse, ExecutionStatus, StepResult
        from core.runtime import store_result

        step = StepResult(
            step_id=0, action="find_and_send", status="success",
            summary=result_text, data=params
        )
        
        resp = CommandResponse(
            request_id=_request_id,
            status=ExecutionStatus.COMPLETED if "Failed" not in result_text else ExecutionStatus.FAILED,
            interpreted_action="find_and_send",
            final_result=result_text,
            steps=[step],
            data={"params": params},
            errors=[result_text] if "Failed" in result_text else [],
            elapsed_ms=latency_ms,
            source=_source,
        )
        store_result(resp)
    except Exception as e:
        print(f"Error storing compound result: {e}")
        
    return True


def route(command: str, actions: dict, _source: str = "voice", _request_id: str = "") -> bool:
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

    # Ensure every routed command has a stable request id (used by API + remote job flows)
    if not _request_id:
        _request_id = str(uuid.uuid4())

    if not command or not command.strip():
        print("⚠️  Empty command received")
        return True

    command = command.strip().lower()
    print(f"\n🔍 Routing: '{command}'")

    # ── Update thinking UI ───────────────────────────────────
    update_thinking(command=command, stage="Routing")

    # ── Pre-route: Interrupt detection ───────────────────────
    if is_interrupt(command):
        mgr = get_interrupt_manager()
        mgr.cancel(reason=command)
        speak_instant("Alright, stopping.")
        update_thinking(command=command, action="interrupted", stage="Cancelled")
        log_interaction(
            you_said=command, action_taken="interrupt",
            was_understood=True, intent_source="builtin",
            confidence=1.0, latency_ms=(time.time() - start_time) * 1000,
            normalized_text=command,
        )
        mgr.reset()
        return True

    # ── Pre-route: Hard-coded terminal commands (Windows) ────
    # These bypass normalization and intent engine entirely.
    if sys.platform == "win32":
        handled = _handle_terminal_preroute(command, actions, start_time)
        if handled:
            return True

    # ── Phase 1: Pending Task Resumption ─────────────────────
    # If ARC previously asked a clarification question, check if
    # the user's input is an answer (short reply) rather than a
    # completely new command.
    if has_pending() and is_pending_answer(command):
        pending = get_pending()
        if pending:
            print(f"🔄 Resuming pending task: {pending.action} (filling: {pending.missing_param})")
            resumed = resume_with_answer(command)
            if resumed:
                action = resumed["action"]
                params = resumed["params"]
                update_thinking(command=command, intent=action, stage="Resumed")

                # ── P1 FIX: Safety check on resumed tasks ────
                # Destructive actions (delete_file, shutdown, etc.)
                # MUST go through confirmation even when resumed.
                safety = check_safety(
                    action,
                    resumed.get("confidence", 0.8),
                    has_context_reference=False,
                    word_count=len(command.split()),
                )
                if safety.decision == SafetyDecision.CONFIRM:
                    prompt = get_confirmation(action, params)
                    if _is_headless_source(_source):
                        confirmed_resp = ask_user_input(prompt, _source, _request_id, event_type="confirm")
                        confirmed = confirmed_resp.strip().lower() in ("yes", "y", "confirm", "ok", "sure", "do it")
                    else:
                        confirmed = ask_voice_confirmation(prompt)
                    if not confirmed:
                        if _is_headless_source(_source):
                            try:
                                from core.command_models import CommandResponse, ExecutionStatus
                                from core.runtime import store_result

                                store_result(CommandResponse(
                                    request_id=_request_id,
                                    status=ExecutionStatus.CANCELLED,
                                    interpreted_action=action,
                                    final_result="Cancelled by user.",
                                    elapsed_ms=(time.time() - start_time) * 1000,
                                    source=_source,
                                    data={"params": dict(params or {})},
                                ))
                            except Exception:
                                pass
                        latency_ms = (time.time() - start_time) * 1000
                        log_interaction(
                            you_said=command, action_taken=f"{action}_cancelled",
                            was_understood=True, intent_source=resumed.get("intent_source", "pending"),
                            confidence=resumed.get("confidence", 0.8), latency_ms=latency_ms,
                            normalized_text=command,
                            spoken_text="Alright, cancelled.",
                        )
                        return True
                elif safety.decision == SafetyDecision.GEMINI:
                    # Confidence too low even after resume — fall through
                    # to the normal pipeline to let Gemini handle it.
                    pass  # Will fall through to Step 1: Normalize below
                # SafetyDecision.EXECUTE or confirmed CONFIRM → proceed

                if safety.decision != SafetyDecision.GEMINI:
                    ack_text = get_ack(action)
                    if ack_text:
                        speak_ack(ack_text)

                    before_state = _capture_before_state(action, params)
                    result = _execute_action(action, params, actions, text=command)
                    result = _verify_action_result(action, params, result, before_state, actions=actions, text=command)
                    spoken_text = get_result_text(result)
                    speak_result(spoken_text)

                    update_context(
                        action=action,
                        target=params.get("target", params.get("name", params.get("query", ""))),
                        result=result.summary,
                        command=resumed.get("original_command", command),
                    )

                    # Phase 1 fix: Check for follow-up action and ground it
                    # with the result from step 1.
                    if pending.follow_up_action:
                        print(f"🔗 Chaining to follow-up: {pending.follow_up_action}")
                        from core.response_policy import get_missing_params as get_mp

                        # ── Inject step-1 result into follow-up params ──
                        # The user's answer (command) is the concrete target
                        # produced by step 1 (e.g., folder name, filename).
                        step1_target = command.strip()
                        follow_params = dict(pending.follow_up_params or {})

                        # Map step-1 action → which param to inject into step 2
                        _STEP1_TO_FOLLOW_PARAM = {
                            "create_folder": "location",
                            "open_folder":   "location",
                            "create_file":   "filename",
                            "rename_file":   "filename",
                        }
                        inject_key = _STEP1_TO_FOLLOW_PARAM.get(action)
                        if inject_key and step1_target:
                            follow_params[inject_key] = step1_target
                            # Also set target so grounding is consistent
                            if "target" not in follow_params:
                                follow_params["target"] = step1_target

                        follow_missing = get_mp(pending.follow_up_action, follow_params)
                        if follow_missing:
                            # Build a grounded question referencing step 1
                            grounding_ctx = {
                                "parent_target": step1_target,
                                "parent_action": action,
                            }
                            fq, fp = build_single_slot_question(
                                pending.follow_up_action, follow_params,
                                follow_missing, grounding_context=grounding_ctx,
                            )
                            if fq and fp:
                                set_pending(PendingTask(
                                    action=pending.follow_up_action,
                                    known_params=follow_params,
                                    missing_param=fp,
                                    question_asked=fq,
                                    original_command=resumed.get("original_command", command),
                                    normalized_command=command,
                                    intent_source=resumed.get("intent_source", "pending"),
                                    confidence=resumed.get("confidence", 0.8),
                                ))
                                speak_result(fq)

                    try:
                        wm = get_working_memory()
                        wm.record_action(
                            action=action, params=params,
                            reason=f"Resumed from pending: '{command}'",
                            outcome="success" if result.success else "failed",
                            confidence=resumed.get("confidence", 0.8),
                            command=command,
                            intent_source=resumed.get("intent_source", "pending"),
                        )
                        wm.update_grounding(
                            last_action=action,
                            last_file=params.get("filename"),
                        )
                    except Exception:
                        pass

                    latency_ms = (time.time() - start_time) * 1000
                    full_spoken = f"{ack_text} {spoken_text}".strip() if ack_text else spoken_text
                    log_interaction(
                        you_said=command, action_taken=action,
                        was_understood=True, intent_source=resumed.get("intent_source", "pending"),
                        confidence=resumed.get("confidence", 0.8), latency_ms=latency_ms,
                        normalized_text=command, params=params,
                        spoken_text=full_spoken,
                    )
                    save_exchange(command, full_spoken)
                    save_exchange(command, full_spoken)

                    return True

    # ── Step 1: Normalize ────────────────────────────────────
    normalized = normalize(command)
    cleaned    = normalized.cleaned
    print(f"📋 Normalized: '{cleaned}'")

    update_thinking(command=command, stage="Normalized", intent=cleaned)

    # ── Step 2: Compound command? (create + write in one) ────
    if is_compound_file_command(cleaned):
        print(f"⚙️  Compound file command detected")
        return _handle_compound_file(command, cleaned, actions, start_time, _source, _request_id)

    # ── Step 2.5: Search and Send? ───────────────────────────
    if is_find_and_send_command(cleaned):
        print(f"⚙️  Compound search and send detected")
        return _handle_find_and_send_command(command, cleaned, actions, start_time, _source, _request_id)

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

    update_thinking(command=command, intent=intent.action, confidence=intent.confidence, stage="Classified")

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

    # ── Step 4.5: Structured interpretation + live context ──
    machine_context = _build_interpreter_context()
    missing_params = get_missing_params(intent.action, params)
    interpreted = interpret_command(
        cleaned,
        machine_context,
        fast_action=intent.action,
        fast_confidence=intent.confidence,
        fast_target=_pick_interpreter_target(params),
        fast_params=params,
        ambiguities=[f"missing:{name}" for name in missing_params],
    )
    if interpreted.params:
        params = dict(interpreted.params)
    if interpreted.target and "target" not in params:
        params["target"] = interpreted.target
    if interpreted.action:
        intent.action = interpreted.action
    if interpreted.confidence:
        intent.confidence = interpreted.confidence
    if interpreted.source:
        intent.source = interpreted.source

    # ── Phase 1 fix [P2]: target_type-based action correction ──
    # If target_type inference disagrees with the fast-intent action,
    # correct the action. e.g. fast_intent=open_app + target_type=website
    # → should become search_google or open_url, not open_app.
    _TARGET_TYPE_ACTION_CORRECTIONS = {
        ("open_app", "website"): "open_url",
        ("open_app", "browser_search"): "search_google",
        ("open_app", "file"): "read_file",
        ("open_app", "folder"): "open_folder",
        ("open_app", "email"): "search_emails",
        ("open_app", "tab"): "switch_to_app",
    }
    if interpreted.target_type and interpreted.target_type != "unknown":
        correction_key = (intent.action, interpreted.target_type)
        corrected_action = _TARGET_TYPE_ACTION_CORRECTIONS.get(correction_key)
        if corrected_action:
            print(f"🔀 Target-type correction: {intent.action} + {interpreted.target_type} → {corrected_action}")
            intent.action = corrected_action
            # Re-extract params for the corrected action
            fresh_params = _extract_params(corrected_action, cleaned)
            if fresh_params:
                params.update(fresh_params)

    print(
        f"🧠 Structured command: action={intent.action} "
        f"target={interpreted.target or '-'} target_type={interpreted.target_type or '-'} "
        f"ambiguities={interpreted.ambiguities or []}"
    )

    # ── Step 5: Confidence evaluation ────────────────────────
    conf_result = evaluate_confidence(
        action=intent.action,
        intent_confidence=intent.confidence,
        params=params,
        text=cleaned,
        has_context_ref=has_ctx,
        context_resolved=was_resolved if has_ctx else False,
    )
    missing_params = get_missing_params(intent.action, params)
    if _is_headless_source(_source):
        confidence_floor = _remote_confidence_floor(intent.action, params, missing_params)
        if confidence_floor and conf_result.score < confidence_floor:
            conf_result.score = confidence_floor
            conf_result.tier = (
                ConfidenceTier.HIGH if confidence_floor > 0.8 else ConfidenceTier.MEDIUM
            )
            conf_result.should_execute = True
            conf_result.should_confirm = intent.action in DESTRUCTIVE_ACTIONS
            conf_result.recommendation = (
                f"Remote deterministic action ({confidence_floor:.2f}) — using local executor."
            )
    print(f"🎯 Confidence: {conf_result.score:.2f} ({conf_result.tier.value}) — {conf_result.recommendation}")
    update_thinking(command=command, intent=intent.action, confidence=conf_result.score, stage="Confidence")

    # ── Step 5.5: ManagerBrain Decision (Phase 3) ────────────
    brain = get_brain()
    decision_result = brain.decide(
        command=command, 
        intent_action=intent.action, 
        intent_confidence=conf_result.score, 
        params=params, 
        text=cleaned, 
        has_context_ref=has_ctx, 
        context_resolved=was_resolved if has_ctx else False
    )

    if decision_result.decision == BrainDecision.PLAN_AND_EXECUTE:
        if _is_headless_source(_source):
            print("🤖 ManagerBrain: headless source detected — using deterministic action path")
        else:
            print("🤖 ManagerBrain: Complex command detected — routing to ManagerAgent")
            update_thinking(command=command, stage="Planning Task Graph")
            if brain._manager:
                brain._manager.run(command)
            else:
                print("⚠️ ManagerAgent not available — falling back to old logic")
                # Let it fall through to execution if no manager
            return True

    elif decision_result.decision == BrainDecision.CHAT:
        print("💬 ManagerBrain: Conversational input detected")
        # Ensure it skips execution and falls to Gemini
        conf_result.score = 0.0  

    # ── Step 6: Safety check ─────────────────────────────────
    safety = check_safety(intent.action, conf_result.score, has_ctx, word_count=len(cleaned.split()))
    missing_params = get_missing_params(intent.action, params)
    if missing_params and safety.decision in {SafetyDecision.EXECUTE, SafetyDecision.CONFIRM}:
        safety = SafetyDecision(
            SafetyDecision.CONTEXT_ASK,
            f"Missing required params: {', '.join(missing_params)}",
            intent.action,
            conf_result.score,
        )
    print(f"🛡️  Safety: {safety.decision} — {safety.reason}")

    latency_ms = (time.time() - start_time) * 1000

    # ── DECISION: EXECUTE ────────────────────────────────────
    # New flow: ack → execute → grounded result → log spoken text
    if safety.decision == SafetyDecision.EXECUTE:
        # 1. Instant ack (Mac say, truly fast)
        ack_text = get_ack(intent.action)
        if ack_text:
            completed = speak_ack(ack_text)
            if not completed:
                log_interaction(
                    you_said=command, action_taken=intent.action,
                    was_understood=True, intent_source=intent.source,
                    confidence=intent.confidence, latency_ms=latency_ms,
                    normalized_text=cleaned, spoken_text=ack_text,
                )
                return False

        # 2. Execute action → get structured result
        before_state = _capture_before_state(intent.action, params)
        result = _execute_action(intent.action, params, actions, text=command, _source=_source, _request_id=_request_id)
        result = _verify_action_result(intent.action, params, result, before_state, actions=actions, text=command)
        print(f"✅ Result: {result.summary if result.success else result.error}")

        # 3. Generate grounded spoken text from result
        spoken_text = get_result_text(result)

        # 4. Speak the actual outcome (skip for actions where ack IS the result)
        _SKIP_RESULT_SPEECH = {
            "volume_up", "volume_down", "mute", "unmute",
            "brightness_up", "brightness_down", "lock_screen",
            "close_tab", "new_tab", "fullscreen", "mission_control",
            "minimise_all", "show_desktop", "close_window",
            "pause_music", "next_track", "previous_track",
        }
        if intent.action not in _SKIP_RESULT_SPEECH:
            speak_result(spoken_text)

        # 5. Update context
        update_context(
            action=intent.action,
            target=params.get("target", params.get("name", params.get("query", ""))),
            result=result.summary,
            command=cleaned,
        )

        # 6. Log with actual spoken text
        latency_ms = (time.time() - start_time) * 1000
        full_spoken = f"{ack_text} {spoken_text}".strip() if ack_text else spoken_text
        log_interaction(
            you_said=command, action_taken=intent.action,
            was_understood=True, intent_source=intent.source,
            confidence=intent.confidence, latency_ms=latency_ms,
            normalized_text=cleaned, params=params,
            spoken_text=full_spoken,
        )

        save_exchange(command, full_spoken)

        # ── Phase 1: Store structured result for API / remote callers ──
        try:
            from core.command_models import CommandResponse, ExecutionStatus
            from core.runtime import store_result

            step = result.to_step_result()
            data = dict(result.data or {})
            data.setdefault("params", dict(params or {}))
            if ack_text:
                data.setdefault("ack", ack_text)

            resp = CommandResponse(
                request_id=_request_id,
                status=ExecutionStatus.COMPLETED if result.success else ExecutionStatus.FAILED,
                interpreted_action=intent.action,
                final_result=spoken_text,
                steps=[step],
                data=data,
                errors=[spoken_text] if not result.success else [],
                elapsed_ms=(time.time() - start_time) * 1000,
                source=_source,
            )
            store_result(resp)
        except Exception:
            pass

        # ── Reinforcement: track + boost successful action ───
        track_action(cleaned, intent.action, intent.confidence, params, intent.source)
        if result.success:
            boost_confidence(cleaned, intent.action)

        # ── Working Memory: record action ─────────────────────
        try:
            wm = get_working_memory()
            wm.record_action(
                action=intent.action,
                params=params,
                reason=f"User said '{command}'",
                outcome="success" if result.success else "failed",
                confidence=intent.confidence,
                error=result.error if not result.success else "",
                command=command,
                intent_source=intent.source,
            )
            # Phase 1: Update grounding context
            wm.update_grounding(
                last_action=intent.action,
                last_file=params.get("filename"),
            )
        except Exception:
            pass

        # Phase 1: Clear any stale pending task on successful execution
        if has_pending():
            clear_pending()

        # ── Continuous Memory: extract preferences from command ─
        try:
            cm = get_continuous_memory()
            cm.extract_and_store(command)
        except Exception:
            pass

        # ── Background Gemini: gated, only for interesting successes ─
        result_str = result.summary if result.success else f"Error: {result.error}"
        if not _is_headless_source(_source) and should_enhance(intent.action, result_str):
            generate_followup(
                action=intent.action,
                command=command,
                action_result=result_str,
                instant_response=ack_text or spoken_text,
                speak_func=speak_result,
            )

        return True

    elif safety.decision == SafetyDecision.CONFIRM:
        # Use response_policy for confirmation prompt
        prompt = get_confirmation(intent.action, params)
        if _is_headless_source(_source):
            confirmed_resp = ask_user_input(prompt, _source, _request_id, event_type="confirm")
            confirmed = confirmed_resp.strip().lower() in ("yes", "y", "confirm", "ok", "sure", "do it")
        else:
            confirmed = ask_voice_confirmation(prompt)

        if confirmed:
            ack_text = get_ack(intent.action)
            if ack_text:
                speak_ack(ack_text)

            before_state = _capture_before_state(intent.action, params)
            result = _execute_action(intent.action, params, actions, text=cleaned, _source=_source, _request_id=_request_id)
            result = _verify_action_result(intent.action, params, result, before_state, actions=actions, text=cleaned)
            spoken_text = get_result_text(result)
            speak_result(spoken_text)
            print(f"✅ Confirmed & executed: {result.summary}")

            update_context(
                action=intent.action,
                target=params.get("target", params.get("name", "")),
                result=result.summary,
                command=cleaned,
            )

            latency_ms = (time.time() - start_time) * 1000
            full_spoken = f"{ack_text} {spoken_text}".strip() if ack_text else spoken_text
            log_interaction(
                you_said=command, action_taken=intent.action,
                was_understood=True, intent_source=intent.source,
                confidence=intent.confidence, latency_ms=latency_ms,
                normalized_text=cleaned, params=params,
                spoken_text=full_spoken,
            )
            save_exchange(command, full_spoken)

            try:
                wm = get_working_memory()
                wm.record_action(
                    action=intent.action,
                    params=params,
                    reason=f"User confirmed '{command}'",
                    outcome="success" if result.success else "failed",
                    confidence=intent.confidence,
                    command=command,
                    intent_source=intent.source,
                )
            except Exception:
                pass

            # ── Phase 1: Store structured result for API / remote callers ──
            try:
                from core.command_models import CommandResponse, ExecutionStatus
                from core.runtime import store_result

                step = result.to_step_result()
                data = dict(result.data or {})
                data.setdefault("params", dict(params or {}))
                if ack_text:
                    data.setdefault("ack", ack_text)

                resp = CommandResponse(
                    request_id=_request_id,
                    status=ExecutionStatus.COMPLETED if result.success else ExecutionStatus.FAILED,
                    interpreted_action=intent.action,
                    final_result=spoken_text,
                    steps=[step],
                    data=data,
                    errors=[spoken_text] if not result.success else [],
                    elapsed_ms=(time.time() - start_time) * 1000,
                    source=_source,
                )
                store_result(resp)
            except Exception:
                pass
        else:
            latency_ms = (time.time() - start_time) * 1000
            log_interaction(
                you_said=command, action_taken=f"{intent.action}_cancelled",
                was_understood=True, intent_source=intent.source,
                confidence=intent.confidence, latency_ms=latency_ms,
                normalized_text=cleaned,
                spoken_text="Alright, cancelled.",
            )

            # ── Phase 1: Store cancellation for API / remote callers ──
            try:
                from core.command_models import CommandResponse, ExecutionStatus
                from core.runtime import store_result

                store_result(CommandResponse(
                    request_id=_request_id,
                    status=ExecutionStatus.CANCELLED,
                    interpreted_action=intent.action,
                    final_result="Cancelled by user.",
                    elapsed_ms=(time.time() - start_time) * 1000,
                    source=_source,
                    data={"params": dict(params or {})},
                ))
            except Exception:
                pass
        return True

    # ── DECISION: CONTEXT_ASK ────────────────────────────────
    # Phase 1: Smart clarification with pending task state.
    # Instead of just speaking a question and forgetting, we now
    # store a PendingTask so the user's next short answer resumes
    # the original task.
    elif safety.decision == SafetyDecision.CONTEXT_ASK:
        missing_params = get_missing_params(intent.action, params)

        # Use Phase 1 single-slot question builder
        question, missing_param = build_single_slot_question(
            intent.action, params, missing_params
        )

        if not question:
            # Fallback to old clarification if no missing param detected
            question = get_clarification(intent.action, params)
            missing_param = missing_params[0] if missing_params else "target"

        if _is_headless_source(_source):
            resp = ask_user_input(question, _source, _request_id, event_type="clarify")
            if resp:
                params = _apply_slot_reply(params, intent.action, missing_param or "target", resp)

                for _ in range(5):
                    remaining = get_missing_params(intent.action, params)
                    if not remaining:
                        break
                    next_question, next_param = build_single_slot_question(
                        intent.action, params, remaining
                    )
                    if not next_question:
                        next_question = get_clarification(intent.action, params)
                        next_param = remaining[0]
                    next_resp = ask_user_input(next_question, _source, _request_id, event_type="clarify")
                    if not next_resp:
                        from core.command_models import CommandResponse
                        from core.runtime import store_result
                        store_result(CommandResponse.fail(_request_id, intent.action, "Clarification cancelled.", source=_source))
                        return True
                    params = _apply_slot_reply(params, intent.action, next_param or "target", next_resp)

                ack_text = get_ack(intent.action)
                if ack_text:
                    speak_ack(ack_text)

                before_state = _capture_before_state(intent.action, params)
                result = _execute_action(intent.action, params, actions, text=cleaned, _source=_source, _request_id=_request_id)
                result = _verify_action_result(intent.action, params, result, before_state, actions=actions, text=cleaned)
                spoken_text = get_result_text(result)
                if intent.action not in {"volume_up", "volume_down", "brightness_up", "brightness_down"}:
                    speak_result(spoken_text)

                update_context(
                    action=intent.action,
                    target=params.get("target", params.get("name", params.get("query", ""))),
                    result=result.summary,
                    command=cleaned,
                )

                latency_ms = (time.time() - start_time) * 1000
                full_spoken = f"{ack_text} {spoken_text}".strip() if ack_text else spoken_text
                log_interaction(
                    you_said=command, action_taken=intent.action,
                    was_understood=True, intent_source=intent.source,
                    confidence=intent.confidence, latency_ms=latency_ms,
                    normalized_text=cleaned, params=params,
                    spoken_text=full_spoken,
                )
                save_exchange(command, full_spoken)
                _store_command_response(
                    _request_id, _source, intent.action, params,
                    result, spoken_text, start_time, ack_text,
                )
                return True
            else:
                from core.runtime import store_result
                from core.command_models import CommandResponse
                store_result(CommandResponse.fail(_request_id, intent.action, "Clarification cancelled.", source=_source))
                return True

        # Store pending task for resumption
        # Phase 1 fix: Detect follow-up intent from the original command
        # e.g., "make a folder, I want to write something in it"
        # → follow_up_action="edit_file", follow_up_params={"content": "something"}
        primary_clause, follow_action, follow_params = detect_follow_up_intent(command)
        if follow_action:
            print(f"🔗 Follow-up detected: {follow_action} (params={follow_params})")

        set_pending(PendingTask(
            action=intent.action,
            known_params=dict(params),
            missing_param=missing_param or "target",
            question_asked=question,
            original_command=command,
            normalized_command=cleaned,
            intent_source=intent.source,
            confidence=intent.confidence,
            follow_up_action=follow_action,
            follow_up_params=follow_params,
        ))

        speak_result(question)
        log_interaction(
            you_said=command, action_taken="context_ask_pending",
            was_understood=False, intent_source=intent.source,
            confidence=intent.confidence, latency_ms=latency_ms,
            normalized_text=cleaned,
            spoken_text=question,
        )
        return True

    # ── DECISION: GEMINI FALLBACK ────────────────────────────
    elif safety.decision == SafetyDecision.GEMINI:
        if _is_headless_source(_source):
            # Try Gemini for all headless commands — chat, questions, and ambiguous intents
            try:
                gemini_result = ask_gemini(command)
                gemini_type = gemini_result.get("type", "chat")
                gemini_action = gemini_result.get("action")
                gemini_response = gemini_result.get("response", "")

                if gemini_type == "chat" or gemini_action in ("answer_question", "general_chat", None):
                    # Conversational response — return as result
                    response_text = gemini_response or "I'm not sure about that."
                    result = ActionResult.ok(
                        intent.action, response_text, user_message=response_text
                    )
                    _store_command_response(
                        _request_id, _source, intent.action, params,
                        result, response_text, start_time,
                    )
                    return True

                elif gemini_type == "action" and gemini_action:
                    # Gemini resolved an action — execute it
                    ack_text = get_ack(gemini_action)
                    merged_params = _merge_gemini_params(gemini_result, params)
                    before_state = _capture_before_state(gemini_action, merged_params)
                    exec_result = _execute_action(
                        gemini_action, merged_params, actions,
                        text=command, _source=_source, _request_id=_request_id,
                    )
                    exec_result = _verify_action_result(
                        gemini_action, merged_params, exec_result,
                        before_state, actions=actions, text=command,
                    )
                    spoken_text = get_result_text(exec_result)
                    _store_command_response(
                        _request_id, _source, gemini_action, merged_params,
                        exec_result, spoken_text, start_time, ack_text or "",
                    )
                    # Learn from Gemini resolution
                    if gemini_action not in ("answer_question", "chat_response"):
                        learn(
                            normalized_input=cleaned,
                            action=gemini_action,
                            params=merged_params,
                            confidence=1.0,
                            source="gemini",
                        )
                    return True
            except Exception as e:
                print(f"⚠️  Gemini fallback error for headless: {e}")

            # Gemini failed — return a clear error
            msg = "I couldn't understand that well enough to act. Please rephrase."
            try:
                from core.command_models import CommandResponse, ExecutionStatus
                from core.runtime import store_result
                store_result(CommandResponse(
                    request_id=_request_id,
                    status=ExecutionStatus.FAILED,
                    interpreted_action=intent.action,
                    final_result=msg,
                    errors=[msg],
                    elapsed_ms=(time.time() - start_time) * 1000,
                    source=_source,
                    data={"params": dict(params or {})},
                ))
            except Exception:
                pass
            return True

        print(f"🤖 Falling back to Gemini (confidence={intent.confidence:.2f})")
        return _gemini_fallback(command, cleaned, actions, start_time, params)

    return True


def _handle_compound_file(
    raw_command: str,
    normalized_command: str,
    actions: dict,
    start_time: float,
    _source: str = "voice",
    _request_id: str = "",
) -> bool:
    """
    Handles compound create+write commands like:
    'create a file called notes.txt and write hello world in it'
    """
    params = extract_compound_file_params(normalized_command)
    filename = params.get("filename", "")
    location = params.get("location") or "desktop"
    content  = params.get("content")

    if not filename:
        name_response = ask_user_input(
            "What do you want me to name the file?",
            _source,
            _request_id,
            event_type="clarify",
        )
        if name_response and name_response.strip():
            # Use param extractor to clean up user's response like "name it hello"
            from core.param_extractors import extract_filename
            clean_name = extract_filename(name_response).get("filename")
            if clean_name:
                filename = clean_name
            else:
                filename = name_response.strip().split()[-1]
        else:
            speak_result("I didn't catch a name. Let's try again later.")
            return True

    # Handle format if no extension
    if "." not in filename:
        detected_fmt = _detect_format_from_context(normalized_command)
        if detected_fmt:
            filename = filename + detected_fmt
            print(f"📄 Auto-detected format: {detected_fmt}")
        else:
            fmt_response = ask_user_input(
                f"What format should {filename} be? Like text, document, python?",
                _source,
                _request_id,
                event_type="clarify",
            )
            if fmt_response:
                ext = _resolve_format(fmt_response)
                filename = filename + ext
            else:
                filename = filename + ".txt"

    # Step 1: Create the file
    speak_ack("Creating and writing.")
    if "create_file" in actions:
        actions["create_file"](filename, location)
        update_file_context(filename, action="create_file")
        print(f"📄 Created: {filename}")

    # Step 2: Write content (or ask for it)
    if not content:
        content_response = ask_user_input(
            "What do you want me to write in it?",
            _source,
            _request_id,
            event_type="clarify",
        )
        if content_response and content_response.strip():
            # Check if user is rejecting / correcting
            response_lower = content_response.strip().lower()
            rejection_words = {"no", "nothing", "never mind", "nevermind", "cancel",
                               "stop", "forget it", "don't", "not", "skip", "nope"}
            if any(w in response_lower for w in rejection_words):
                speak_result("Alright, file created without content.")
                track_action(normalized_command, "create_file", 1.0,
                           {"filename": filename}, "compound")
                return True
            content = content_response.strip()
        else:
            speak_result("I didn't catch that. You can tell me later.")
            track_action(normalized_command, "create_file", 1.0,
                       {"filename": filename}, "compound")
            latency_ms = (time.time() - start_time) * 1000
            log_interaction(
                you_said=raw_command, action_taken="create_file",
                was_understood=True, intent_source="compound",
                confidence=1.0, latency_ms=latency_ms,
                normalized_text=normalized_command,
                spoken_text=f"Created {filename}.",
            )
            return True

    if "edit_file" in actions:
        actions["edit_file"](filename, content, location)
        update_file_context(filename, action="edit_file")
        print(f"✏️  Wrote to: {filename}")

    result_summary = f"Created {filename} and wrote content"
    spoken_text = f"Created {filename} and wrote the content."
    speak_result(spoken_text)

    update_context(
        action="create_and_edit_file",
        target=filename,
        result=result_summary,
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
        spoken_text=spoken_text,
    )
    save_exchange(raw_command, spoken_text)

    if _is_headless_source(_source):
        _store_command_response(
            _request_id,
            _source,
            "create_and_edit_file",
            {"filename": filename, "content": content, "location": location},
            ActionResult.ok(
                "create_and_edit_file",
                result_summary,
                data={"filename": filename, "content": content, "location": location},
                user_message=spoken_text,
            ),
            spoken_text,
            start_time,
            "Creating and writing.",
        )

    if not _is_headless_source(_source) and should_enhance("create_file", result_summary):
        generate_followup(
            action="create_file",
            command=raw_command,
            action_result=result_summary,
            instant_response="Creating and writing.",
            speak_func=speak_result,
        )

    return True


def _gemini_fallback(
    raw_command: str,
    normalized_command: str,
    actions: dict,
    start_time: float,
    fallback_params: dict | None = None,
) -> bool:
    """
    Gemini fallback path. Called when fast engine confidence is too low.
    Also learns from the result for future fast resolution.
    """
    result = ask_gemini(raw_command)
    response_text = result.get("response", "On it.")
    action        = result.get("action")

    print(f"🤖 Gemini understood: {result}")

    # ── Chat response (no action) ────────────────────────────
    if result["type"] == "chat":
        completed = speak_chat(response_text)
        latency_ms = (time.time() - start_time) * 1000
        log_interaction(
            you_said=raw_command, action_taken="chat_response",
            was_understood=True, sent_to_gemini=True,
            gemini_response=response_text, intent_source="gemini",
            latency_ms=latency_ms, normalized_text=normalized_command,
            spoken_text=response_text,
        )
        return completed

    # ── Action response ──────────────────────────────────────
    if result["type"] == "action" and action:

        if action == "answer_question":
            completed = speak_chat(response_text)
            latency_ms = (time.time() - start_time) * 1000
            log_interaction(
                you_said=raw_command, action_taken="answer_question",
                was_understood=True, sent_to_gemini=True,
                gemini_response=response_text, intent_source="gemini",
                latency_ms=latency_ms, normalized_text=normalized_command,
                spoken_text=response_text,
            )
            return completed

        if action in DESTRUCTIVE_ACTIONS:
            prompt = get_confirmation(action, fallback_params)
            confirmed = ask_voice_confirmation(prompt)
            if not confirmed:
                latency_ms = (time.time() - start_time) * 1000
                log_interaction(
                    you_said=raw_command, action_taken=f"{action}_cancelled",
                    was_understood=True, sent_to_gemini=True,
                    intent_source="gemini", latency_ms=latency_ms,
                    normalized_text=normalized_command,
                    spoken_text="Alright, cancelled.",
                )
                return True

        # 1. Ack via response_policy (not Gemini wording)
        ack_text = get_ack(action)
        if ack_text:
            speak_ack(ack_text)

        # 2. Execute
        params = _merge_gemini_params(result, fallback_params)
        before_state = _capture_before_state(action, params)
        exec_result = _execute_action(action, params, actions, text=raw_command)
        exec_result = _verify_action_result(action, params, exec_result, before_state, actions=actions, text=raw_command)
        print(f"✅ Gemini action result: {exec_result.summary if exec_result.success else exec_result.error}")

        # 3. Grounded result
        spoken_text = get_result_text(exec_result)
        _SKIP_RESULT_SPEECH = {
            "volume_up", "volume_down", "mute", "unmute",
            "brightness_up", "brightness_down", "lock_screen",
            "close_tab", "new_tab", "fullscreen", "mission_control",
            "minimise_all", "show_desktop", "close_window",
        }
        if action not in _SKIP_RESULT_SPEECH:
            speak_result(spoken_text)

        update_context(
            action=action,
            target=params.get("target", params.get("name", params.get("filename", params.get("query", "")))),
            result=exec_result.summary,
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
        full_spoken = f"{ack_text} {spoken_text}".strip() if ack_text else spoken_text
        log_interaction(
            you_said=raw_command, action_taken=action,
            was_understood=True, sent_to_gemini=True,
            gemini_response=response_text, intent_source="gemini",
            latency_ms=latency_ms, normalized_text=normalized_command,
            params=params,
            spoken_text=full_spoken,
        )
        save_exchange(raw_command, full_spoken)

        # ── Working Memory: record Gemini action ──────────────
        try:
            wm = get_working_memory()
            wm.record_action(
                action=action,
                params=params,
                reason=f"Gemini resolved '{raw_command}'",
                outcome="success" if exec_result.success else "failed",
                confidence=1.0,
                command=raw_command,
                intent_source="gemini",
            )
        except Exception:
            pass

        # ── Continuous Memory: extract from command ───────────
        try:
            cm = get_continuous_memory()
            cm.extract_and_store(raw_command)
        except Exception:
            pass

        return True

    fallback_msg = "I understood but can't do that yet."
    speak_result(fallback_msg)
    latency_ms = (time.time() - start_time) * 1000
    log_interaction(
        you_said=raw_command, action_taken="unknown",
        was_understood=False, sent_to_gemini=True,
        gemini_response=str(result), intent_source="gemini",
        latency_ms=latency_ms, normalized_text=normalized_command,
        spoken_text=fallback_msg,
    )
    return True
