"""
Jarvis — Real-Time Voice AI Assistant (Production Pipeline)

Architecture:
   Wake Word → Whisper STT → Normalize → Fast Intent Engine
   → Safety Check → Execute + Instant Response
                          ↓ (background)
                    Gemini Smart Follow-up

Speed-first: fast local logic for most tasks,
Gemini only when necessary or in background.
"""

import os
import sys

# ── Fix speechbrain lazy module crashes ──────────────────────
# speechbrain 1.x uses lazy module loading. When Python's inspect module
# (used by torch) calls hasattr(module, '__file__') or getfile(module),
# it triggers the lazy loader which fails for missing optional deps (k2).
# Even for successfully loaded modules, __file__ might be None causing
# TypeError in inspect.getfile(). Fix both issues at the source.
try:
    import speechbrain.utils.importutils as _sb_importutils
    _OrigLazyModule = _sb_importutils.LazyModule

    _orig_ensure = _OrigLazyModule.ensure_module
    def _safe_ensure(self, *args, **kwargs):
        try:
            return _orig_ensure(self, *args, **kwargs)
        except (ImportError, Exception):
            import types
            target_name = getattr(self, 'target', 'unknown')
            dummy = types.ModuleType(target_name)
            dummy.__file__ = target_name.replace('.', '/') + '.py'
            dummy.__path__ = []
            dummy.__package__ = target_name
            self.lazy_module = dummy
            return dummy
    _OrigLazyModule.ensure_module = _safe_ensure

    _orig_getattr = _OrigLazyModule.__getattr__
    def _safe_getattr(self, attr):
        if attr == '__file__':
            try:
                mod = self.ensure_module(1)
                f = getattr(mod, '__file__', None)
                if f is not None:
                    return f
            except Exception:
                pass
            target = getattr(self, 'target', 'unknown')
            return target.replace('.', '/') + '.py'
        return _orig_getattr(self, attr)
    _OrigLazyModule.__getattr__ = _safe_getattr
except Exception:
    pass
# ─────────────────────────────────────────────────────────────

import warnings
os.environ["TORCHCODEC_DISABLE_LOAD"] = "1"
# Ensure homebrew binaries (ffmpeg, etc.) are in PATH (Mac only)
import sys as _sys
if _sys.platform == "darwin":
    os.environ["PATH"] = "/opt/homebrew/bin:" + os.environ.get("PATH", "")
warnings.filterwarnings("ignore", message=".*torchcodec.*")
warnings.filterwarnings("ignore", message=".*FFmpeg.*")
warnings.filterwarnings("ignore", category=UserWarning)

import sys
from core.voice_response import speak, speak_and_wait
from core.logger import print_todays_summary
from core.memory import clear_conversation
from core.agent import run_agent
import core.agent as agent_module

try:
    import dotenv
except ImportError:
    dotenv = None

if dotenv is not None:
    dotenv.load_dotenv()

try:
    import pkg_resources
except ImportError:
    class _MockDistribution:
        def __init__(self, version='2.0.10'):
            self.version = version
    class _MockPkgResources:
        def get_distribution(self, name):
            return _MockDistribution()
    sys.modules['pkg_resources'] = _MockPkgResources()

# ── Core modules ─────────────────────────────────────────────
from core.speech_to_text import listen
from core.intent_router import route

ACTIONS = {}


# Correction handling now uses reinforcement learning
from core.reinforcement import is_correction, handle_correction, track_action

# ── Multi-Agent System ───────────────────────────────────────
# Triggers that indicate multi-step / complex commands → ManagerAgent
AGENT_TRIGGERS = [
    "search for", "look for", "check if",
    "after that", "also open", "and then",
    "summarise", "tell me about", "read and",
    "open and", "find and", "check my emails and",
    "research", "send my", "email my",
    "look up", "find out", "what is", "who is",
]

# ── Agent instances (initialized in main) ────────────────────
_manager_agent = None


