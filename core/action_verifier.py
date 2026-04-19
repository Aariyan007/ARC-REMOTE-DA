"""
Compare perception (or other probes) before and after executing an action.
Native / DOM signals first; vision or OCR only when needed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Optional

from core.command_schema import VerificationResult

if TYPE_CHECKING:
    from core.perception_engine import PerceptionState


@dataclass
class ExpectedDelta:
    """What should change after a successful action (any subset may be set)."""

    active_app_contains: Optional[str] = None
    window_title_contains: Optional[str] = None
    active_app_not_equals: Optional[str] = None


def _norm(s: str) -> str:
    return (s or "").strip().lower()


def verify_perception_delta(
    before: "PerceptionState",
    after: "PerceptionState",
    expected: ExpectedDelta,
) -> VerificationResult:
    """
    Heuristic check using coarse perception_engine fields.
    Tighten with accessibility / browser_state when available.
    """
    details: dict[str, Any] = {
        "before_app": getattr(before, "active_app", ""),
        "after_app": getattr(after, "active_app", ""),
        "before_window": getattr(before, "active_window", ""),
        "after_window": getattr(after, "active_window", ""),
    }

    if expected.active_app_not_equals:
        want = _norm(expected.active_app_not_equals)
        if want and _norm(getattr(before, "active_app", "")) == _norm(getattr(after, "active_app", "")):
            return VerificationResult(
                ok=False,
                message="Expected foreground app to change.",
                details=details,
            )

    if expected.active_app_contains:
        needle = _norm(expected.active_app_contains)
        hay = _norm(getattr(after, "active_app", ""))
        if needle and needle not in hay:
            return VerificationResult(
                ok=False,
                message=f"Expected active app to match '{expected.active_app_contains}'.",
                details=details,
            )

    if expected.window_title_contains:
        needle = _norm(expected.window_title_contains)
        hay = _norm(getattr(after, "active_window", ""))
        if needle and needle not in hay:
            return VerificationResult(
                ok=False,
                message=f"Expected window title to contain '{expected.window_title_contains}'.",
                details=details,
            )

    return VerificationResult(ok=True, message="State consistent with expectations.", details=details)


@dataclass
class VerificationPolicy:
    """Hook for stricter checks later (timeouts, retries, AX tree equality)."""

    max_wait_seconds: float = 2.0
    extra: dict[str, Any] = field(default_factory=dict)
