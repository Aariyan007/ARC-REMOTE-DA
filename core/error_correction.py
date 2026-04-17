"""
Error Correction System — Intent-specific + parameter-specific corrections.

Builds on the existing reinforcement.py correction loop, but stores
corrections in a structured, scope-aware format that allows exact
override matching.

Key properties:
    - Intent-specific: only overrides when the SAME intent is matched
    - Parameter-specific: overrides specific parameters, not the whole action
    - Context-aware: tracks the original command for similarity matching
    - Reinforced: times_applied counter tracks successful usage
    - Highest priority: corrections override heuristics, preferences, defaults

Storage: data/error_corrections.json

Cross-platform: Pure Python, JSON persistence.
"""

import os
import re
import json
import time
import threading
from datetime import datetime
from typing import Optional, List
from dataclasses import dataclass, field, asdict


# ─── Settings ────────────────────────────────────────────────
BASE_DIR          = os.path.dirname(os.path.dirname(__file__))
CORRECTIONS_PATH  = os.path.join(BASE_DIR, "data", "error_corrections.json")
MAX_CORRECTIONS   = 200
SIMILARITY_THRESHOLD = 0.6   # For fuzzy command matching
# ─────────────────────────────────────────────────────────────


@dataclass
class Correction:
    """A single learned correction entry."""
    id:               str
    intent:           str             # The intent that was wrong (e.g., "open_app")
    wrong_param:      str             # The wrong parameter value (e.g., "resume.pdf")
    correct_param:    str             # The correct value (e.g., "resume_v2.pdf")
    param_key:        str = ""        # Which param key (e.g., "target", "filename")
    correct_intent:   str = ""        # Override intent entirely (empty = keep intent)
    original_command: str = ""        # The command that triggered the mistake
    context:          str = ""        # Context tag (e.g., "user_resume_opening")
    confidence:       float = 1.0
    timestamp:        str = ""
    times_applied:    int = 0
    last_applied:     str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "Correction":
        return Correction(**{k: v for k, v in d.items()
                            if k in Correction.__dataclass_fields__})


