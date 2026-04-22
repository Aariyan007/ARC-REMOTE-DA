"""
Command Models — the canonical data types for the text-command pipeline.

Every input to the system arrives as a CommandRequest.
Every output leaves as a CommandResponse.
Voice (speak) is an optional side effect, never the primary output.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, List, Optional


# ─── Execution status enum ────────────────────────────────────

class ExecutionStatus(str, Enum):
    QUEUED             = "queued"
    RUNNING            = "running"
    NEEDS_CONFIRMATION = "needs_confirmation"   # ambiguous — caller must resolve
    COMPLETED          = "completed"
    FAILED             = "failed"
    CANCELLED          = "cancelled"


# ─── Per-step result ──────────────────────────────────────────

@dataclass
class StepResult:
    """Result of one step in a multi-step command."""
    step_id: int
    action: str
    status: str                          # done | failed | skipped
    summary: str = ""
    error: str = ""
    data: dict = field(default_factory=dict)
    verified: bool = False


# ─── Request ──────────────────────────────────────────────────

@dataclass
class CommandRequest:
    """
    Canonical input to the command pipeline.
    Created by every entry point (voice, API, local UI, phone).
    """
    text: str
    source: str = "voice"               # voice | api | phone | local_ui
    user: str = "aariyan"
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    session_id: Optional[str] = None    # groups related requests


# ─── Response ─────────────────────────────────────────────────

@dataclass
class CommandResponse:
    """
    Canonical output from the command pipeline.
    Always returned — even from voice commands.
    Callers decide whether to speak, log, or return as JSON.
    """
    request_id: str
    status: ExecutionStatus
    interpreted_action: str
    final_result: str                   # human-readable one-liner
    steps: List[StepResult] = field(default_factory=list)
    data: dict = field(default_factory=dict)    # machine-readable output
    errors: List[str] = field(default_factory=list)
    elapsed_ms: float = 0.0
    source: str = "voice"

    # ── Convenience constructors ──────────────────────────────

    @staticmethod
    def ok(
        request_id: str,
        action: str,
        result: str,
        *,
        data: dict = None,
        steps: List[StepResult] = None,
        elapsed_ms: float = 0.0,
        source: str = "voice",
    ) -> "CommandResponse":
        return CommandResponse(
            request_id=request_id,
            status=ExecutionStatus.COMPLETED,
            interpreted_action=action,
            final_result=result,
            steps=steps or [],
            data=data or {},
            elapsed_ms=elapsed_ms,
            source=source,
        )

    @staticmethod
    def fail(
        request_id: str,
        action: str,
        error: str,
        *,
        steps: List[StepResult] = None,
        elapsed_ms: float = 0.0,
        source: str = "voice",
    ) -> "CommandResponse":
        return CommandResponse(
            request_id=request_id,
            status=ExecutionStatus.FAILED,
            interpreted_action=action,
            final_result=error,
            errors=[error],
            steps=steps or [],
            elapsed_ms=elapsed_ms,
            source=source,
        )

    @staticmethod
    def needs_confirmation(
        request_id: str,
        action: str,
        message: str,
        *,
        data: dict = None,
        source: str = "voice",
    ) -> "CommandResponse":
        return CommandResponse(
            request_id=request_id,
            status=ExecutionStatus.NEEDS_CONFIRMATION,
            interpreted_action=action,
            final_result=message,
            data=data or {},
            source=source,
        )

    def to_dict(self) -> dict:
        return {
            "request_id":          self.request_id,
            "status":              self.status.value,
            "interpreted_action":  self.interpreted_action,
            "final_result":        self.final_result,
            "steps":               [
                {
                    "step_id":  s.step_id,
                    "action":   s.action,
                    "status":   s.status,
                    "summary":  s.summary,
                    "error":    s.error,
                    "data":     s.data,
                    "verified": s.verified,
                }
                for s in self.steps
            ],
            "data":                self.data,
            "errors":              self.errors,
            "elapsed_ms":          self.elapsed_ms,
            "source":              self.source,
        }
