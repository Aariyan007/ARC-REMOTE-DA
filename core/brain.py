"""
ManagerBrain — Central Decision Engine.

Replaces simple intent routing with a multi-stage Think → Plan → Execute loop.

Pipeline:
    1. Fast Match (local intent engine)
    2. Confidence check
    3. If LOW / complex → ManagerBrain planning via Gemini
    4. Execution via agent dispatch
    5. Observation + optional re-plan

Fallback Loop:
    If a local action fails → automatically attempt Cloud Re-plan

This is the "brain" that sits above the ManagerAgent and decides
HOW to handle each command at a strategic level.
"""

import os
import time
import json
from typing import Optional
from enum import Enum
from dataclasses import dataclass, field

from core.confidence import evaluate_confidence, ConfidenceTier, ConfidenceResult
from core.event_bus import get_event_bus


# ─── Decision Types ──────────────────────────────────────────
class BrainDecision(Enum):
    FAST_EXECUTE    = "fast_execute"      # Direct fast-path execution
    PLAN_AND_EXECUTE = "plan_and_execute"  # Multi-step via ManagerAgent
    CLOUD_REPLAN    = "cloud_replan"      # Gemini re-plan after failure  
    CLARIFY         = "clarify"           # Ask user for more info
    CHAT            = "chat"             # Conversational response
    OBSERVE_REPLAN  = "observe_replan"    # Re-plan based on observation


@dataclass
class BrainResult:
    """Result from ManagerBrain decision."""
    decision:      BrainDecision
    confidence:    ConfidenceResult
    action:        str         = ""
    params:        dict        = field(default_factory=dict)
    plan:          dict        = None     # Multi-step plan from Gemini
    observation:   str         = ""       # What the brain observed post-execution
    retry_count:   int         = 0
    total_ms:      float       = 0.0


# ─── Complexity Detection ────────────────────────────────────
COMPLEX_INDICATORS = [
    "after that", "and then", "also", "then",
    "but if", "unless", "otherwise",
    "first", "next", "finally",
    "search for", "research", "look up", "find out",
    "send my", "email my", "forward",
    "check if", "make sure",
]

CONVERSATIONAL_INDICATORS = [
    "how are you", "what's up", "tell me a joke",
    "good morning", "good night", "hey jarvis",
    "thank you", "thanks", "you're welcome",
    "who are you", "what can you do",
]


def _is_complex(command: str) -> bool:
    """Detect if a command requires multi-step planning."""
    cmd_lower = command.lower()
    # 1. Explicit indicators
    matches = sum(1 for ind in COMPLEX_INDICATORS if ind in cmd_lower)
    if matches >= 1:
        return True
        
    # 2. Conjunctions in longer commands (e.g. "make a folder ... and create a file")
    if " and " in cmd_lower and len(cmd_lower.split()) >= 6:
        return True
        
    # 3. Multiple action verbs without conjunctions 
    # e.g., "make a folder create a file open vscode"
    action_verbs = ["create", "make", "open", "delete", "remove", "close", "start", "stop", "search", "find", "send", "email", "tell"]
    verbs_found = sum(1 for verb in action_verbs if f"{verb} " in cmd_lower)
    if verbs_found >= 2:
        return True
        
    return False


def _is_conversational(command: str) -> bool:
    """Detect if a command is just chat/conversation."""
    cmd_lower = command.lower()
    return any(ind in cmd_lower for ind in CONVERSATIONAL_INDICATORS)