def _initialize_actions():
    """Load control layer lazily so importing main doesn't require full runtime deps."""
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
        print(f"⚠️  Control layer unavailable: {e}")
        print("Install project dependencies first with: pip install -r requirements.txt")
        return False

    ACTIONS = {
        "open_vscode": open_vscode,
        "open_safari": open_safari,
        "open_terminal": open_terminal,
        "search_google": search_google,
        "tell_time": tell_time,
        "tell_date": tell_date,
        "lock_screen": lock_screen,
        "shutdown_pc": shutdown_pc,
        "restart_pc": restart_pc,
        "sleep_mac": sleep_mac,
        "morning_briefing": morning_briefing,
        "tell_weather": tell_weather,
        "read_news": read_news,
        "open_folder": open_folder,
        "create_folder": create_folder,
        "search_file": search_file,
        "read_emails": read_emails,
        "search_emails": search_emails,
        "send_email": send_email,
        "open_gmail": open_gmail,
        "summarise_pdf": summarise_latest_pdf,
        "volume_up": volume_up,
        "volume_down": volume_down,
        "mute": mute,
        "unmute": unmute,
        "get_volume": get_volume,
        "brightness_up": brightness_up,
        "brightness_down": brightness_down,
        "take_screenshot": take_screenshot,
        "minimise_all": minimise_all,
        "minimise_app": minimise_app,
        "show_desktop": show_desktop,
        "close_window": close_window,
        "close_tab": close_tab,
        "new_tab": new_tab,
        "fullscreen": fullscreen,
        "mission_control": mission_control,
        "close_app": close_app,
        "switch_to_app": switch_to_app,
        "get_battery": get_battery,
        "start_work_day": start_work_day,
        "end_work_day": end_work_day,
        "read_file": read_file,
        "create_file": create_file,
        "edit_file": edit_file,
        "delete_file": delete_file,
        "rename_file": rename_file,
        "get_recent_files": get_recent_files,
        "copy_file": copy_file,
    }

    try:
        from control.playwright_browser import (
            action_web_back,
            action_web_close_tab,
            action_web_new_tab,
            action_web_refresh,
        )

        ACTIONS["web_back"] = action_web_back
        ACTIONS["web_refresh"] = action_web_refresh
        ACTIONS["web_new_tab"] = action_web_new_tab
        ACTIONS["web_close_tab"] = action_web_close_tab
    except ImportError as e:
        print(f"⚠️  Playwright not available — install: pip install playwright && playwright install chromium ({e})")

    if sys.platform == "win32":
        from control import open_cmd, open_powershell, open_windows_terminal
        ACTIONS["open_cmd"] = open_cmd
        ACTIONS["open_powershell"] = open_powershell
        ACTIONS["open_windows_terminal"] = open_windows_terminal

    return True


def _initialize_fast_engine():
    """
    Initialize the fast intent engine on startup.
    Loads the sentence-transformer model and pre-computes embeddings.
    Also loads learned intents from the database.
    """
    print("\n🧠 Initializing fast intent engine...")
    from core.fast_intent import initialize
    from core.learned_intents import get_learned_examples, get_stats

    # Load learned examples and inject into intent engine
    learned = get_learned_examples()
    try:
        initialize(learned)
    except ModuleNotFoundError as e:
        if e.name == "sentence_transformers":
            print("⚠️  Fast intent engine unavailable: sentence_transformers is not installed.")
            print("Install project dependencies first with: pip install -r requirements.txt")
            return False
        raise

    stats = get_stats()
    if stats.get("total", 0) > 0:
        print(f"📚 Loaded {stats['total']} learned intents ({stats.get('unique_actions', 0)} unique actions)")
    print("✅ Fast intent engine ready\n")
    return True


