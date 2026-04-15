"""
Event Bus — Central pub/sub communication for all agents.

All agents and engines communicate through the EventBus instead of
direct coupling. This enables loose architecture where any component
can react to events from any other component.

Event Types:
    perception_update  — PerceptionEngine polled new state
    mood_change        — Mood engine changed mood
    proactive_trigger  — Proactive loop wants to interact
    research_complete  — ResearchAgent finished a search
    agent_result       — Any agent completed an action
    command_received   — A new voice command was received
    system_event       — System-level events (startup, shutdown)

Usage:
    bus = get_event_bus()
    bus.subscribe("perception_update", my_callback)
    bus.publish("perception_update", {"active_app": "VSCode"})
"""

import threading
import time
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Any, Optional
from dataclasses import dataclass, field


# ─── Event Data ──────────────────────────────────────────────
@dataclass
class Event:
    """A single event in the system."""
    event_type:  str                       # e.g., "perception_update"
    data:        dict  = field(default_factory=dict)
    source:      str   = ""                # Who published it
    timestamp:   float = 0.0               # Auto-set on publish

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = time.time()


# ─── Event Bus ───────────────────────────────────────────────
class EventBus:
    """
    Thread-safe publish/subscribe event system.

    - subscribe(event_type, callback) — register a listener
    - publish(event_type, data, source) — fire an event
    - unsubscribe(event_type, callback) — remove a listener
    - Async dispatch: callbacks run in thread pool, never blocking publisher
    - Event history: last 100 events stored for debugging
    """

    def __init__(self, max_history: int = 100, max_workers: int = 2):
        self._subscribers: dict[str, list[Callable]] = defaultdict(list)
        self._lock = threading.Lock()
        self._history: deque = deque(maxlen=max_history)
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="jarvis_bus"
        )
        self._enabled = True

    def subscribe(self, event_type: str, callback: Callable) -> None:
        """
        Register a callback for an event type.

        Args:
            event_type: The event to listen for (e.g., "perception_update")
            callback:   Function(event: Event) → None
        """
        with self._lock:
            if callback not in self._subscribers[event_type]:
                self._subscribers[event_type].append(callback)

    def unsubscribe(self, event_type: str, callback: Callable) -> None:
        """Remove a callback from an event type."""
        with self._lock:
            if callback in self._subscribers[event_type]:
                self._subscribers[event_type].remove(callback)

    def publish(self, event_type: str, data: dict = None, source: str = "") -> None:
        """
        Publish an event. All subscribers are notified asynchronously.

        Args:
            event_type: The event type string
            data:       Dict of event payload
            source:     Name of the publisher (for debugging)
        """
        if not self._enabled:
            return

        event = Event(
            event_type=event_type,
            data=data or {},
            source=source,
        )

        # Store in history
        self._history.append(event)

        # Get subscribers snapshot (thread-safe)
        with self._lock:
            callbacks = list(self._subscribers.get(event_type, []))

        # Dispatch to all subscribers asynchronously
        for cb in callbacks:
            self._executor.submit(self._safe_dispatch, cb, event)

    def _safe_dispatch(self, callback: Callable, event: Event) -> None:
        """Safely calls a subscriber callback, catching errors."""
        try:
            callback(event)
        except Exception as e:
            print(f"⚠️  EventBus dispatch error [{event.event_type}]: {e}")

    def get_history(self, event_type: str = None, limit: int = 20) -> list:
        """
        Returns recent event history, optionally filtered by type.
        """
        events = list(self._history)
        if event_type:
            events = [e for e in events if e.event_type == event_type]
        return events[-limit:]

    def clear_history(self) -> None:
        """Clears the event history buffer."""
        self._history.clear()

    def enable(self) -> None:
        """Enable event publishing."""
        self._enabled = True

    def disable(self) -> None:
        """Disable event publishing (silences all events)."""
        self._enabled = False

    @property
    def subscriber_count(self) -> dict:
        """Returns count of subscribers per event type."""
        with self._lock:
            return {k: len(v) for k, v in self._subscribers.items() if v}

    def shutdown(self) -> None:
        """Clean shutdown of the event bus thread pool."""
        self._enabled = False
        self._executor.shutdown(wait=False)
        print("🔄 EventBus shut down")


# ─── Singleton ───────────────────────────────────────────────
_bus_instance: Optional[EventBus] = None
_bus_lock = threading.Lock()


def get_event_bus() -> EventBus:
    """Returns the global EventBus singleton."""
    global _bus_instance
    if _bus_instance is None:
        with _bus_lock:
            if _bus_instance is None:
                _bus_instance = EventBus()
    return _bus_instance


# ─── Quick Test ──────────────────────────────────────────────
if __name__ == "__main__":
    import time

    print("=" * 60)
    print("  EVENT BUS TEST")
    print("=" * 60)

    bus = get_event_bus()
    received = []

    def on_perception(event: Event):
        received.append(event)
        print(f"  📡 Received: {event.event_type} → {event.data}")

    def on_mood(event: Event):
        received.append(event)
        print(f"  🎭 Mood changed: {event.data}")

    bus.subscribe("perception_update", on_perception)
    bus.subscribe("mood_change", on_mood)

    print(f"\nSubscribers: {bus.subscriber_count}")

    # Publish events
    bus.publish("perception_update", {"active_app": "VSCode", "idle_sec": 5}, source="perception")
    bus.publish("mood_change", {"mood": "focused"}, source="mood_engine")
    bus.publish("perception_update", {"active_app": "Chrome", "idle_sec": 0}, source="perception")

    time.sleep(0.5)  # Wait for async dispatch

    print(f"\nReceived {len(received)} events")
    print(f"History: {len(bus.get_history())} total, {len(bus.get_history('perception_update'))} perception")

    bus.shutdown()
    print("\n✅ EventBus test passed!")
