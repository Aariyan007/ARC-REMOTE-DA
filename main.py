import sys
from core.voice_response import speak
from core.logger import print_todays_summary
from core.memory import clear_conversation
from control.briefing import morning_briefing
from control.open_apps import open_settings
from control.weather import tell_weather

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
from control.open_apps import open_vscode, open_safari, open_terminal
from control.web_search import search_google
from control.time_utils import tell_time, tell_date
from control.system_actions import lock_screen, shutdown_pc, restart_pc, sleep_mac

# ── Action map ───────────────────────────────────────────────
ACTIONS = {
    "open_vscode":    open_vscode,
    "open_safari":    open_safari,
    "open_terminal":  open_terminal,
    "search_google":  search_google,
    "tell_time":      tell_time,
    "tell_date":      tell_date,
    "lock_screen":    lock_screen,
    "shutdown_pc":    shutdown_pc,
    "restart_pc":     restart_pc,
    "sleep_mac":      sleep_mac,
    "morning_briefing": morning_briefing,
    "open_settings": open_settings,
    "tell_weather": tell_weather,
}


def assistant_loop():
    speak("Yes, I'm listening")
    print("\n✅ Jarvis activated — listening for your command...")

    while True:
        command = listen()

        if not command:
            print("⚠️  Didn't catch that. Try again.")
            continue

        if any(word in command for word in ["goodbye", "go to sleep", "stop listening"]):
            clear_conversation() 
            print_todays_summary()
            speak("Going to sleep. Goodbye.")
            print("😴 Jarvis going to sleep...")
            break

        route(command, ACTIONS)


def main():
    print("=" * 50)
    print("  JARVIS STARTING UP")
    print("=" * 50)
    print("Say the wake word to activate Jarvis...\n")

    while True:
        activated = start_listener()
        if activated:
            assistant_loop()
            print("\nWaiting for wake word again...\n")


if __name__ == "__main__":
    main()