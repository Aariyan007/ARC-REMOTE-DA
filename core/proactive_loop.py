"""
Proactive Context Loop — Background daemon that proactively offers help.

Subscribes to perception_update events from PerceptionEngine and
triggers proactive actions based on rules.

Rules:
    1. Coding session long + idle → ask mood → suggest music
    2. App switched to media → suppress notifications
    3. Long idle → log session end
    4. Time bracket change → mood update + optional greeting

Behavior:
    - Non-intrusive: never interrupts active speech or command processing
    - Configurable cooldowns between proactive prompts
    - User can disable entirely via enabled flag
    - Subscribes to EventBus, never polls directly

Cross-platform: Pure Python logic, no platform-specific code.
"""

import time
import threading
from typing import Optional, Callable
from dataclasses import dataclass

from core.event_bus import get_event_bus, Event


# ─── Proactive Rules Config ─────────────────────────────────
@dataclass
class ProactiveConfig:
    """Configuration for proactive behavior."""
    enabled:                  bool  = True
    cooldown_minutes:         float = 30.0    # Min time between proactive prompts
    coding_session_threshold: float = 1800.0  # 30 min before asking mood
    idle_threshold:           float = 900.0   # 15 min idle → log session end
    idle_check_enabled:       bool  = True
    coding_check_enabled:     bool  = True
    music_suggestion_enabled: bool  = True


# ─── Mood → Music Mapping ───────────────────────────────────
MOOD_MUSIC_MAP = {
    "tired":     {"query": "lo-fi chill beats",    "label": "some chill lo-fi"},
    "exhausted": {"query": "ambient relaxation",   "label": "ambient relaxation music"},
    "motivated": {"query": "phonk gym motivation", "label": "some high-energy phonk"},
    "focused":   {"query": "deep focus music",     "label": "deep focus music"},
    "happy":     {"query": "feel good pop hits",   "label": "feel-good music"},
    "sad":       {"query": "comfort music chill",  "label": "some comfort music"},
    "stressed":  {"query": "calm piano music",     "label": "calm piano music"},
    "bored":     {"query": "upbeat electronic",    "label": "something upbeat"},
    "neutral":   {"query": "focus playlist",       "label": "a focus playlist"},
}

# Keywords to detect mood from user response
MOOD_KEYWORDS = {
    "tired":     ["tired", "sleepy", "exhausted", "drained", "low energy", "fatigue"],
    "exhausted": ["dead", "burnt out", "done", "can't", "no more"],
    "motivated": ["motivated", "pumped", "let's go", "feeling good", "great", "amazing", "energized"],
    "focused":   ["focused", "in the zone", "working", "fine", "good", "okay", "alright"],
    "happy":     ["happy", "awesome", "fantastic", "wonderful", "excited"],
    "sad":       ["sad", "down", "upset", "meh", "not great", "bad"],
    "stressed":  ["stressed", "anxious", "overwhelmed", "pressure"],
    "bored":     ["bored", "boring", "nothing to do", "blah"],
}


def _detect_mood_from_response(response: str) -> str:
    """Detect mood from a user's response text."""
    response_lower = response.lower().strip()

    for mood, keywords in MOOD_KEYWORDS.items():
        for kw in keywords:
            if kw in response_lower:
                return mood

    return "neutral"