def _initialize_agents():
    """
    Initialize the multi-agent system.
    Creates specialized agents and the ManagerAgent orchestrator.
    """
    global _manager_agent

    print("🤖 Initializing multi-agent system...")

    from core.agents.filesystem_agent import FileSystemAgent
    from core.agents.system_agent import SystemControlAgent
    from core.agents.manager_agent import ManagerAgent
    from core.agents.music_agent import MusicAgent
    from core.agents.companion_agent import CompanionAgent
    from core.agents.research_agent import ResearchAgent

    # Create specialized agents with access to their relevant actions
    # Create specialized agents with access to their relevant actions
    from core.agents.knowledge_agent import KnowledgeAgent
    fs_agent        = FileSystemAgent(actions_map=ACTIONS)
    sys_agent       = SystemControlAgent(actions_map=ACTIONS)
    music_agent     = MusicAgent()
    companion_agent = CompanionAgent()
    research_agent  = ResearchAgent()
    knowledge_agent = KnowledgeAgent()
    
    agents_dict = {
        "filesystem": fs_agent,
        "system":     sys_agent,
        "music":      music_agent,
        "companion":  companion_agent,
        "research":   research_agent,
        "knowledge":  knowledge_agent,
    }

    # Add Window Agent (Mac only for now)
    try:
        from core.agents.window_agent import WindowAgent
        agents_dict["window"] = WindowAgent()
    except ImportError:
        pass

    # Create the ManagerAgent (orchestrator)
    _manager_agent = ManagerAgent(
        agents=agents_dict,
        actions=ACTIONS,
    )

    agents = _manager_agent.list_agents()
    print(f"✅ Agents ready: {', '.join(agents)}")
    for name in agents:
        agent = _manager_agent.get_agent(name)
        print(f"   📦 {name}: {len(agent.capabilities)} actions")


_greeted_this_boot = False   # only greet once per process launch

def assistant_loop():
    global _greeted_this_boot

    # Respond immediately so the user knows Jarvis is active
    speak("Activated Sir")
    print("\n✅ Jarvis activated — listening for your command...")

    # ── Daily greeting runs in background (won't freeze the mic) ─
    if not _greeted_this_boot:
        _greeted_this_boot = True
        from core.daily_greeting import should_greet, daily_greeting
        if should_greet():
            import threading
            threading.Thread(target=daily_greeting, daemon=True).start()

    while True:
        command = listen()

        if not command:
            print("⚠️  Didn't catch that. Try again.")
            continue

        # Sleep commands
        if any(word in command for word in ["goodbye", "go to sleep", "stop listening"]):
            clear_conversation()
            print_todays_summary()
            speak_and_wait("Going to sleep. Goodbye.")
            print("😴 Jarvis going to sleep...")
            break

        # ── Correction handling (reinforcement learning) ─────
        if is_correction(command):
            print("🔄 Correction detected — learning from mistake")
            result = handle_correction(command, ACTIONS)
            print(f"📚 Correction result: {result}")
            continue

        # ── Fast/Brain pipeline ──────────────────────────────
        # ManagerBrain will intercept complex commands inside route()
        was_interrupted = route(command, ACTIONS)

        if not was_interrupted:
            print("✋ Interrupted — listening for new command...")
            # Loop continues naturally


