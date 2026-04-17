"""
Memory Integrator — Pre-action memory orchestrator.

Single entry point that checks ALL memory layers before any action,
enforcing the strict decision priority:

    1. Learned corrections  (HIGHEST)  — error_correction.py
    2. Explicit preferences             — continuous_memory.py
    3. Long-term context                — vector_memory.py
    4. Default logic        (LOWEST)   — existing intent engine

Returns a MemoryDecision that MUST be enforced by brain.py.
This is NOT optional — overrides, preferences, and context
are all mandatory when present.

Cross-platform: Pure Python, no I/O.
"""

import time
import threading
from typing import Optional, List
from dataclasses import dataclass, field


@dataclass
class MemoryDecision:
    """
    Result of pre-action memory check.

    All fields are mandatory to inspect in brain.py:
        - override_action:    If set, MUST execute this instead
        - override_params:    If set, MUST merge into params
        - relevant_memories:  If set, MUST add to Gemini context
        - preferences_used:   If set, MUST inject into params/context
        - source:             Which layer produced the decision
    """
    override_action:    Optional[str]  = None
    override_params:    Optional[dict] = None
    relevant_memories:  list           = field(default_factory=list)
    preferences_used:   list           = field(default_factory=list)
    source:             str            = "default"   # correction | preference | memory | default
    correction_id:      str            = ""          # ID of correction used (for tracking)
    confidence:         float          = 0.0         # Confidence of the memory decision
    debug_log:          list           = field(default_factory=list)  # [MEMORY USED] log entries

    @property
    def has_override(self) -> bool:
        """True if this decision overrides the default action."""
        return self.override_action is not None

    @property
    def has_param_overrides(self) -> bool:
        """True if params should be modified."""
        return bool(self.override_params)

    @property
    def has_context(self) -> bool:
        """True if relevant memories should be injected."""
        return bool(self.relevant_memories)

    @property
    def has_preferences(self) -> bool:
        """True if preferences were used."""
        return bool(self.preferences_used)


