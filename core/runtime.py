"""
Runtime — shared boot + canonical command execution.

Every entry point (main.py voice loop, main_ui.py API server, tests)
imports this module and calls boot() once, then calls execute_text_command()
for every command regardless of source.

Voice (speak) is an optional side effect gated by source.
"""

from __future__ import annotations

import sys
import os

# Prevent sentence_transformers from importing TensorFlow (we use PyTorch only).
# Without this, Keras 3 vs tf-keras conflict crashes the import chain.
os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("TRANSFORMERS_NO_TF", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import time
import uuid
import threading
from typing import Optional

if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from core.command_models import (
    CommandRequest, CommandResponse, ExecutionStatus, StepResult
)

# ─── Global state ─────────────────────────────────────────────

ACTIONS: dict = {}
_manager_agent = None
_booted = False
_boot_lock = threading.Lock()

# ─── Session store (in-memory, keyed by request_id) ───────────
_results: dict[str, CommandResponse] = {}
_results_lock = threading.Lock()


def store_result(response: CommandResponse) -> None:
    with _results_lock:
        _results[response.request_id] = response


def get_result(request_id: str) -> Optional[CommandResponse]:
    with _results_lock:
        return _results.get(request_id)


# ─── Boot ─────────────────────────────────────────────────────

def boot(*, voice: bool = True) -> bool:
    """
    Initialize all subsystems once.
    Safe to call multiple times (idempotent).

    Args:
        voice: If True, preload Whisper and start voice-related subsystems.
    """
    global _booted
    with _boot_lock:
        if _booted:
            return True
        print("=" * 50)
        print("  DESKTOP AUTOMATION ENGINE — STARTING")
        print("=" * 50)

        ok = _initialize_actions()
        if not ok:
            return False

        _initialize_fast_engine()

        if voice:
            _preload_whisper()

        _initialize_agents()
        _initialize_subsystems()

        _booted = True
        print("\n✅ Runtime ready.\n")
        return True


def _initialize_actions() -> bool:
    global ACTIONS
    try:
        from control import (
            open_vscode, open_safari, open_terminal,
            search_google, tell_time, tell_date,
            lock_screen, shutdown_pc, restart_pc, sleep_mac,
            morning_briefing, tell_weather,
            open_folder, create_folder, search_file,
            read_emails, search_emails, send_email, open_gmail,
            summarise_latest_pdf,
            volume_up, volume_down, mute, unmute, get_volume,
            brightness_up, brightness_down, take_screenshot,
            minimise_all, minimise_app, show_desktop, close_window,
            get_battery, start_work_day, end_work_day,
            close_app, switch_to_app, fullscreen, mission_control,
            close_tab, new_tab,
            read_file, create_file, delete_file,
            rename_file, get_recent_files, copy_file, edit_file,
        )
        from core.daily_greeting import read_news
    except ImportError as e:
        # Partial failure — log but continue with whatever loaded
        print(f"⚠️  Some control modules unavailable: {e}")
        print("   Boot will continue with reduced action set.")
        # Try to import each module individually to salvage what works
        try:
            from control import (
                open_vscode, open_safari, open_terminal,
                search_google, tell_time, tell_date,
                lock_screen, shutdown_pc, restart_pc, sleep_mac,
                open_folder, create_folder, search_file,
                volume_up, volume_down, mute, unmute, get_volume,
                brightness_up, brightness_down, take_screenshot,
                minimise_all, minimise_app, show_desktop, close_window,
                get_battery, start_work_day, end_work_day,
                close_app, switch_to_app, fullscreen, mission_control,
                close_tab, new_tab,
                read_file, create_file, delete_file,
                rename_file, get_recent_files, copy_file, edit_file,
                search_files_advanced,
            )
        except ImportError as e2:
            print(f"⚠️  Control layer fully unavailable: {e2}")
            return False

    # Build ACTIONS from whatever loaded — missing funcs are skipped
    _action_candidates = {
        "open_vscode": "open_vscode", "open_safari": "open_safari",
        "open_terminal": "open_terminal", "search_google": "search_google",
        "tell_time": "tell_time", "tell_date": "tell_date",
        "lock_screen": "lock_screen", "shutdown_pc": "shutdown_pc",
        "restart_pc": "restart_pc", "sleep_mac": "sleep_mac",
        "morning_briefing": "morning_briefing", "tell_weather": "tell_weather",
        "read_news": "read_news",
        "open_folder": "open_folder", "create_folder": "create_folder",
        "search_file": "search_file",
        "read_emails": "read_emails", "search_emails": "search_emails",
        "send_email": "send_email", "open_gmail": "open_gmail",
        "summarise_pdf": "summarise_latest_pdf",
        "volume_up": "volume_up", "volume_down": "volume_down",
        "mute": "mute", "unmute": "unmute", "get_volume": "get_volume",
        "brightness_up": "brightness_up", "brightness_down": "brightness_down",
        "take_screenshot": "take_screenshot",
        "minimise_all": "minimise_all", "minimise_app": "minimise_app",
        "show_desktop": "show_desktop", "close_window": "close_window",
        "close_tab": "close_tab", "new_tab": "new_tab",
        "fullscreen": "fullscreen", "mission_control": "mission_control",
        "close_app": "close_app", "switch_to_app": "switch_to_app",
        "get_battery": "get_battery",
        "start_work_day": "start_work_day", "end_work_day": "end_work_day",
        "read_file": "read_file", "create_file": "create_file",
        "edit_file": "edit_file", "delete_file": "delete_file",
        "rename_file": "rename_file", "get_recent_files": "get_recent_files",
        "copy_file": "copy_file",
        "search_files_advanced": "search_files_advanced",
    }
    _locals = locals()
    for action_name, var_name in _action_candidates.items():
        if var_name in _locals:
            ACTIONS[action_name] = _locals[var_name]
    
    if ACTIONS:
        print(f"✅ Loaded {len(ACTIONS)} actions")
    else:
        print("⚠️  No actions loaded!")
        return False

    # Playwright browser actions
    try:
        from control.playwright_browser import (
            action_web_back, action_web_close_tab,
            action_web_new_tab, action_web_refresh,
        )
        ACTIONS.update({
            "web_back": action_web_back, "web_refresh": action_web_refresh,
            "web_new_tab": action_web_new_tab, "web_close_tab": action_web_close_tab,
        })
    except ImportError:
        pass

    # Windows-specific
    if sys.platform == "win32":
        try:
            from control import open_cmd, open_powershell, open_windows_terminal
            ACTIONS.update({
                "open_cmd": open_cmd,
                "open_powershell": open_powershell,
                "open_windows_terminal": open_windows_terminal,
            })
        except ImportError:
            pass

    return True


def _initialize_fast_engine() -> bool:
    print("🧠 Initializing fast intent engine...")
    try:
        from core.fast_intent import initialize
        from core.learned_intents import get_learned_examples, get_stats
        learned = get_learned_examples()
        initialize(learned)
        stats = get_stats()
        if stats.get("total", 0) > 0:
            print(f"📚 Loaded {stats['total']} learned intents")
        print("✅ Fast intent engine ready")
        return True
    except ModuleNotFoundError as e:
        print(f"⚠️  Fast intent engine unavailable: {e}")
        return False


def _preload_whisper() -> None:
    try:
        from core.speech_to_text import preload_whisper
        preload_whisper()
    except Exception as e:
        print(f"⚠️  Whisper preload skipped: {e}")


def _initialize_agents() -> None:
    global _manager_agent
    print("🤖 Initializing multi-agent system...")
    try:
        from core.agents.filesystem_agent import FileSystemAgent
        from core.agents.system_agent import SystemControlAgent
        from core.agents.manager_agent import ManagerAgent
        from core.agents.music_agent import MusicAgent
        from core.agents.companion_agent import CompanionAgent
        from core.agents.research_agent import ResearchAgent
        from core.agents.knowledge_agent import KnowledgeAgent
        from core.agents.computer_use_agent import ComputerUseAgent

        agents_dict = {
            "filesystem":   FileSystemAgent(actions_map=ACTIONS),
            "system":       SystemControlAgent(actions_map=ACTIONS),
            "music":        MusicAgent(),
            "companion":    CompanionAgent(),
            "research":     ResearchAgent(),
            "knowledge":    KnowledgeAgent(),
            "computer_use": ComputerUseAgent(),
        }
        try:
            from core.agents.window_agent import WindowAgent
            agents_dict["window"] = WindowAgent()
        except ImportError:
            pass

        _manager_agent = ManagerAgent(agents=agents_dict, actions=ACTIONS)
        agents = _manager_agent.list_agents()
        print(f"✅ Agents ready: {', '.join(agents)}")
    except Exception as e:
        print(f"⚠️  Agent init failed: {e}")


def _initialize_subsystems() -> None:
    """Start background subsystems: thinking UI, event bus, perception, proactive loop, memory."""
    from core.voice_response import speak

    try:
        from core.thinking_ui import init_thinking_ui
        init_thinking_ui()
        print("🖥️  Thinking UI started")
    except Exception as e:
        print(f"⚠️  Thinking UI skipped: {e}")

    try:
        from core.interrupt_manager import get_interrupt_manager
        get_interrupt_manager()
        print("⛔ Interrupt manager ready")
    except Exception:
        pass

    try:
        from core.event_bus import get_event_bus
        _event_bus = get_event_bus()
        print("📡 Event bus ready")
    except Exception:
        pass

    try:
        from core.perception_engine import get_perception_engine
        _perception = get_perception_engine()
        _perception.start()
    except Exception as e:
        print(f"⚠️  Perception engine skipped: {e}")

    try:
        from core.proactive_loop import get_proactive_loop
        from core.speech_to_text import listen as stt_listen
        _proactive = get_proactive_loop(speak_func=speak, listen_func=stt_listen)
        _proactive.start()
    except Exception as e:
        print(f"⚠️  Proactive loop skipped: {e}")

    # Memory subsystems
    for name, loader in [
        ("Continuous memory",  lambda: __import__('core.continuous_memory', fromlist=['get_continuous_memory']).get_continuous_memory()),
        ("Working memory",     lambda: __import__('core.working_memory',    fromlist=['get_working_memory']).get_working_memory()),
        ("Error corrections",  lambda: __import__('core.error_correction',  fromlist=['get_error_correction_store']).get_error_correction_store()),
        ("Memory integrator",  lambda: __import__('core.memory_integrator', fromlist=['get_memory_integrator']).get_memory_integrator()),
        ("Vector memory",      lambda: __import__('core.vector_memory',     fromlist=['get_vector_memory']).get_vector_memory()),
    ]:
        try:
            loader()
            print(f"[M] {name} ready")
        except Exception as e:
            print(f"⚠️  {name} skipped: {e}")

    # Brain
    try:
        from core.brain import get_brain
        get_brain(manager_agent=_manager_agent, actions=ACTIONS)
        print("🧠 ManagerBrain ready")
    except Exception as e:
        print(f"⚠️  ManagerBrain skipped: {e}")

    # Habits
    try:
        from core.habits import refresh_habits
        habits = refresh_habits(days=30)
        if habits:
            print(f"🔁 Habits: {len(habits)} patterns detected")
    except Exception:
        pass

    # Retrospective
    try:
        from core.retrospective import run_retrospective
        retro = run_retrospective()
        if retro.get("fixes", 0) > 0:
            print(f"[R] Applied {retro['fixes']} self-corrections")
    except Exception:
        pass


# ─── Canonical command entry point ────────────────────────────

def execute_text_command(
    text: str,
    source: str = "voice",
    session_id: Optional[str] = None,
    user: str = "aariyan",
) -> CommandResponse:
    """
    THE single entry point for all commands regardless of origin.

    Args:
        text:       The raw command string ("find uber.txt and email it to ...")
        source:     "voice" | "api" | "phone" | "local_ui"
        session_id: optional grouping key for related commands
        user:       who is issuing the command

    Returns:
        CommandResponse with full execution log.
        Voice output (speak) is a side effect gated on source == "voice".
    """
    if not _booted:
        return CommandResponse.fail(
            str(uuid.uuid4()), "boot",
            "Runtime not booted. Call runtime.boot() first.",
            source=source,
        )

    # Non-voice sources should never trigger local TTS by default.
    prev_silent = os.environ.get("ARC_SILENT")
    if source != "voice":
        os.environ["ARC_SILENT"] = "1"

    request = CommandRequest(
        text=text, source=source, user=user, session_id=session_id
    )
    if session_id:
        request.id = session_id

    start = time.time()

    try:
        # ── Phase 4: WorkflowEngine first ────────────────────────
        try:
            from core.workflow_engine import get_workflow_engine
            engine = get_workflow_engine()
            workflow_name = engine.match(text)
            if workflow_name:
                print(f"⚙️  WorkflowEngine matched: {workflow_name}")
                response = engine.run(workflow_name, text, request.id, source=source)
                response.elapsed_ms = (time.time() - start) * 1000
                store_result(response)
                return response
        except Exception as e:
            print(f"⚠️  WorkflowEngine error: {e}")

        # ── Fallback: existing intent_router pipeline ─────────────
        from core.intent_router import route
        # route() returns bool (was_interrupted); wrap its output
        route(text, ACTIONS, _source=source, _request_id=request.id)

        # Retrieve structured result if intent_router stored one
        response = get_result(request.id)
        if response is None:
            # route() didn't store a result — build a minimal OK response
            response = CommandResponse.ok(
                request.id, "unknown", "Command processed.",
                elapsed_ms=(time.time() - start) * 1000, source=source,
            )
    except Exception as e:
        response = CommandResponse.fail(
            request.id, "unknown", str(e),
            elapsed_ms=(time.time() - start) * 1000, source=source,
        )
    finally:
        if source != "voice":
            if prev_silent is None:
                os.environ.pop("ARC_SILENT", None)
            else:
                os.environ["ARC_SILENT"] = prev_silent

    response.elapsed_ms = (time.time() - start) * 1000
    store_result(response)
    return response
