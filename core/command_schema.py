"""
Strict structured command representation for the unified pipeline.

normalize → interpret → ground → choose action → execute → verify → learn
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Optional


@dataclass
class MachineContext:
    """Grounding snapshot passed into the interpreter (expand over time)."""

    active_app: str = ""
    active_window: str = ""
    idle_seconds: float = 0.0
    system_state: str = "unknown"
    last_file: Optional[str] = None
    recent_actions: list[str] = field(default_factory=list)
    browser_url: Optional[str] = None
    browser_title: Optional[str] = None
    visual_summary: Optional[str] = None  # OCR or vision caption; optional

    def to_prompt_block(self) -> str:
        lines = [
            f"active_app: {self.active_app or '(unknown)'}",
            f"active_window: {self.active_window or '(unknown)'}",
            f"idle_seconds: {self.idle_seconds:.1f}",
            f"system_state: {self.system_state}",
            f"last_file: {self.last_file or '(none)'}",
            f"recent_actions: {', '.join(self.recent_actions[-8:]) or '(none)'}",
            f"browser: {self.browser_title or '(no title)'} | {self.browser_url or '(no url)'}",
        ]
        if self.visual_summary:
            lines.append(f"visual_summary: {self.visual_summary[:2000]}")
        return "\n".join(lines)


@dataclass
class RequiredState:
    """
    Preconditions / postconditions in loose key-value form.
    Example keys: active_app_is, window_contains, path_exists
    """

    preconditions: dict[str, Any] = field(default_factory=dict)
    postconditions: dict[str, Any] = field(default_factory=dict)


@dataclass
class InterpretedCommand:
    """Single structured interpretation of a user utterance."""

    action: str
    target: Optional[str] = None
    params: dict[str, Any] = field(default_factory=dict)
    required_state: RequiredState = field(default_factory=RequiredState)
    confidence: float = 0.0
    ambiguities: list[str] = field(default_factory=list)
    natural_response: Optional[str] = None
    source: str = "unknown"  # e.g. fast_intent | llm_structured | learned
    target_type: Optional[str] = None  # Phase 1: app|file|folder|website|browser_search|tab|email|note|unknown

    def to_json(self) -> str:
        payload = asdict(self)
        return json.dumps(payload, indent=2, default=str)

    @classmethod
    def from_json(cls, raw: str) -> "InterpretedCommand":
        data = json.loads(raw)
        rs = data.pop("required_state", {}) or {}
        pre = rs.get("preconditions", {}) if isinstance(rs, dict) else {}
        post = rs.get("postconditions", {}) if isinstance(rs, dict) else {}
        data["required_state"] = RequiredState(
            preconditions=dict(pre) if isinstance(pre, Mapping) else {},
            postconditions=dict(post) if isinstance(post, Mapping) else {},
        )
        return cls(**data)

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "InterpretedCommand":
        d = dict(data)
        rs = d.pop("required_state", None)
        if isinstance(rs, RequiredState):
            req = rs
        elif isinstance(rs, Mapping):
            req = RequiredState(
                preconditions=dict(rs.get("preconditions", {}) or {}),
                postconditions=dict(rs.get("postconditions", {}) or {}),
            )
        else:
            req = RequiredState()
        return cls(required_state=req, **d)


@dataclass
class VerificationResult:
    """Outcome of comparing perception before vs after an action."""

    ok: bool
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)