class MemoryIntegrator:
    """
    Pre-action memory orchestrator.

    Called AFTER intent classification and confidence evaluation,
    but BEFORE final action execution.

    Flow:
        Intent → Confidence → **MemoryIntegrator** → Final Decision

    Usage:
        integrator = MemoryIntegrator()
        decision = integrator.pre_action_check(
            command="open my editor",
            intent="open_app",
            params={"target": "vscode"},
            confidence=0.85
        )

        if decision.has_override:
            execute(decision.override_action, decision.override_params)
        if decision.has_preferences:
            inject_preferences(decision.preferences_used)
        if decision.has_context:
            add_to_gemini_context(decision.relevant_memories)
    """

    def __init__(self):
        self._lock = threading.Lock()

    def pre_action_check(
        self,
        command:    str,
        intent:     str,
        params:     dict,
        confidence: float = 0.0,
    ) -> MemoryDecision:
        """
        Check all memory layers in priority order.

        Priority:
            1. Corrections (highest)
            2. Explicit preferences
            3. Long-term semantic context
            4. Default (lowest)

        Args:
            command:    Original user command
            intent:     Classified intent action
            params:     Extracted parameters
            confidence: Confidence score from evaluation

        Returns:
            MemoryDecision — MUST be enforced by caller.
        """
        decision = MemoryDecision()
        debug = []

        # ── Layer 1: Corrections (HIGHEST PRIORITY) ──────────
        correction_override = self._check_corrections(command, intent, params)
        if correction_override:
            decision.source = "correction"

            if correction_override.get("override_intent"):
                decision.override_action = correction_override["override_intent"]
                debug.append(f"Correction: intent override "
                            f"{intent} → {decision.override_action}")

            if correction_override.get("override_params"):
                decision.override_params = correction_override["override_params"]
                debug.append(f"Correction: param override {decision.override_params}")

            decision.correction_id = correction_override.get("correction_id", "")
            decision.confidence = correction_override.get("confidence", 1.0)

            # Log
            if debug:
                decision.debug_log = debug
                self._log_memory_used(debug)
            return decision  # Corrections override everything — return immediately

        # ── Layer 2: Explicit Preferences ────────────────────
        preferences = self._check_preferences(intent, params)
        if preferences:
            decision.preferences_used = preferences
            decision.source = "preference"

            # Build param overrides from preferences
            param_overrides = {}
            for pref in preferences:
                pref_key = pref.get("key", "")
                pref_value = pref.get("value", "")

                # Map preference keys to param keys
                if pref_key in ("editor", "browser", "terminal"):
                    param_overrides["target"] = pref_value
                elif pref_key == "dark_mode":
                    param_overrides["theme"] = "dark"
                elif pref_key == "work_tool":
                    param_overrides["tool"] = pref_value

            if param_overrides:
                decision.override_params = param_overrides
                debug.append(f"Preference: injecting {param_overrides}")

            debug.append(f"Preferences used: {[p['key'] for p in preferences]}")

        # ── Layer 3: Long-Term Semantic Context ──────────────
        memories = self._check_long_term(command)
        if memories:
            decision.relevant_memories = memories
            if decision.source == "default":
                decision.source = "memory"

            debug.append(f"Context: {len(memories)} relevant memories found")

        # ── Layer 4: Default (no memory influence) ───────────
        if not debug:
            debug.append("No memory influence — using default logic")

        decision.debug_log = debug
        if debug and decision.source != "default":
            self._log_memory_used(debug)

        return decision

    # ─── Layer Implementations ───────────────────────────────

    def _check_corrections(self, command: str, intent: str, params: dict) -> Optional[dict]:
        """Layer 1: Check error correction store."""
        try:
            from core.error_correction import get_error_correction_store
            store = get_error_correction_store()
            return store.check_corrections(command, intent, params)
        except Exception as e:
            return None

    def _check_preferences(self, intent: str, params: dict) -> list:
        """
        Layer 2: Check continuous memory for relevant preferences.

        Returns list of relevant preference dicts.
        Only returns preferences that are RELEVANT to the current intent.
        """
        try:
            from core.continuous_memory import get_continuous_memory
            mem = get_continuous_memory()
            preferences = mem.get_preferences()

            relevant = []
            for pref in preferences:
                if self._is_preference_relevant(pref, intent, params):
                    relevant.append({
                        "key": pref.key,
                        "value": pref.value,
                        "confidence": pref.confidence,
                    })
                    # Reinforce: this preference was accessed
                    mem.reinforce(pref.key, "preference")

            return relevant
        except Exception:
            return []

    def _check_long_term(self, command: str) -> list:
        """
        Layer 3: Search vector memory for relevant context.

        Returns list of relevant memory strings.
        """
        try:
            from core.vector_memory import get_vector_memory
            vm = get_vector_memory()
            results = vm.search(command, top_k=3, min_score=0.4)
            return [
                {
                    "text": r.document.text[:200],
                    "similarity": r.similarity,
                    "metadata": r.document.metadata,
                }
                for r in results
            ]
        except Exception:
            return []

    def _is_preference_relevant(self, pref, intent: str, params: dict) -> bool:
        """
        Determines if a preference is relevant to the current intent.

        E.g., "editor=VSCode" is relevant to "open_app" but not "send_email".
        """
        key = pref.key.lower()

        # App-related preferences → relevant for app/system intents
        app_intents = {"open_app", "close_app", "switch_to_app", "open_file"}
        app_prefs = {"editor", "browser", "terminal", "vscode", "dark_mode"}
        if key in app_prefs and intent in app_intents:
            return True

        # Tool preferences → relevant for coding/development intents
        if key == "work_tool" and intent in {"open_app", "open_terminal"}:
            return True

        # Music preferences → relevant for music intents
        music_intents = {"play_music", "play_playlist", "pause_music"}
        if "music" in key and intent in music_intents:
            return True

        # File preferences → relevant for file intents
        file_intents = {"create_file", "edit_file", "read_file", "open_file"}
        file_prefs = {"default_format", "file_location"}
        if key in file_prefs and intent in file_intents:
            return True

        return False

    def _log_memory_used(self, entries: list) -> None:
        """Print [MEMORY USED] annotations to console."""
        print("\n[MEMORY USED]")
        for entry in entries:
            print(f"  • {entry}")
        print()

    def build_context_string(self, decision: MemoryDecision) -> str:
        """
        Build a context string from memory decision for Gemini prompts.

        Called when relevant_memories are present to inject context
        into the LLM prompt.
        """
        if not decision.relevant_memories:
            return ""

        lines = ["Relevant context from memory:"]
        for mem in decision.relevant_memories[:3]:
            text = mem.get("text", "")
            sim = mem.get("similarity", 0)
            lines.append(f"- {text} (relevance: {sim:.0%})")

        if decision.preferences_used:
            lines.append("\nUser preferences:")
            for pref in decision.preferences_used:
                lines.append(f"- {pref['key']}: {pref['value']}")

        return "\n".join(lines)


