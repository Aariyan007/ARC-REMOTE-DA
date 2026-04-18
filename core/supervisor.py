"""
Supervisor — Real-time self-learning auditor.

Runs during the session (every N commands) to:
1. Review recent interactions from WorkingMemory
2. Detect misalignments in real-time
3. Push corrections to error_corrections and intent_patches
4. Unlike Retrospective (which runs on startup for yesterday),
   Supervisor runs LIVE and fixes problems within the same session.

This is the "always-on conscience" of Jarvis.
"""

import os
import json
import time
from datetime import datetime
from typing import Optional

from dotenv import load_dotenv
load_dotenv()


# ── Settings ─────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(__file__))
PATCHES_PATH = os.path.join(BASE_DIR, "data", "intent_patches.json")
REVIEW_INTERVAL = 10       # Review every N commands
CONFIDENCE_FLOOR = 0.45    # Below this = definitely suspicious
# ─────────────────────────────────────────────────────────────


class Supervisor:
    """
    Real-time learning supervisor.

    Usage:
        supervisor = Supervisor()
        # After each command:
        supervisor.observe(command, action, confidence, source, result)
        # Internally decides when to audit
    """

    def __init__(self):
        self._observations = []  # Recent interactions buffer
        self._corrections_applied = 0
        self._session_start = datetime.now().isoformat()
        self._client = None

    def _get_client(self):
        """Lazy-load Gemini client."""
        if self._client is None:
            from google import genai
            self._client = genai.Client(api_key=os.getenv("API_KEY"))
        return self._client

    def observe(self, command: str, action: str, confidence: float,
                source: str, result: str = "", error: str = ""):
        """
        Record an observation. Called after each command execution.
        Automatically triggers audit when buffer is full.
        """
        self._observations.append({
            "command": command,
            "action": action,
            "confidence": confidence,
            "source": source,
            "result": result,
            "error": error,
            "timestamp": datetime.now().isoformat(),
        })

        # Immediate flag: very low confidence or error
        if confidence < CONFIDENCE_FLOOR and source == "builtin":
            self._flag_suspicious(self._observations[-1])

        # Periodic audit
        if len(self._observations) >= REVIEW_INTERVAL:
            self._audit_batch()

    def _flag_suspicious(self, obs: dict):
        """Immediately flag a suspicious interaction for review."""
        print(f"[Supervisor] Flagged: \"{obs['command'][:40]}\" "
              f"-> {obs['action']} (conf={obs['confidence']:.2f})")

        # Ask Gemini what the correct action should be
        correct = self._ask_correct_intent(obs["command"])
        if correct and correct != obs["action"]:
            self._apply_live_correction(
                command=obs["command"],
                wrong_action=obs["action"],
                correct_action=correct,
            )

    def _audit_batch(self):
        """Review the recent batch of observations for patterns."""
        if not self._observations:
            return

        # Pattern 1: Repeated commands with different actions
        for i in range(1, len(self._observations)):
            curr = self._observations[i]
            prev = self._observations[i - 1]

            # Word overlap check
            curr_words = set(curr["command"].lower().split())
            prev_words = set(prev["command"].lower().split())
            if not curr_words or not prev_words:
                continue

            overlap = len(curr_words & prev_words) / len(curr_words | prev_words)

            if overlap > 0.5 and curr["action"] != prev["action"]:
                # User repeated — first attempt was probably wrong
                print(f"[Supervisor] Repetition detected: "
                      f"\"{prev['command'][:30]}\" -> {prev['action']} "
                      f"then {curr['action']}")

                # The second attempt is usually more correct
                self._apply_live_correction(
                    command=prev["command"],
                    wrong_action=prev["action"],
                    correct_action=curr["action"],
                )

        # Pattern 2: All low-confidence actions (batch check)
        low_conf = [o for o in self._observations
                    if o["confidence"] < 0.50 and o["source"] == "builtin"]
        if len(low_conf) > 3:
            print(f"[Supervisor] Warning: {len(low_conf)}/{len(self._observations)} "
                  f"commands had low confidence. Intent engine may need more training data.")

        # Clear buffer
        self._observations.clear()

    def _ask_correct_intent(self, command: str) -> Optional[str]:
        """Ask Gemini for the correct intent classification."""
        try:
            client = self._get_client()

            from core.retrospective import VALID_ACTIONS
            actions_list = ", ".join(sorted(VALID_ACTIONS))

            prompt = f"""You are an intent classifier for a voice assistant.

Given this user command: "{command}"

What is the correct intent/action from this list?
{actions_list}

Return ONLY the action name, nothing else."""

            response = client.models.generate_content(
                model="gemini-3.1-flash-lite-preview",
                contents=prompt,
            )

            action = response.text.strip().lower().replace('"', '').replace("'", "")
            action = action.split('\n')[0].strip()
            action = action.split(' ')[0].strip() if ' ' in action else action

            if action in VALID_ACTIONS:
                return action
            return None

        except Exception as e:
            print(f"[Supervisor] Gemini query failed: {e}")
            return None

    def _apply_live_correction(self, command: str, wrong_action: str,
                                correct_action: str):
        """Apply a correction immediately to intent_patches.json."""
        # Generate examples from the command
        from core.retrospective import RetrospectiveEngine
        engine = RetrospectiveEngine()
        examples = engine._generalize_command(command, correct_action)

        # Load existing patches
        patches = {"generated": "", "patches": [], "negative_examples": []}
        if os.path.exists(PATCHES_PATH):
            try:
                with open(PATCHES_PATH, "r", encoding="utf-8") as f:
                    patches = json.load(f)
            except Exception:
                pass

        patches["generated"] = datetime.now().strftime("%Y-%m-%d")

        # Find or create patch for this action
        existing_patch = None
        for p in patches.get("patches", []):
            if p.get("action") == correct_action:
                existing_patch = p
                break

        if existing_patch:
            existing_set = set(existing_patch.get("add_examples", []))
            new_examples = [e for e in examples if e not in existing_set]
            existing_patch["add_examples"].extend(new_examples)
        else:
            patches["patches"].append({
                "action": correct_action,
                "add_examples": examples,
                "source": "supervisor_live",
                "from_command": command,
                "was_misrouted_as": wrong_action,
            })

        # Add negative example
        if wrong_action:
            patches.setdefault("negative_examples", []).append({
                "action": wrong_action,
                "text": command,
                "correct_action": correct_action,
            })

        # Save
        os.makedirs(os.path.dirname(PATCHES_PATH), exist_ok=True)
        with open(PATCHES_PATH, "w", encoding="utf-8") as f:
            json.dump(patches, f, indent=2, ensure_ascii=False)

        self._corrections_applied += 1
        print(f"[Supervisor] LIVE FIX: {wrong_action} -> {correct_action} "
              f"for \"{command[:40]}\" "
              f"(+{len(examples)} examples)")

        # Also store in error corrections for immediate override
        try:
            from core.error_correction import get_error_correction_store
            store = get_error_correction_store()
            store.learn_intent_correction(
                wrong_intent=wrong_action,
                correct_intent=correct_action,
                original_command=command,
                context="supervisor_live",
            )
        except Exception:
            pass

    def get_stats(self) -> dict:
        """Return supervisor statistics for this session."""
        return {
            "session_start": self._session_start,
            "observations": len(self._observations),
            "corrections_applied": self._corrections_applied,
        }

    def flush(self):
        """Force audit of remaining observations (call at session end)."""
        if self._observations:
            self._audit_batch()


# ── Singleton ────────────────────────────────────────────────
_supervisor = None

def get_supervisor() -> Supervisor:
    """Get or create the singleton Supervisor."""
    global _supervisor
    if _supervisor is None:
        _supervisor = Supervisor()
    return _supervisor


# ── Quick Test ───────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 50)
    print("  SUPERVISOR TEST")
    print("=" * 50)

    sup = Supervisor()

    # Simulate observations
    sup.observe("open chrome", "open_app", 0.85, "builtin", "Opened Chrome")
    sup.observe("what is on my screen", "brightness_up", 0.42, "builtin", "Brightness up")
    sup.observe("no what is on my screen", "take_screenshot", 0.78, "gemini", "Screenshot taken")

    print(f"\nStats: {sup.get_stats()}")
    print("Done.")
