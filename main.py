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
import warnings
os.environ["TORCHCODEC_DISABLE_LOAD"] = "1"
# Ensure homebrew binaries (ffmpeg, etc.) are in PATH
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
from core.listener import start_listener
from core.speech_to_text import listen
from core.intent_router import route

# ── Control modules ──────────────────────────────────────────
from control.mac.open_apps import open_vscode, open_safari, open_terminal
from control.web_search import search_google
from control.time_utils import tell_time, tell_date
from control.mac.system_actions import lock_screen, shutdown_pc, restart_pc, sleep_mac
from control.mac.briefing import morning_briefing
from control.mac.weather import tell_weather
from control.mac.folder_control import open_folder, create_folder, search_file
from control.email_control import read_emails, search_emails, send_email, open_gmail
from control.pdf_summariser import summarise_latest_pdf
from control.mac.system_controls import (
    volume_up, volume_down, mute, unmute, get_volume,
    brightness_up, brightness_down, take_screenshot,
    minimise_all, minimise_app, show_desktop, close_window,
    get_battery, start_work_day, end_work_day,
    close_app, switch_to_app, fullscreen, mission_control,
    close_tab, new_tab
)

from control.mac.file_ops import (
    read_file, create_file, delete_file,
    rename_file, get_recent_files, copy_file
)

# ── Action map ───────────────────────────────────────────────
ACTIONS = {
    # Apps
    "open_vscode":       open_vscode,
    "open_safari":       open_safari,
    "open_terminal":     open_terminal,

    # Web
    "search_google":     search_google,

    # Time
    "tell_time":         tell_time,
    "tell_date":         tell_date,

    # System
    "lock_screen":       lock_screen,
    "shutdown_pc":       shutdown_pc,
    "restart_pc":        restart_pc,
    "sleep_mac":         sleep_mac,

    # Info
    "morning_briefing":  morning_briefing,
    "tell_weather":      tell_weather,

    # Folders
    "open_folder":       open_folder,
    "create_folder":     create_folder,
    "search_file":       search_file,

    # Email
    "read_emails":       read_emails,
    "search_emails":     search_emails,
    "send_email":        send_email,
    "open_gmail":        open_gmail,

    # PDF
    "summarise_pdf":     summarise_latest_pdf,

    # Volume
    "volume_up":         volume_up,
    "volume_down":       volume_down,
    "mute":              mute,
    "unmute":            unmute,
    "get_volume":        get_volume,

    # Brightness
    "brightness_up":     brightness_up,
    "brightness_down":   brightness_down,

    # Screenshot
    "take_screenshot":   take_screenshot,

    # Windows
    "minimise_all":      minimise_all,
    "minimise_app":      minimise_app,
    "show_desktop":      show_desktop,
    "close_window":      close_window,
    "close_tab":         close_tab,
    "new_tab":           new_tab,
    "fullscreen":        fullscreen,
    "mission_control":   mission_control,

    # App control
    "close_app":         close_app,
    "switch_to_app":     switch_to_app,

    # Battery
    "get_battery":       get_battery,

    # Routines
    "start_work_day":    start_work_day,
    "end_work_day":      end_work_day,
    
    "read_file":       read_file,
    "create_file":     create_file,
    "delete_file":     delete_file,
    "rename_file":     rename_file,
    "get_recent_files": get_recent_files,
    "copy_file":       copy_file,
}

CORRECTION_WORDS = ["no", "not that", "wrong", "other", "different", "actually", "instead"]

# ── Agent triggers for complex multi-step commands ───────────
AGENT_TRIGGERS = [
    "find", "search for", "look for", "check if",
    "and then", "after that", "also open", "then",
    "summarise", "tell me about", "read and",
    "open and", "find and", "check my emails and",
]


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
    initialize(learned)

    stats = get_stats()
    if stats.get("total", 0) > 0:
        print(f"📚 Loaded {stats['total']} learned intents ({stats.get('unique_actions', 0)} unique actions)")
    print("✅ Fast intent engine ready\n")


def assistant_loop():
    speak("Yes, I'm listening")
    print("\n✅ Jarvis activated — listening for your command...")

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

        # Correction handling — uses agent with context
        if any(w in command.lower() for w in CORRECTION_WORDS) and agent_module.LAST_AGENT_RESULT:
            print("🔄 Correction detected — continuing agent with context")
            context_command = f"{command}. Previous context: {agent_module.LAST_AGENT_RESULT}"
            run_agent(context_command, ACTIONS)
            continue

        # Complex multi-step commands — use agent
        if any(t in command.lower() for t in AGENT_TRIGGERS):
            print("🤖 Complex command — using agent")
            run_agent(command, ACTIONS)
            continue

        # ── Speed-first pipeline ─────────────────────────────
        # This is the new pipeline:
        # normalize → fast intent → safety check → execute
        was_interrupted = route(command, ACTIONS)

        if not was_interrupted:
            print("✋ Interrupted — listening for new command...")
            # Loop continues naturally


def main():
    print("=" * 50)
    print("  JARVIS STARTING UP")
    print("=" * 50)

    # Initialize the fast intent engine (loads model + embeddings)
    _initialize_fast_engine()

    print("Say the wake word to activate Jarvis...\n")

    while True:
        activated = start_listener()
        if activated:
            assistant_loop()
            print("\nWaiting for wake word again...\n")


if __name__ == "__main__":
    main()
