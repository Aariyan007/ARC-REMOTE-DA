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


# ─── Destructive Actions ─────────────────────────────────────
# These ALWAYS require voice confirmation before execution.
DESTRUCTIVE_ACTIONS = {
    "shutdown_pc",
    "restart_pc",
    "delete_file",
    "send_email",
    "sleep_mac",
}

# ─── Confidence Thresholds ──────────────────────────────────
HIGH_CONFIDENCE    = 0.85   # Execute immediately (safe actions)
MEDIUM_CONFIDENCE  = 0.50   # Execute safe actions, Gemini for destructive
LOW_CONFIDENCE     = 0.50   # Below this → always Gemini


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


def check_safety(action: str, confidence: float, has_context_reference: bool = False) -> SafetyDecision:
    """
    Decides whether to execute, confirm, or fall back to Gemini.

    Args:
        action:                The resolved action name
        confidence:            Intent engine confidence (0.0 - 1.0)
        has_context_reference: True if command contains pronouns like "it", "that"
    """
    # Context references need high confidence or clarification
    if has_context_reference and confidence < HIGH_CONFIDENCE:
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
    Timeout after `timeout` seconds → cancel (returns False).
    """
    from core.voice_response import speak
    from core.speech_to_text import listen

    # Speak the confirmation prompt
    speak(prompt)

    # Listen for yes/no
    print(f"⏳ Waiting for confirmation ({timeout}s timeout)...")
    start = time.time()

    response = listen()

    if time.time() - start > timeout:
        print("⏰ Confirmation timed out — cancelling")
        speak("Timed out. Cancelling.")
        return False

    if not response:
        speak("I didn't catch that. Cancelling to be safe.")
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
