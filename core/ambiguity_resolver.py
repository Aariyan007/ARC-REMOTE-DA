"""
When confidence is medium, prefer a short clarification over a wrong guess.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from core.command_schema import InterpretedCommand


@dataclass
class DisambiguationPrompt:
    """One question the user can answer (voice or text)."""

    question: str
    options: list[str]


def should_disambiguate(
    cmd: InterpretedCommand,
    *,
    low: float = 0.40,
    high: float = 0.72,
) -> bool:
    """True if confidence sits in the 'uncertain' band or explicit ambiguities exist."""
    if cmd.ambiguities:
        return True
    return low <= cmd.confidence < high


def build_disambiguation_prompt(cmd: InterpretedCommand) -> Optional[DisambiguationPrompt]:
    """
    Produce a minimal clarification from structured fields.
    Extend with domain-specific templates as the schema grows.
    """
    action = (cmd.action or "").lower()
    target = (cmd.target or "").strip()

    if cmd.ambiguities:
        opts = []
        for line in cmd.ambiguities[:4]:
            if ":" in line:
                opts.append(line.split(":", 1)[-1].strip())
            else:
                opts.append(line.strip())
        opts = [o for o in opts if o] or ["cancel"]
        return DisambiguationPrompt(
            question="I need a quick clarification — which did you mean?",
            options=opts[:6],
        )

    if action in ("open_app", "switch_to_app") and target in (
        "chrome",
        "google chrome",
        "safari",
        "firefox",
        "edge",
        "brave",
    ):
        return DisambiguationPrompt(
            question=f"For {target}: open a new window, or switch to an existing one?",
            options=["open", "switch", "cancel"],
        )

    if action in ("open_app",) and not target:
        return DisambiguationPrompt(
            question="Which app should I open?",
            options=["cancel"],
        )

    return None