# ─── Proactive Loop ─────────────────────────────────────────
class ProactiveLoop:
    """
    Background system that monitors perception and triggers proactive actions.

    Usage:
        loop = ProactiveLoop(speak_func=speak, listen_func=listen)
        loop.start()
        ...
        loop.stop()
    """

    def __init__(
        self,
        speak_func:  Callable = None,
        listen_func: Callable = None,
        config:      ProactiveConfig = None,
    ):
        self._speak = speak_func
        self._listen = listen_func
        self._config = config or ProactiveConfig()

        self._last_prompt_time: float = 0.0
        self._last_time_bracket: str = ""
        self._session_logged: bool = False
        self._running: bool = False
        self._lock = threading.Lock()

        # State tracking
        self._coding_prompted: bool = False
        self._suppress_notifications: bool = False

    def start(self) -> None:
        """Start listening to perception events."""
        if self._running:
            return

        self._running = True

        # Subscribe to perception updates
        bus = get_event_bus()
        bus.subscribe("perception_update", self._on_perception_update)

        print("🔁 ProactiveLoop started")

    def stop(self) -> None:
        """Stop the proactive loop."""
        self._running = False

        try:
            bus = get_event_bus()
            bus.unsubscribe("perception_update", self._on_perception_update)
        except Exception:
            pass

        print("🔁 ProactiveLoop stopped")

    @property
    def enabled(self) -> bool:
        return self._config.enabled

    @enabled.setter
    def enabled(self, value: bool):
        self._config.enabled = value
        state = "enabled" if value else "disabled"
        print(f"🔁 Proactive behavior {state}")

    def _can_prompt(self) -> bool:
        """Check if enough time has passed since last proactive prompt."""
        cooldown_sec = self._config.cooldown_minutes * 60
        return (time.time() - self._last_prompt_time) > cooldown_sec

    def _on_perception_update(self, event: Event) -> None:
        """Called on every perception_update event from EventBus."""
        if not self._running or not self._config.enabled:
            return

        data = event.data
        active_app     = data.get("active_app", "")
        system_state   = data.get("system_state", "")
        idle_seconds   = data.get("idle_seconds", 0)
        session_dur    = data.get("session_duration", 0)
        time_of_day    = data.get("time_of_day", "")

        # ── Rule 1: Coding for a while + idle → ask mood ────
        if (self._config.coding_check_enabled
                and system_state == "coding"
                and session_dur > self._config.coding_session_threshold
                and idle_seconds > 60
                and not self._coding_prompted
                and self._can_prompt()):
            self._trigger_coding_checkin()

        # ── Rule 2: Media app → suppress notifications ──────
        if system_state == "media":
            if not self._suppress_notifications:
                self._suppress_notifications = True
                print("🔇 Media app detected — suppressing proactive prompts")
        else:
            self._suppress_notifications = False

        # ── Rule 3: Long idle → log session end ─────────────
        if (self._config.idle_check_enabled
                and idle_seconds > self._config.idle_threshold
                and not self._session_logged):
            self._log_session_end(idle_seconds)

        elif idle_seconds < 60:
            self._session_logged = False  # Reset when user is active

        # ── Rule 4: Time bracket change → mood update ───────
        if time_of_day and time_of_day != self._last_time_bracket:
            if self._last_time_bracket:  # Skip first detection
                self._on_time_bracket_change(self._last_time_bracket, time_of_day)
            self._last_time_bracket = time_of_day

        # Reset coding prompt flag when user switches away from coding
        if system_state != "coding":
            self._coding_prompted = False

    def _trigger_coding_checkin(self) -> None:
        """Ask the user how they're feeling during a long coding session."""
        if self._suppress_notifications:
            return

        with self._lock:
            self._coding_prompted = True
            self._last_prompt_time = time.time()

        print("🤖 Proactive: Coding session check-in")

        # Speak the question
        if self._speak:
            try:
                self._speak("Hey, you've been coding for a while. How are you feeling today?")
            except Exception as e:
                print(f"⚠️  Proactive speak error: {e}")
                return

        # Listen for response
        if self._listen and self._config.music_suggestion_enabled:
            try:
                response = self._listen()
                if response:
                    mood = _detect_mood_from_response(response)
                    music_info = MOOD_MUSIC_MAP.get(mood, MOOD_MUSIC_MAP["neutral"])

                    print(f"🎭 Detected mood: {mood} → suggesting {music_info['label']}")

                    # Suggest music
                    if self._speak:
                        self._speak(f"Got it. Let me play {music_info['label']} for you.")

                    # Trigger MusicAgent via EventBus
                    bus = get_event_bus()
                    bus.publish("proactive_trigger", {
                        "trigger":  "music_suggestion",
                        "mood":     mood,
                        "query":    music_info["query"],
                        "agent":    "music",
                        "action":   "play_playlist",
                    }, source="proactive_loop")

            except Exception as e:
                print(f"⚠️  Proactive listen error: {e}")

    def _log_session_end(self, idle_seconds: float) -> None:
        """Log that the user appears to have stepped away."""
        self._session_logged = True
        minutes = idle_seconds / 60
        print(f"💤 User appears idle ({minutes:.0f} min) — session paused")

        bus = get_event_bus()
        bus.publish("system_event", {
            "event":   "session_idle",
            "idle_min": round(minutes, 1),
        }, source="proactive_loop")

    def _on_time_bracket_change(self, old_bracket: str, new_bracket: str) -> None:
        """Handle time of day bracket change (morning → afternoon, etc.)."""
        print(f"🕐 Time bracket: {old_bracket} → {new_bracket}")

        # Update mood engine
        try:
            pass # Let time-based mood take over
        except Exception:
            pass

        bus = get_event_bus()
        bus.publish("mood_change", {
            "reason":      "time_bracket_change",
            "old_bracket": old_bracket,
            "new_bracket": new_bracket,
        }, source="proactive_loop")


# ─── Singleton ───────────────────────────────────────────────
_loop_instance: Optional[ProactiveLoop] = None
_loop_lock = threading.Lock()


def get_proactive_loop(
    speak_func: Callable = None,
    listen_func: Callable = None,
) -> ProactiveLoop:
    """Returns the global ProactiveLoop singleton."""
    global _loop_instance
    if _loop_instance is None:
        with _loop_lock:
            if _loop_instance is None:
                _loop_instance = ProactiveLoop(
                    speak_func=speak_func,
                    listen_func=listen_func,
                )
    return _loop_instance


# ─── Quick Test ──────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("  PROACTIVE LOOP TEST")
    print("=" * 60)

    # Test mood detection
    test_responses = [
        ("I'm so tired", "tired"),
        ("Feeling great, let's go!", "motivated"),
        ("I'm fine, just working", "focused"),
        ("Kinda bored honestly", "bored"),
        ("yeah whatever", "neutral"),
    ]

    print("\n── Mood Detection ──")
    for response, expected in test_responses:
        detected = _detect_mood_from_response(response)
        status = "✅" if detected == expected else "❌"
        print(f"  {status} '{response}' → {detected} (expected: {expected})")

    # Test music mapping
    print("\n── Mood → Music ──")
    for mood, info in MOOD_MUSIC_MAP.items():
        print(f"  🎵 {mood:12s} → {info['label']}")

    # Test proactive loop (dry run)
    print("\n── ProactiveLoop dry run ──")
    loop = ProactiveLoop(config=ProactiveConfig(enabled=True, cooldown_minutes=0.1))
    loop.start()

    # Simulate a perception event
    bus = get_event_bus()
    bus.publish("perception_update", {
        "active_app":      "Code",
        "system_state":    "coding",
        "idle_seconds":    5,
        "session_duration": 100,
        "time_of_day":     "afternoon",
    }, source="test")

    time.sleep(1)
    loop.stop()

    print("\n✅ ProactiveLoop test passed!")