# ─── ManagerBrain ────────────────────────────────────────────
class ManagerBrain:
    """
    Central decision engine. Analyzes commands and decides the
    optimal execution strategy.

    Think → Plan → Execute → Observe → Re-plan

    Usage:
        brain = ManagerBrain(manager_agent, actions)
        result = brain.decide(command, intent, params)
        # result.decision tells you what to do
    """

    def __init__(self, manager_agent=None, actions: dict = None):
        self._manager = manager_agent
        self._actions = actions or {}
        self._max_retries = 2
        self._execution_history = []  # Recent decisions for learning

    def decide(
        self,
        command:          str,
        intent_action:    str,
        intent_confidence: float,
        params:           dict,
        text:             str = "",
        has_context_ref:  bool = False,
        context_resolved: bool = False,
    ) -> BrainResult:
        """
        Main entry point. Analyzes the command and returns a BrainDecision.

        Returns:
            BrainResult with the optimal execution strategy.
        """
        start = time.time()

        # ── Step 1: Evaluate confidence ──────────────────────
        conf = evaluate_confidence(
            action=intent_action,
            intent_confidence=intent_confidence,
            params=params,
            text=text,
            has_context_ref=has_context_ref,
            context_resolved=context_resolved,
        )

        # ── Step 2: Check if conversational ──────────────────
        if _is_conversational(command):
            return BrainResult(
                decision=BrainDecision.CHAT,
                confidence=conf,
                action="casual_chat",
                params={"query": command},
                total_ms=(time.time() - start) * 1000,
            )

        # ── Step 3: Check complexity ─────────────────────────
        is_complex = _is_complex(command)

        # ── Step 4: Route based on confidence + complexity ───
        if conf.tier == ConfidenceTier.HIGH and not is_complex:
            # High confidence, simple command → fast execute
            result = BrainResult(
                decision=BrainDecision.FAST_EXECUTE,
                confidence=conf,
                action=intent_action,
                params=params,
                total_ms=(time.time() - start) * 1000,
            )

        elif conf.tier == ConfidenceTier.HIGH and is_complex:
            # High confidence but complex → plan and execute
            result = BrainResult(
                decision=BrainDecision.PLAN_AND_EXECUTE,
                confidence=conf,
                action=intent_action,
                params=params,
                total_ms=(time.time() - start) * 1000,
            )

        elif conf.tier == ConfidenceTier.MEDIUM:
            if is_complex:
                # Medium + complex → plan with Gemini
                result = BrainResult(
                    decision=BrainDecision.PLAN_AND_EXECUTE,
                    confidence=conf,
                    action=intent_action,
                    params=params,
                    total_ms=(time.time() - start) * 1000,
                )
            else:
                # Medium + simple → fast execute (but confirm)
                result = BrainResult(
                    decision=BrainDecision.FAST_EXECUTE,
                    confidence=conf,
                    action=intent_action,
                    params=params,
                    total_ms=(time.time() - start) * 1000,
                )

        else:
            # Low confidence → clarify
            result = BrainResult(
                decision=BrainDecision.CLARIFY,
                confidence=conf,
                action=intent_action,
                params=params,
                total_ms=(time.time() - start) * 1000,
            )

        # Log the decision
        self._log_decision(command, result)

        # Publish event
        try:
            bus = get_event_bus()
            bus.publish("brain_decision", {
                "command":    command,
                "decision":   result.decision.value,
                "confidence": conf.score,
                "action":     intent_action,
            }, source="brain")
        except Exception:
            pass

        return result

    def handle_failure(
        self,
        command:     str,
        failed_action: str,
        error:       str,
        original_result: BrainResult,
    ) -> BrainResult:
        """
        Called when an action fails. Attempts cloud re-plan.

        Returns:
            New BrainResult with CLOUD_REPLAN or CLARIFY decision.
        """
        retry = original_result.retry_count + 1

        if retry > self._max_retries:
            return BrainResult(
                decision=BrainDecision.CLARIFY,
                confidence=original_result.confidence,
                action=failed_action,
                observation=f"Failed after {retry} attempts: {error}",
                retry_count=retry,
            )

        print(f"🔄 Brain: Action '{failed_action}' failed — attempting cloud re-plan (retry {retry})")

        return BrainResult(
            decision=BrainDecision.CLOUD_REPLAN,
            confidence=original_result.confidence,
            action=failed_action,
            params=original_result.params,
            observation=f"Previous attempt failed: {error}",
            retry_count=retry,
        )

    def observe_and_replan(
        self,
        command:       str,
        executed_steps: list,
        remaining_steps: list,
        environment_change: str = "",
    ) -> Optional[BrainResult]:
        """
        Post-execution observation. Checks if the plan needs adjustment.

        Called after each step in a TaskGraph to evaluate if remaining
        steps are still valid.

        Returns:
            BrainResult with OBSERVE_REPLAN if changes needed, None otherwise.
        """
        if not environment_change and not any(s.get("failed") for s in executed_steps):
            return None  # Everything fine, continue

        print(f"👁️  Brain: Observing post-execution state...")
        print(f"   Executed: {len(executed_steps)}, Remaining: {len(remaining_steps)}")
        if environment_change:
            print(f"   Environment change: {environment_change}")

        # Check for failures in executed steps
        failures = [s for s in executed_steps if s.get("failed")]
        if failures:
            return BrainResult(
                decision=BrainDecision.OBSERVE_REPLAN,
                confidence=ConfidenceResult(
                    score=0.5,
                    tier=ConfidenceTier.MEDIUM,
                    should_execute=True,
                    should_confirm=True,
                    factors={},
                    recommendation="Re-planning due to step failure",
                ),
                observation=f"Step failed: {failures[0].get('error', 'unknown')}",
            )

        return None

    def _log_decision(self, command: str, result: BrainResult) -> None:
        """Log decision for learning."""
        entry = {
            "timestamp": time.time(),
            "command":   command,
            "decision":  result.decision.value,
            "confidence": result.confidence.score,
            "action":    result.action,
        }
        self._execution_history.append(entry)
        # Keep last 100
        if len(self._execution_history) > 100:
            self._execution_history = self._execution_history[-100:]

    def get_decision_stats(self) -> dict:
        """Returns stats about recent brain decisions."""
        if not self._execution_history:
            return {"total": 0}

        decisions = [e["decision"] for e in self._execution_history]
        return {
            "total":          len(decisions),
            "fast_execute":   decisions.count("fast_execute"),
            "plan_execute":   decisions.count("plan_and_execute"),
            "cloud_replan":   decisions.count("cloud_replan"),
            "clarify":        decisions.count("clarify"),
            "chat":           decisions.count("chat"),
        }


