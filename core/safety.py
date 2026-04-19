"""
Safety Layer — confidence thresholds, destructive action confirmation,
and voice-based yes/no confirmation flow.

Rules:
- confidence > 0.85 → execute (unless destructive)
- 0.50 - 0.85 → execute if safe, Gemini if destructive
- < 0.50 → always Gemini fallback
- Destructive actions ALWAYS require voice confirmation
"""

import time
from typing import Optional

from core.voice_response import speak
from core.speech_to_text import listen


# ─── Destructive Actions ─────────────────────────────────────
# These ALWAYS require voice confirmation before execution.
DESTRUCTIVE_ACTIONS = {
    "shutdown_pc",
    "restart_pc",
    "delete_file",
    "sleep_mac",
}

# ─── Safe With Context ───────────────────────────────────────
# Non-destructive actions that can execute even with context
# references ("that", "it", "the file") at medium confidence.
SAFE_WITH_CONTEXT = {
    "edit_file", "read_file", "create_file", "copy_file",
    "get_recent_files", "open_app", "close_app", "switch_to_app",
    "open_folder", "volume_up", "volume_down", "rename_file",
    "mute", "unmute", "brightness_up", "brightness_down",
    "tell_time", "tell_date", "get_battery", "take_screenshot",
    "open_url", "web_back", "web_refresh", "web_new_tab", "web_close_tab",
}

# ─── Confidence Thresholds ──────────────────────────────────
HIGH_CONFIDENCE    = 0.85   # Execute immediately (safe actions)
MEDIUM_CONFIDENCE  = 0.50   # Execute safe actions, Gemini for destructive
LOW_CONFIDENCE     = 0.50   # Below this → always Gemini
CONFIDENCE_FLOOR   = 0.40   # Below this → ALWAYS Gemini, never execute


class SafetyDecision:
    """Result of a safety check."""
    EXECUTE        = "execute"         # Execute immediately
    CONFIRM        = "confirm"         # Ask user for confirmation
    GEMINI         = "gemini"          # Fall back to Gemini
    CONTEXT_ASK    = "context_ask"     # Ask for context clarification

    def __init__(self, decision: str, reason: str, action: str = None, confidence: float = 0.0):
        self.decision   = decision
        self.reason     = reason
        self.action     = action
        self.confidence = confidence

    def __repr__(self):
        return f"SafetyDecision({self.decision}, confidence={self.confidence:.2f}, reason='{self.reason}')"


def check_safety(action: str, confidence: float, has_context_reference: bool = False, word_count: int = 0) -> SafetyDecision:
    """
    Decides whether to execute, confirm, or fall back to Gemini.

    Args:
        action:                The resolved action name
        confidence:            Intent engine confidence (0.0 - 1.0)
        has_context_reference: True if command contains pronouns like "it", "that"
        word_count:            Number of words in the command (for garbage detection)
    """
    # Very short input (1-2 words) with low confidence → garbage, skip
    if word_count <= 2 and confidence < HIGH_CONFIDENCE:
        return SafetyDecision(
            SafetyDecision.GEMINI,
            "Too short to be meaningful — needs Gemini",
            action,
            confidence
        )

    # Absolute confidence floor — below this, nothing should execute
    if confidence < CONFIDENCE_FLOOR:
        return SafetyDecision(
            SafetyDecision.GEMINI,
            "Below minimum confidence floor — needs Gemini",
            action,
            confidence
        )

    # Context references — safe actions can execute at medium confidence
    if has_context_reference and confidence < HIGH_CONFIDENCE:
        if action in SAFE_WITH_CONTEXT and confidence >= 0.60:
            return SafetyDecision(
                SafetyDecision.EXECUTE,
                "Safe action with resolvable context reference",
                action,
                confidence
            )
        # Destructive + context → still ask for confirmation (not block)
        if action in DESTRUCTIVE_ACTIONS and confidence >= 0.60:
            return SafetyDecision(
                SafetyDecision.CONFIRM,
                f"Destructive action with context — confirmation required",
                action,
                confidence
            )
        return SafetyDecision(
            SafetyDecision.CONTEXT_ASK,
            "Ambiguous context reference with low confidence",
            action,
            confidence
        )

    # Destructive actions ALWAYS need confirmation
    if action in DESTRUCTIVE_ACTIONS:
        return SafetyDecision(
            SafetyDecision.CONFIRM,
            f"'{action}' is destructive — confirmation required",
            action,
            confidence
        )

    # High confidence → execute
    if confidence >= HIGH_CONFIDENCE:
        return SafetyDecision(
            SafetyDecision.EXECUTE,
            "High confidence match",
            action,
            confidence
        )

    # Medium confidence → execute (non-destructive was already caught above)
    if confidence >= MEDIUM_CONFIDENCE:
        return SafetyDecision(
            SafetyDecision.EXECUTE,
            "Medium confidence, non-destructive action",
            action,
            confidence
        )

    # Low confidence → Gemini fallback
    return SafetyDecision(
        SafetyDecision.GEMINI,
        "Low confidence — needs Gemini",
        action,
        confidence
    )


def ask_voice_confirmation(prompt: str, timeout: float = 10.0) -> bool:
    """
    Asks the user a yes/no question via voice, listens for response.
    Returns True if user confirms, False otherwise.
    """
    # Speak the confirmation prompt
    speak(prompt)

    # Listen — listen() already has its own silence+timeout logic
    print(f"⏳ Waiting for confirmation...")
    response = listen()

    if not response or not response.strip():
        print("⏰ No response — cancelling")
        speak("Timed out. Cancelling.")
        return False

    response = response.lower().strip()

    YES_WORDS = {"yes", "yeah", "yep", "yup", "sure", "do it", "go ahead",
                 "confirm", "ok", "okay", "affirmative", "proceed", "absolutely"}
    NO_WORDS  = {"no", "nope", "nah", "cancel", "stop", "don't", "abort",
                 "negative", "nevermind", "never mind", "wait"}

    for word in YES_WORDS:
        if word in response:
            print("✅ User confirmed")
            return True

    for word in NO_WORDS:
        if word in response:
            print("❌ User denied")
            speak("Alright, cancelled.")
            return False

    # Ambiguous response
    speak("I wasn't sure about that. Cancelling to be safe.")
    return False


# ─── Quick test ──────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("  SAFETY LAYER TEST")
    print("=" * 60)

    tests = [
        ("open_app",     0.95, False),
        ("open_app",     0.70, False),
        ("open_app",     0.30, False),
        ("shutdown_pc",  0.99, False),   # Always confirms
        ("delete_file",  0.90, False),   # Always confirms
        ("close_app",    0.80, True),    # Context: "close it"
        ("close_app",    0.90, True),    # High confidence context OK
    ]

    for action, conf, ctx in tests:
        result = check_safety(action, conf, ctx)
        print(f"  {action} (conf={conf}, ctx={ctx}) → {result}")