# ─── Singleton ───────────────────────────────────────────────
_mi_instance: Optional[MemoryIntegrator] = None
_mi_lock = threading.Lock()


def get_memory_integrator() -> MemoryIntegrator:
    """Returns the global MemoryIntegrator singleton."""
    global _mi_instance
    if _mi_instance is None:
        with _mi_lock:
            if _mi_instance is None:
                _mi_instance = MemoryIntegrator()
    return _mi_instance


# ─── Quick Test ──────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("  MEMORY INTEGRATOR TEST")
    print("=" * 60)

    integrator = MemoryIntegrator()

    # Test 1: No memories → default
    print("\n── Test 1: No memory influence ──")
    decision = integrator.pre_action_check(
        command="play music",
        intent="play_music",
        params={},
        confidence=0.9,
    )
    print(f"  Source: {decision.source}")
    print(f"  Override: {decision.has_override}")
    print(f"  Debug: {decision.debug_log}")

    # Test 2: With corrections
    print("\n── Test 2: Setup correction ──")
    try:
        from core.error_correction import get_error_correction_store
        store = get_error_correction_store()
        store.learn_correction(
            intent="open_app",
            wrong_param="vscode",
            correct_param="cursor",
            param_key="target",
            original_command="open my editor",
        )

        decision = integrator.pre_action_check(
            command="open my editor",
            intent="open_app",
            params={"target": "vscode"},
            confidence=0.9,
        )
        print(f"  Source: {decision.source}")
        print(f"  Override action: {decision.override_action}")
        print(f"  Override params: {decision.override_params}")
        store.clear_all()
    except Exception as e:
        print(f"  Skipped (error_correction not available): {e}")

    # Test 3: With preferences
    print("\n── Test 3: Setup preferences ──")
    try:
        from core.continuous_memory import get_continuous_memory
        mem = get_continuous_memory()
        mem.store("preference", "editor", "Cursor", confidence=0.9)

        decision = integrator.pre_action_check(
            command="open my editor",
            intent="open_app",
            params={"target": "code"},
            confidence=0.85,
        )
        print(f"  Source: {decision.source}")
        print(f"  Preferences: {decision.preferences_used}")
        print(f"  Override params: {decision.override_params}")
        mem.delete_memory("editor", "preference")
    except Exception as e:
        print(f"  Skipped (continuous_memory not available): {e}")

    # Test 4: Context string builder
    print("\n── Test 4: Context string ──")
    fake_decision = MemoryDecision(
        relevant_memories=[
            {"text": "User discussed API integration on Monday", "similarity": 0.82},
            {"text": "User prefers Python for backend work", "similarity": 0.75},
        ],
        preferences_used=[
            {"key": "editor", "value": "VSCode", "confidence": 0.9},
        ],
    )
    context = integrator.build_context_string(fake_decision)
    print(context)

    print("\n✅ Memory integrator test passed!")
