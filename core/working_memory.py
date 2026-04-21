"""
Working Memory — Short-term execution journal.

Maintains the last 5–10 actions with full context for:
    - Explainability: "Why did you do that?"
    - Re-evaluation: check if action succeeded
    - Session awareness: "What have you been doing?"
    - Failure tracking: error + recovery_action fields

Entries auto-expire (deque capped at 10).
Publishes working_memory_update to EventBus.

Cross-platform: Pure Python, no persistence (session-only).
"""

import time
import threading
from collections import deque
from datetime import datetime
from typing import Optional, List
from dataclasses import dataclass, asdict


# ─── Settings ────────────────────────────────────────────────
MAX_ENTRIES = 10
# ─────────────────────────────────────────────────────────────


@dataclass
class WorkingMemoryEntry:
    """A single action entry in working memory."""
    action:          str              # e.g., "open_app"
    params:          dict             # e.g., {"target": "vscode"}
    reason:          str              # e.g., "User said 'open vscode'"
    timestamp:       str              # ISO format
    outcome:         str              # "success" | "failed" | "pending"
    confidence:      float  = 0.0    # Confidence score at decision time
    error:           str    = ""     # Error message if failed
    recovery_action: str    = ""     # What recovery was attempted
    command:         str    = ""     # Original user command
    intent_source:   str    = ""     # "builtin" | "learned" | "gemini"

    def to_dict(self) -> dict:
        return asdict(self)


