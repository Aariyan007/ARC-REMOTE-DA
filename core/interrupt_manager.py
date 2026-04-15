"""
Interrupt Manager — detects voice interrupts and cancels ongoing actions.

Interrupt phrases:
  - "wait", "stop", "hold on", "cancel", "never mind",
    "change that", "forget it", "that's wrong"

Provides:
  - is_interrupt(command): checks if command is an interrupt
  - InterruptManager: manages cancellation state via threading.Event
"""

import threading


# ─── Interrupt Phrases ───────────────────────────────────────
INTERRUPT_PHRASES = [
    "wait",
    "stop",
    "hold on",
    "cancel",
    "never mind",
    "nevermind",
    "change that",
    "forget it",
    "that's wrong",
    "no no no",
    "abort",
    "halt",
    "not that",
    "wrong one",
    "go back",
]


def is_interrupt(command: str) -> bool:
    """
    Returns True if the entire command is an interrupt phrase.
    Prevents false positives on commands like "stop the music".
    """
    if not command:
        return False
    
    # Clean up the command (remove punctuation, extraneous spaces)
    import string
    cmd = command.translate(str.maketrans('', '', string.punctuation)).lower().strip()
    
    # Strip optional "jarvis" from the beginning or end
    if cmd.startswith("jarvis "):
        cmd = cmd[7:].strip()
    elif cmd.endswith(" jarvis"):
        cmd = cmd[:-7].strip()

    # Must be an exact match to a known interrupt phrase
    return cmd in INTERRUPT_PHRASES


class InterruptManager:
    """
    Manages interrupt/cancellation state for the assistant pipeline.

    Usage:
        mgr = InterruptManager()

        # In route() or action execution:
        if mgr.should_cancel.is_set():
            return  # abort current action

        # When interrupt detected:
        mgr.cancel()

        # After handling interrupt:
        mgr.reset()
    """

    def __init__(self):
        self._cancel_event = threading.Event()
        self._lock = threading.Lock()
        self._last_command = ""

    @property
    def should_cancel(self) -> threading.Event:
        """Threading Event — set when an interrupt is active."""
        return self._cancel_event

    @property
    def is_cancelled(self) -> bool:
        """Quick check if cancellation is active."""
        return self._cancel_event.is_set()

    def cancel(self, reason: str = ""):
        """Signal that the current action should be cancelled."""
        with self._lock:
            self._cancel_event.set()
            self._last_command = reason
            print(f"✋ Interrupt triggered: {reason or 'user request'}")

    def reset(self):
        """Clear the cancellation state — ready for next command."""
        with self._lock:
            self._cancel_event.clear()
            self._last_command = ""

    def check_and_cancel(self, command: str) -> bool:
        """
        Convenience: check if command is an interrupt, and if so,
        set the cancel flag. Returns True if interrupted.
        """
        if is_interrupt(command):
            self.cancel(reason=command)
            return True
        return False


# ─── Module-level singleton ─────────────────────────────────
_manager = None


def get_interrupt_manager() -> InterruptManager:
    """Get or create the singleton InterruptManager."""
    global _manager
    if _manager is None:
        _manager = InterruptManager()
    return _manager


# ─── Quick test ──────────────────────────────────────────────
if __name__ == "__main__":
    tests = [
        "stop", "wait a second", "open vscode",
        "cancel that", "never mind", "search google",
        "hold on", "forget it", "change that please",
    ]

    print("=== Interrupt Manager Test ===")
    for cmd in tests:
        result = is_interrupt(cmd)
        print(f"  '{cmd}' → {'🛑 INTERRUPT' if result else '✅ normal'}")