def main():
    print("=" * 50)
    print("  JARVIS STARTING UP")
    print("=" * 50)

    if not _initialize_actions():
        return

    # Initialize the fast intent engine (loads model + embeddings)
    if not _initialize_fast_engine():
        return

    # Pre-warm Whisper so it never loads mid-command
    from core.speech_to_text import preload_whisper
    preload_whisper()

    # Initialize the multi-agent system
    _initialize_agents()

    # Initialize the Floating Thinking UI
    try:
        from core.thinking_ui import init_thinking_ui
        init_thinking_ui()
        print("🖥️  Thinking UI started")
    except Exception as e:
        print(f"⚠️  Thinking UI skipped: {e}")

    # Initialize the Interrupt Manager
    from core.interrupt_manager import get_interrupt_manager
    _interrupt_mgr = get_interrupt_manager()
    print("⛔ Interrupt manager ready")

    # ── Initialize Event Bus ─────────────────────────────────
    from core.event_bus import get_event_bus
    _event_bus = get_event_bus()
    print("📡 Event bus ready")

    # ── Initialize Perception Engine ─────────────────────────
    from core.perception_engine import get_perception_engine
    _perception = get_perception_engine()
    _perception.start()

    # ── Initialize Proactive Context Loop ────────────────────
    from core.proactive_loop import get_proactive_loop
    _proactive = get_proactive_loop(
        speak_func=speak,
        listen_func=listen,
    )
    _proactive.start()

    # ── Wire proactive music triggers to MusicAgent ──────────
    def _on_proactive_music(event):
        """Handle proactive music suggestion from ProactiveLoop."""
        data = event.data
        if data.get("trigger") == "music_suggestion" and _manager_agent:
            agent = _manager_agent.get_agent("music")
            if agent:
                agent.execute("play_playlist", {"query": data.get("query", "focus playlist")})

    _event_bus.subscribe("proactive_trigger", _on_proactive_music)


    # ── Initialize ManagerBrain (Phase 3) ────────────────────
    from core.brain import get_brain
    _brain = get_brain(manager_agent=_manager_agent, actions=ACTIONS)
    print("\U0001f9e0 ManagerBrain ready")

    # ── Initialize Cognitive Memory Layer ─────────────────────
    # Continuous Memory (long-term structured memory)
    try:
        from core.continuous_memory import get_continuous_memory
        _continuous_mem = get_continuous_memory()
        print(f"[M] Continuous memory ready ({_continuous_mem.count} memories)")
    except Exception as e:
        print(f"\u26a0\ufe0f  Continuous memory skipped: {e}")

    # Working Memory (short-term execution journal)
    try:
        from core.working_memory import get_working_memory
        _working_mem = get_working_memory()
        print("[M] Working memory ready")
    except Exception as e:
        print(f"\u26a0\ufe0f  Working memory skipped: {e}")

    # Error Correction Store (learned corrections)
    try:
        from core.error_correction import get_error_correction_store
        _error_corrections = get_error_correction_store()
        print(f"[M] Error corrections ready ({_error_corrections.count} corrections)")
    except Exception as e:
        print(f"\u26a0\ufe0f  Error corrections skipped: {e}")

    # Memory Integrator (pre-action orchestrator)
    try:
        from core.memory_integrator import get_memory_integrator
        _memory_integrator = get_memory_integrator()
        print("[M] Memory integrator ready")
    except Exception as e:
        print(f"\u26a0\ufe0f  Memory integrator skipped: {e}")

    # ── Initialize Vector Memory ─────────────────────────────
    try:
        from core.vector_memory import get_vector_memory
        _vector_mem = get_vector_memory()
        print(f"\U0001f4be Vector memory ready ({_vector_mem.document_count} documents)")
    except Exception as e:
        print(f"\u26a0\ufe0f  Vector memory skipped: {e}")

    # ── Initialize Habits Engine ─────────────────────────────
    try:
        from core.habits import refresh_habits, get_suggestions_for_now
        habits = refresh_habits(days=30)
        if habits:
            print(f"\U0001f501 Habits: {len(habits)} patterns detected")
        suggestions = get_suggestions_for_now()
        if suggestions:
            print(f"\U0001f4a1 Suggestions for now: {len(suggestions)}")
    except Exception as e:
        print(f"\u26a0\ufe0f  Habits engine skipped: {e}")

    # ── Run Retrospective Learning (review yesterday) ─────────
    try:
        from core.retrospective import run_retrospective
        retro = run_retrospective()  # Reviews yesterday's logs
        if retro.get("fixes", 0) > 0:
            print(f"[R] Applied {retro['fixes']} self-corrections from yesterday")
        elif retro.get("status") == "clean":
            print("[R] Yesterday's session was clean -- no fixes needed")
    except Exception as e:
        print(f"Warning: Retrospective skipped: {e}")

    print("\nSay the wake word to activate Jarvis...\n")

    try:
        from core.listener import start_listener
    except ImportError as e:
        print(f"⚠️  Wake-word listener unavailable: {e}")
        print("Install the missing audio/wake-word dependencies to run hotword mode.")
        return

    try:
        while True:
            activated = start_listener()
            if activated:
                assistant_loop()
                print("\nWaiting for wake word again...\n")
    except KeyboardInterrupt:
        print("\n⚠️  Shutting down...")
    finally:
        # ── Clean shutdown ─────────────────────────────────
        _proactive.stop()
        _perception.stop()
        _event_bus.shutdown()
        if _manager_agent:
            _manager_agent.shutdown()
        print("✅ Jarvis shut down cleanly.")


if __name__ == "__main__":
    main()