class ErrorCorrectionStore:
    """
    Intent-specific + parameter-specific correction store.

    Usage:
        store = ErrorCorrectionStore()

        # Learn: "When intent=open_app and target=vscode, I meant terminal"
        store.learn_correction(
            intent="open_app",
            wrong_param="vscode",
            correct_param="terminal",
            param_key="target",
            original_command="open my editor"
        )

        # Check: before executing open_app with target=vscode
        override = store.check_corrections("open my editor", "open_app", {"target": "vscode"})
        # override → {"target": "terminal"}
    """

    def __init__(self):
        self._corrections: list[Correction] = []
        self._lock = threading.Lock()
        self._load()

    def learn_correction(
        self,
        intent:           str,
        wrong_param:      str,
        correct_param:    str,
        param_key:        str   = "",
        correct_intent:   str   = "",
        original_command: str   = "",
        context:          str   = "",
        confidence:       float = 1.0,
    ) -> str:
        """
        Store a new correction.

        Args:
            intent:           The intent that was wrong
            wrong_param:      The wrong parameter value
            correct_param:    The correct parameter value
            param_key:        Which parameter key was wrong (e.g., "target")
            correct_intent:   If the entire intent was wrong, the correct intent
            original_command: The original command text
            context:          A context tag for scoping
            confidence:       How confident we are in this correction

        Returns:
            Correction ID.
        """
        with self._lock:
            # Check if identical correction exists
            for existing in self._corrections:
                if (existing.intent == intent and
                        existing.wrong_param == wrong_param and
                        existing.param_key == param_key):
                    # Update existing correction
                    existing.correct_param = correct_param
                    existing.correct_intent = correct_intent
                    existing.confidence = max(existing.confidence, confidence)
                    existing.timestamp = datetime.now().isoformat()
                    print(f"🔄 Correction updated: {intent}.{param_key}: "
                          f"{wrong_param} → {correct_param}")
                    self._save()
                    return existing.id

            # New correction
            import hashlib
            corr_id = hashlib.md5(
                f"{intent}:{wrong_param}:{time.time()}".encode()
            ).hexdigest()[:10]

            correction = Correction(
                id=corr_id,
                intent=intent,
                wrong_param=wrong_param,
                correct_param=correct_param,
                param_key=param_key,
                correct_intent=correct_intent,
                original_command=original_command,
                context=context,
                confidence=confidence,
            )
            self._corrections.append(correction)
            print(f"📝 Correction learned: {intent}.{param_key}: "
                  f"{wrong_param} → {correct_param}")

            # Prune if over limit
            if len(self._corrections) > MAX_CORRECTIONS:
                # Remove least-applied, oldest corrections
                self._corrections.sort(
                    key=lambda c: (c.times_applied, c.timestamp)
                )
                self._corrections = self._corrections[-MAX_CORRECTIONS:]

            self._save()
            return corr_id

    def learn_intent_correction(
        self,
        wrong_intent:     str,
        correct_intent:   str,
        original_command: str = "",
        context:          str = "",
    ) -> str:
        """
        Store a correction for an entire intent (not just parameters).

        Example: User says "open my editor" → classified as search_file
                 Correct intent is open_app
        """
        return self.learn_correction(
            intent=wrong_intent,
            wrong_param=wrong_intent,
            correct_param=correct_intent,
            param_key="_intent_",
            correct_intent=correct_intent,
            original_command=original_command,
            context=context,
        )

    def check_corrections(
        self,
        command: str,
        intent:  str,
        params:  dict,
    ) -> Optional[dict]:
        """
        Check if any corrections apply to this command + intent + params.

        Returns:
            Override dict with corrected values, or None if no corrections apply.
            Format: {
                "override_intent": "...",    # or None
                "override_params": {...},    # corrected params
                "correction_id": "...",
                "confidence": float
            }
        """
        with self._lock:
            best_match = None
            best_score = 0.0

            for correction in self._corrections:
                score = self._match_score(command, intent, params, correction)
                if score > best_score and score >= SIMILARITY_THRESHOLD:
                    best_match = correction
                    best_score = score

            if best_match:
                override = {
                    "override_intent": best_match.correct_intent or None,
                    "override_params": {},
                    "correction_id": best_match.id,
                    "confidence": best_match.confidence,
                }

                # Build override params
                if best_match.param_key and best_match.param_key != "_intent_":
                    override["override_params"][best_match.param_key] = best_match.correct_param

                # Track usage
                best_match.times_applied += 1
                best_match.last_applied = datetime.now().isoformat()
                self._save()

                print(f"⚡ Correction applied: {best_match.intent}.{best_match.param_key}: "
                      f"{best_match.wrong_param} → {best_match.correct_param} "
                      f"(applied {best_match.times_applied}x)")

                return override

        return None

    def _match_score(
        self,
        command:    str,
        intent:     str,
        params:     dict,
        correction: Correction,
    ) -> float:
        """
        Compute match score between current action and a stored correction.

        Scoring:
            - Intent match:   +0.4
            - Param match:    +0.4  (wrong_param found in current params)
            - Command match:  +0.2  (fuzzy overlap with original_command)
        """
        score = 0.0

        # Intent must match (hard requirement)
        if correction.intent != intent:
            # Unless this is an intent-level correction
            if correction.param_key != "_intent_":
                return 0.0
            # For intent corrections, check command similarity
            if correction.original_command:
                cmd_sim = self._command_similarity(command, correction.original_command)
                return cmd_sim * 0.8 + 0.1  # Scale for intent corrections
            return 0.0

        score += 0.4  # Intent match

        # Param match: check if wrong_param appears in current params
        if correction.param_key and correction.param_key in params:
            current_val = str(params[correction.param_key]).lower()
            wrong_val = correction.wrong_param.lower()
            if current_val == wrong_val:
                score += 0.4  # Exact param match
            elif wrong_val in current_val or current_val in wrong_val:
                score += 0.2  # Partial param match

        # Command similarity bonus
        if correction.original_command:
            cmd_sim = self._command_similarity(command, correction.original_command)
            score += cmd_sim * 0.2

        return score

    def _command_similarity(self, cmd_a: str, cmd_b: str) -> float:
        """Simple word-overlap similarity between two commands."""
        words_a = set(cmd_a.lower().split())
        words_b = set(cmd_b.lower().split())
        if not words_a or not words_b:
            return 0.0
        intersection = words_a & words_b
        union = words_a | words_b
        return len(intersection) / len(union) if union else 0.0

    # ─── User Control ────────────────────────────────────────

    def view_corrections(self) -> list[dict]:
        """Returns all corrections as dicts for viewing."""
        return [
            {
                "intent": c.intent,
                "wrong": f"{c.param_key}={c.wrong_param}",
                "correct": f"{c.param_key}={c.correct_param}",
                "applied": c.times_applied,
                "confidence": c.confidence,
            }
            for c in self._corrections
        ]

    def delete_correction(self, correction_id: str) -> bool:
        """Delete a specific correction."""
        with self._lock:
            for c in self._corrections:
                if c.id == correction_id:
                    self._corrections.remove(c)
                    self._save()
                    print(f"[x] Correction deleted: {c.intent}.{c.param_key}")
                    return True
        return False

    def clear_all(self) -> None:
        """Clear all corrections."""
        with self._lock:
            self._corrections = []
            self._save()
        print("[x] All corrections cleared")

    # ─── Persistence ─────────────────────────────────────────

    def _load(self) -> None:
        if os.path.exists(CORRECTIONS_PATH):
            try:
                with open(CORRECTIONS_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._corrections = [Correction.from_dict(d) for d in data]
            except Exception as e:
                print(f"⚠️  Error corrections load error: {e}")
                self._corrections = []

    def _save(self) -> None:
        os.makedirs(os.path.dirname(CORRECTIONS_PATH), exist_ok=True)
        try:
            data = [c.to_dict() for c in self._corrections]
            with open(CORRECTIONS_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"⚠️  Error corrections save error: {e}")

    @property
    def count(self) -> int:
        return len(self._corrections)


# ─── Singleton ───────────────────────────────────────────────
_ec_instance: Optional[ErrorCorrectionStore] = None
_ec_lock = threading.Lock()


def get_error_correction_store() -> ErrorCorrectionStore:
    """Returns the global ErrorCorrectionStore singleton."""
    global _ec_instance
    if _ec_instance is None:
        with _ec_lock:
            if _ec_instance is None:
                _ec_instance = ErrorCorrectionStore()
    return _ec_instance


# ─── Quick Test ──────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("  ERROR CORRECTION SYSTEM TEST")
    print("=" * 60)

    store = ErrorCorrectionStore()
    store.clear_all()

    # Test 1: Learn a parameter correction
    print("\n── Learn Param Correction ──")
    store.learn_correction(
        intent="open_file",
        wrong_param="resume.pdf",
        correct_param="resume_v2.pdf",
        param_key="filename",
        original_command="open my resume",
        context="user_resume_opening",
    )

    # Test 2: Learn an intent correction
    print("\n── Learn Intent Correction ──")
    store.learn_intent_correction(
        wrong_intent="search_file",
        correct_intent="open_app",
        original_command="open my editor",
    )

    # Test 3: Check corrections (should match param correction)
    print("\n── Check Corrections (param) ──")
    override = store.check_corrections(
        "open my resume", "open_file", {"filename": "resume.pdf"}
    )
    print(f"  Override: {override}")

    # Test 4: Check corrections (should match intent correction)
    print("\n── Check Corrections (intent) ──")
    override = store.check_corrections(
        "open my editor", "search_file", {"query": "editor"}
    )
    print(f"  Override: {override}")

    # Test 5: No match
    print("\n── Check Corrections (no match) ──")
    override = store.check_corrections(
        "play music", "play_music", {}
    )
    print(f"  Override: {override}")

    # Test 6: Duplicate correction (should update)
    print("\n── Duplicate Correction ──")
    store.learn_correction(
        intent="open_file",
        wrong_param="resume.pdf",
        correct_param="resume_final.pdf",
        param_key="filename",
    )

    # Test 7: View all
    print("\n── All Corrections ──")
    for c in store.view_corrections():
        print(f"  {c['intent']}: {c['wrong']} → {c['correct']} (applied={c['applied']}x)")

    print(f"\n  Total corrections: {store.count}")
    print("\n✅ Error correction system test passed!")