class WorkingMemory:
    """
    Short-term execution journal.

    Usage:
        wm = WorkingMemory()
        wm.record_action("open_app", {"target": "vscode"}, "User said open vscode", "success")
        wm.get_last_action()  # → WorkingMemoryEntry
        wm.get_recent_actions(5)  # → list of entries
    """

    def __init__(self, max_entries: int = MAX_ENTRIES):
        self._entries: deque = deque(maxlen=max_entries)
        self._lock = threading.Lock()
        self._grounding: dict = {}  # Phase 1: grounding context signals

    def record_action(
        self,
        action:          str,
        params:          dict  = None,
        reason:          str   = "",
        outcome:         str   = "success",
        confidence:      float = 0.0,
        error:           str   = "",
        recovery_action: str   = "",
        command:         str   = "",
        intent_source:   str   = "",
    ) -> WorkingMemoryEntry:
        """
        Record an action in working memory.

        Args:
            action:          The action name (e.g., "open_app")
            params:          Parameters used
            reason:          Why this action was taken
            outcome:         "success" | "failed" | "pending"
            confidence:      Decision confidence
            error:           Error message if failed
            recovery_action: What recovery was attempted (if any)
            command:         Original user command
            intent_source:   How the intent was resolved

        Returns:
            The created WorkingMemoryEntry.
        """
        entry = WorkingMemoryEntry(
            action=action,
            params=params or {},
            reason=reason,
            timestamp=datetime.now().isoformat(),
            outcome=outcome,
            confidence=confidence,
            error=error,
            recovery_action=recovery_action,
            command=command,
            intent_source=intent_source,
        )

        with self._lock:
            self._entries.append(entry)

        # Publish to EventBus
        self._publish_update(entry)

        return entry

    def record_failure(
        self,
        action:          str,
        params:          dict  = None,
        error:           str   = "",
        recovery_action: str   = "",
        command:         str   = "",
        confidence:      float = 0.0,
    ) -> WorkingMemoryEntry:
        """Convenience: record a failed action with error and recovery."""
        return self.record_action(
            action=action,
            params=params,
            reason=f"Attempted {action} but failed",
            outcome="failed",
            confidence=confidence,
            error=error,
            recovery_action=recovery_action,
            command=command,
        )

    def get_last_action(self) -> Optional[WorkingMemoryEntry]:
        """Returns the most recent action entry."""
        with self._lock:
            if self._entries:
                return self._entries[-1]
        return None

    def get_recent_actions(self, n: int = 5) -> List[WorkingMemoryEntry]:
        """Returns the last N action entries (newest first)."""
        with self._lock:
            entries = list(self._entries)
        return list(reversed(entries[-n:]))

    def get_failures(self) -> List[WorkingMemoryEntry]:
        """Returns all failed actions in current session."""
        with self._lock:
            return [e for e in self._entries if e.outcome == "failed"]

    def summarize_session(self) -> str:
        """
        Returns a human-readable session summary.
        Used for "What have you been doing?" queries.
        """
        with self._lock:
            entries = list(self._entries)

        if not entries:
            return "No actions taken this session."

        lines = [f"Session summary — {len(entries)} actions:"]
        for i, entry in enumerate(entries, 1):
            status = "✅" if entry.outcome == "success" else "❌"
            line = f"  {i}. {status} {entry.action}"
            if entry.params:
                # Show key params
                key_params = {k: v for k, v in entry.params.items()
                             if not k.startswith("_")}
                if key_params:
                    line += f" ({', '.join(f'{k}={v}' for k, v in key_params.items())})"
            if entry.error:
                line += f" — Error: {entry.error}"
            if entry.recovery_action:
                line += f" → Recovery: {entry.recovery_action}"
            lines.append(line)

        # Stats
        successes = sum(1 for e in entries if e.outcome == "success")
        failures = sum(1 for e in entries if e.outcome == "failed")
        lines.append(f"\n  Results: {successes} succeeded, {failures} failed")

        return "\n".join(lines)

    def explain_last(self) -> str:
        """Explain the last action — 'Why did you do that?'"""
        last = self.get_last_action()
        if not last:
            return "I haven't done anything yet."

        explanation = f"I {last.action}"
        if last.params:
            key_params = {k: v for k, v in last.params.items()
                         if not k.startswith("_")}
            if key_params:
                explanation += f" with {key_params}"

        if last.reason:
            explanation += f" because {last.reason}"

        explanation += f" (confidence: {last.confidence:.0%})"

        if last.outcome == "failed":
            explanation += f". But it failed: {last.error}"
            if last.recovery_action:
                explanation += f". I tried to recover by: {last.recovery_action}"

        return explanation

    def clear(self) -> None:
        """Clear all entries."""
        with self._lock:
            self._entries.clear()
        print("[x] Working memory cleared")

    def _publish_update(self, entry: WorkingMemoryEntry) -> None:
        """Publish a working_memory_update event to EventBus."""
        try:
            from core.event_bus import get_event_bus
            bus = get_event_bus()
            bus.publish("working_memory_update", {
                "action":     entry.action,
                "outcome":    entry.outcome,
                "confidence": entry.confidence,
                "error":      entry.error,
            }, source="working_memory")
        except Exception:
            pass  # EventBus not initialized — skip silently

    @property
    def count(self) -> int:
        return len(self._entries)

    # ── Phase 1: Grounding Context Layer ─────────────────────
    # Accumulates contextual state beyond action entries for
    # resolving "it", "that", "again", "this file", "that tab".

    def update_grounding(
        self,
        *,
        last_file: Optional[str] = None,
        last_action: Optional[str] = None,
        last_browser_url: Optional[str] = None,
        last_browser_title: Optional[str] = None,
    ) -> None:
        """Update grounding signals after an action completes."""
        with self._lock:
            if last_file is not None:
                self._grounding["last_file"] = last_file
            if last_action is not None:
                self._grounding["last_action"] = last_action
            if last_browser_url is not None:
                self._grounding["last_browser_url"] = last_browser_url
            if last_browser_title is not None:
                self._grounding["last_browser_title"] = last_browser_title

    def get_grounding_context(self) -> dict:
        """
        Returns all grounding signals for context resolution.

        Used by the intent router to resolve references like:
        - "it" / "that" → last action target
        - "this file" → last_file
        - "that tab" → last_browser_title
        - "again" → last action (for replay)
        """
        with self._lock:
            ctx = dict(self._grounding)

        # Also pull from the last action entry
        last = self.get_last_action()
        if last:
            ctx.setdefault("last_action", last.action)
            ctx.setdefault("last_action_target",
                           last.params.get("target",
                           last.params.get("name",
                           last.params.get("filename",
                           last.params.get("query", "")))))
            ctx["last_action_command"] = last.command
            ctx["last_action_params"] = last.params

        return ctx

    def resolve_reference(self, word: str) -> Optional[str]:
        """
        Resolve a context reference word to a concrete value.

        Supports:
            "it", "that"       → last action target
            "this file"        → last_file
            "that tab"         → last_browser_title
            "again"            → last action command (for replay)

        Returns the resolved value, or None if not grounded.
        """
        ctx = self.get_grounding_context()
        word_lower = word.lower().strip()

        # Pronouns → last action target
        if word_lower in {"it", "that", "this", "them", "this one", "that one",
                          "this thing", "that thing"}:
            return ctx.get("last_action_target") or ctx.get("last_file")

        # File references
        if word_lower in {"this file", "that file", "the file"}:
            return ctx.get("last_file")

        # App references → still resolve to last file/target (best effort)
        if word_lower in {"this app", "that app", "the app"}:
            return ctx.get("last_action_target") or ctx.get("last_file")

        # Folder references
        if word_lower in {"this folder", "that folder", "the folder"}:
            return ctx.get("last_action_target") or ctx.get("last_file")

        # Tab references
        if word_lower in {"this tab", "that tab", "the tab", "current tab"}:
            return ctx.get("last_browser_title")

        # Replay
        if word_lower in {"again", "that again", "do that again", "repeat"}:
            return ctx.get("last_action_command")

        return None


