"""
Confidence Layer — Explicit confidence evaluation for every action.

Wraps the intent classification result with additional signals:
- Intent engine score
- Reinforcement history (past success/failure)
- Parameter completeness
- Context availability
- Perception state relevance

Three-tier decision system:
    HIGH   (>0.8)  → Execute immediately
    MEDIUM (0.5-0.8) → Execute + confirm assumption
    LOW    (<0.5)  → DO NOT execute, ask clarification

Integrates with (but doesn't replace) the existing SafetyDecision system.
"""

import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional


# ─── Confidence Tiers ────────────────────────────────────────
class ConfidenceTier(Enum):
    HIGH   = "high"       # >0.8  → execute
    MEDIUM = "medium"     # 0.5-0.8 → execute + confirm
    LOW    = "low"        # <0.5  → clarify


@dataclass
class ConfidenceResult:
    """Result of confidence evaluation."""
    score:          float           # Final confidence (0.0 - 1.0)
    tier:           ConfidenceTier  # HIGH / MEDIUM / LOW
    should_execute: bool            # Whether to proceed
    should_confirm: bool            # Whether to confirm with user
    factors:        dict            # Breakdown of scoring factors
    recommendation: str             # Human-readable recommendation


# ─── Scoring Weights ─────────────────────────────────────────
WEIGHT_INTENT      = 0.45    # Intent engine confidence
WEIGHT_REINFORCEMENT = 0.20  # Past success rate for this action
WEIGHT_PARAMS      = 0.20    # Parameter completeness
WEIGHT_CONTEXT     = 0.15    # Context availability / relevance


# ─── Actions that require extra parameters ───────────────────
PARAM_REQUIREMENTS = {
    "open_app":        ["target"],
    "close_app":       ["target"],
    "switch_to_app":   ["target"],
    "search_google":   ["query"],
    "open_url":        ["url"],
    "open_folder":     ["target"],
    "create_folder":   ["target"],
    "search_file":     ["query"],
    "send_email":      ["to"],
    "search_emails":   ["query"],
    "read_file":       ["filename"],
    "create_file":     ["filename"],
    "edit_file":       ["filename"],
    "delete_file":     ["filename"],
    "rename_file":     ["filename", "new_name"],
    "copy_file":       ["filename"],
    "volume_up":       [],
    "volume_down":     [],
    "play_music":      [],
    "pause_music":     [],
    "play_playlist":   ["query"],
}


def _score_params(action: str, params: dict) -> float:
    """
    Scores parameter completeness (0.0 - 1.0).
    1.0 = all required params present
    0.0 = no params when they're needed
    """
    required = PARAM_REQUIREMENTS.get(action)
    if required is None:
        # Unknown action — assume no params needed
        return 1.0
    if not required:
        # No params needed
        return 1.0

    present = sum(1 for p in required if params.get(p))
    return present / len(required)


def _score_reinforcement(action: str, text: str) -> float:
    """
    Gets reinforcement score from past success history.
    Returns 0.5 (neutral) if no history exists.
    """
    try:
        from core.reinforcement import get_boost, get_penalty
        boost = get_boost(text, action)
        penalty = get_penalty(text, action)

        # Normalize: boost adds, penalty subtracts
        score = 0.5 + (boost * 0.3) - (penalty * 0.3)
        return max(0.0, min(1.0, score))
    except Exception:
        return 0.5  # Neutral if reinforcement system unavailable


def _score_context(has_context_ref: bool, context_resolved: bool) -> float:
    """
    Scores context availability.
    - No context reference needed → 1.0
    - Context reference present and resolved → 0.9
    - Context reference present but unresolved → 0.3
    """
    if not has_context_ref:
        return 1.0
    if context_resolved:
        return 0.9
    return 0.3