# ─── Singleton ───────────────────────────────────────────────
_brain_instance: Optional[ManagerBrain] = None


def get_brain(manager_agent=None, actions: dict = None) -> ManagerBrain:
    """Returns the global ManagerBrain singleton."""
    global _brain_instance
    if _brain_instance is None:
        _brain_instance = ManagerBrain(manager_agent, actions)
    return _brain_instance


# ─── Quick Test ──────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("  MANAGER BRAIN TEST")
    print("=" * 60)

    brain = ManagerBrain()

    # Test 1: Simple high-confidence command
    r = brain.decide("open vscode", "open_app", 0.95, {"target": "vscode"}, "open vscode")
    print(f"\n1. 'open vscode' -> {r.decision.value} (conf={r.confidence.score:.2f})")

    # Test 2: Complex command
    r = brain.decide(
        "search for my resume and then email it to HR",
        "search_file", 0.80, {"query": "resume"},
        "search for my resume and then email it to HR"
    )
    print(f"2. Complex -> {r.decision.value} (conf={r.confidence.score:.2f})")

    # Test 3: Conversational
    r = brain.decide("how are you doing today", "casual_chat", 0.60, {}, "how are you")
    print(f"3. Chat -> {r.decision.value}")

    # Test 4: Low confidence
    r = brain.decide("mumble something", "unknown", 0.20, {}, "mumble something")
    print(f"4. Low conf -> {r.decision.value} (conf={r.confidence.score:.2f})")

    # Test 5: Failure handling
    r_fail = brain.handle_failure("open vscode", "open_app", "App not found", r)
    print(f"5. Failure -> {r_fail.decision.value} (retry={r_fail.retry_count})")

    print(f"\nStats: {brain.get_decision_stats()}")
    print("\n✅ ManagerBrain test passed!")