# ─── Singleton ───────────────────────────────────────────────
_wm_instance: Optional[WorkingMemory] = None
_wm_lock = threading.Lock()


def get_working_memory() -> WorkingMemory:
    """Returns the global WorkingMemory singleton."""
    global _wm_instance
    if _wm_instance is None:
        with _wm_lock:
            if _wm_instance is None:
                _wm_instance = WorkingMemory()
    return _wm_instance


# ─── Quick Test ──────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("  WORKING MEMORY TEST")
    print("=" * 60)

    wm = WorkingMemory()

    # Test 1: Record successful actions
    print("\n── Record Actions ──")
    wm.record_action(
        "open_app", {"target": "vscode"}, "User said 'open vscode'",
        "success", confidence=0.95, command="open vscode", intent_source="builtin"
    )
    wm.record_action(
        "search_google", {"query": "Python docs"}, "User asked to search",
        "success", confidence=0.88, command="search python docs"
    )

    # Test 2: Record failure with recovery
    print("\n── Record Failure ──")
    wm.record_failure(
        "open_app", {"target": "unknown_app"},
        error="App not found: unknown_app",
        recovery_action="Suggested similar apps",
        command="open that thing",
        confidence=0.45,
    )

    # Test 3: Get last action
    print("\n── Last Action ──")
    last = wm.get_last_action()
    print(f"  Last: {last.action} — {last.outcome}")

    # Test 4: Explain
    print("\n── Explain ──")
    print(f"  {wm.explain_last()}")

    # Test 5: Session summary
    print("\n── Session Summary ──")
    print(wm.summarize_session())

    # Test 6: Get failures
    print("\n── Failures ──")
    failures = wm.get_failures()
    print(f"  {len(failures)} failure(s)")
    for f in failures:
        print(f"    ❌ {f.action}: {f.error}")

    # Test 7: Recent actions
    print("\n── Recent (2) ──")
    for entry in wm.get_recent_actions(2):
        print(f"  {entry.action} → {entry.outcome}")

    # Test 8: Auto-expire (fill beyond max)
    print("\n── Auto-Expire (adding 15 entries to 10-cap deque) ──")
    for i in range(15):
        wm.record_action(f"action_{i}", {}, f"Test action {i}", "success")
    print(f"  Count: {wm.count} (should be 10)")

    # ── Phase 1: Grounding Context Tests ─────────────────────
    print("\n── Grounding Context ──")
    wm2 = WorkingMemory()
    wm2.record_action(
        "create_file", {"filename": "notes.txt", "target": "notes.txt"},
        "User said create file", "success", confidence=0.95,
        command="create a file called notes", intent_source="builtin"
    )
    wm2.update_grounding(last_file="notes.txt", last_action="create_file")

    ctx = wm2.get_grounding_context()
    print(f"  last_file: {ctx.get('last_file')}")
    print(f"  last_action: {ctx.get('last_action')}")
    print(f"  last_action_target: {ctx.get('last_action_target')}")

    resolved = wm2.resolve_reference("it")
    print(f"  resolve 'it' → '{resolved}'")
    assert resolved == "notes.txt", f"Expected 'notes.txt', got '{resolved}'"

    resolved = wm2.resolve_reference("this file")
    print(f"  resolve 'this file' → '{resolved}'")
    assert resolved == "notes.txt"

    # Browser grounding
    wm2.update_grounding(last_browser_title="GitHub", last_browser_url="https://github.com")
    resolved = wm2.resolve_reference("that tab")
    print(f"  resolve 'that tab' → '{resolved}'")
    assert resolved == "GitHub"

    print("  ✅ Grounding context tests passed")

    wm.clear()
    print(f"  After clear: {wm.count}")
    print("\n✅ Working memory test passed!")