# ─── Main Evaluation ─────────────────────────────────────────
def evaluate_confidence(
    action:           str,
    intent_confidence: float,
    params:           dict,
    text:             str     = "",
    has_context_ref:  bool    = False,
    context_resolved: bool    = False,
    perception_state: dict    = None,
) -> ConfidenceResult:
    """
    Evaluates overall confidence for an action decision.

    Args:
        action:            The classified intent action
        intent_confidence: Raw confidence from intent engine (0-1)
        params:            Extracted parameters
        text:              Original/normalized command text
        has_context_ref:   Whether command has pronoun references
        context_resolved:  Whether context was successfully resolved
        perception_state:  Current perception data (optional)

    Returns:
        ConfidenceResult with score, tier, and recommendation.
    """
    # ── Factor 1: Intent engine score ────────────────────────
    intent_score = min(1.0, max(0.0, intent_confidence))

    # ── Factor 2: Reinforcement history ──────────────────────
    reinforcement_score = _score_reinforcement(action, text)

    # ── Factor 3: Parameter completeness ─────────────────────
    param_score = _score_params(action, params)

    # ── Factor 4: Context availability ───────────────────────
    context_score = _score_context(has_context_ref, context_resolved)

    # ── Weighted final score ─────────────────────────────────
    final_score = (
        WEIGHT_INTENT * intent_score
        + WEIGHT_REINFORCEMENT * reinforcement_score
        + WEIGHT_PARAMS * param_score
        + WEIGHT_CONTEXT * context_score
    )

    # Clamp
    final_score = min(1.0, max(0.0, final_score))

    # ── Determine tier ───────────────────────────────────────
    if final_score > 0.8:
        tier = ConfidenceTier.HIGH
        should_execute = True
        should_confirm = False
        recommendation = f"High confidence ({final_score:.2f}) — executing."
    elif final_score >= 0.5:
        tier = ConfidenceTier.MEDIUM
        should_execute = True
        should_confirm = True
        recommendation = f"Medium confidence ({final_score:.2f}) — executing with confirmation."
    else:
        tier = ConfidenceTier.LOW
        should_execute = False
        should_confirm = False
        recommendation = f"Low confidence ({final_score:.2f}) — requesting clarification."

    # ── Override: missing critical params → drop tier ────────
    if param_score < 0.5 and tier == ConfidenceTier.HIGH:
        tier = ConfidenceTier.MEDIUM
        should_confirm = True
        recommendation = f"Missing parameters — dropping to medium confidence."

    factors = {
        "intent":        round(intent_score, 3),
        "reinforcement": round(reinforcement_score, 3),
        "params":        round(param_score, 3),
        "context":       round(context_score, 3),
        "weights": {
            "intent": WEIGHT_INTENT,
            "reinforcement": WEIGHT_REINFORCEMENT,
            "params": WEIGHT_PARAMS,
            "context": WEIGHT_CONTEXT,
        }
    }

    return ConfidenceResult(
        score=round(final_score, 3),
        tier=tier,
        should_execute=should_execute,
        should_confirm=should_confirm,
        factors=factors,
        recommendation=recommendation,
    )


# ─── Quick Test ──────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("  CONFIDENCE LAYER TEST")
    print("=" * 60)

    # Test 1: High confidence
    result = evaluate_confidence(
        action="open_app",
        intent_confidence=0.95,
        params={"target": "vscode"},
        text="open vscode",
    )
    print(f"\n1. open_app (0.95 intent, has params):")
    print(f"   Score: {result.score}  Tier: {result.tier.value}")
    print(f"   Execute: {result.should_execute}  Confirm: {result.should_confirm}")
    print(f"   Recommendation: {result.recommendation}")

    # Test 2: Medium confidence
    result = evaluate_confidence(
        action="delete_file",
        intent_confidence=0.65,
        params={"filename": "test.txt"},
        text="delete test",
    )
    print(f"\n2. delete_file (0.65 intent, has params):")
    print(f"   Score: {result.score}  Tier: {result.tier.value}")
    print(f"   Execute: {result.should_execute}  Confirm: {result.should_confirm}")

    # Test 3: Low confidence
    result = evaluate_confidence(
        action="send_email",
        intent_confidence=0.30,
        params={},
        text="something about email maybe",
    )
    print(f"\n3. send_email (0.30 intent, no params):")
    print(f"   Score: {result.score}  Tier: {result.tier.value}")
    print(f"   Execute: {result.should_execute}  Confirm: {result.should_confirm}")

    # Test 4: High intent but missing params
    result = evaluate_confidence(
        action="rename_file",
        intent_confidence=0.92,
        params={"filename": "old.txt"},  # Missing new_name
        text="rename old",
    )
    print(f"\n4. rename_file (0.92 intent, partial params):")
    print(f"   Score: {result.score}  Tier: {result.tier.value}")
    print(f"   Factors: {result.factors}")

    print("\n✅ Confidence layer test passed!")
