import sys

# ── Compatibility fix (keep your existing one) ───────────────
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
from control.system_actions import lock_screen, shutdown_pc, restart_pc

# ── Action map ───────────────────────────────────────────────
# This is the single place that connects intent_router → control functions.
# To add a new command later: add it here + add it to COMMAND_REGISTRY in router.
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
}


def assistant_loop():
    """
    Core Jarvis loop — runs after wake word is detected.
    Listens for one command, executes it, then loops back.
    """
    print("\n✅ Jarvis activated — listening for your command...")

    while True:
        # Step 1: Hear the command
        command = listen()

        if not command:
            print("⚠️  Didn't catch that. Try again.")
            continue

        # Step 2: Exit words — go back to wake word mode
        if any(word in command for word in ["goodbye", "go to sleep", "stop listening"]):
            print("😴 Jarvis going to sleep. Say the wake word to activate again.")
            break

        # Step 3: Route to correct action
        route(command, ACTIONS)


def main():
    """
    Main entry point.
    Waits for wake word → activates Jarvis → listens for commands → repeats.
    """
    print("=" * 50)
    print("  JARVIS STARTING UP")
    print("=" * 50)
    print("Say the wake word to activate Jarvis...\n")

    while True:
        # Wait for wake word (your existing code — untouched)
        activated = start_listener()

        if activated:
            assistant_loop()
            # After sleep command — go back to waiting for wake word
            print("\nWaiting for wake word again...\n")


if __name__ == "__main__":
    main()