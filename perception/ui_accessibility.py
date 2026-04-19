"""
Accessibility tree summaries (AXUIElement on macOS, UI Automation on Windows).

Use this before screenshots: native structure is richer and cheaper than vision-only agents.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class AXNodeSummary:
    """Tiny serializable slice of an accessibility node."""

    role: str
    title: str
    value: Optional[str] = None
    children: Optional[List["AXNodeSummary"]] = None


def get_focused_element_tree_placeholder(max_depth: int = 4) -> Optional[AXNodeSummary]:
    """Wire to AXUIElement / UIAutomation; returns None until implemented."""
    return None


def tree_to_text(node: AXNodeSummary | None, depth: int = 0) -> str:
    """Flatten a small AX summary for LLM context."""
    if node is None:
        return ""
    pad = "  " * depth
    line = f"{pad}{node.role}: {node.title}"
    if node.value:
        line += f" = {node.value}"
    parts = [line]
    for ch in node.children or []:
        parts.append(tree_to_text(ch, depth + 1))
    return "\n".join(parts)
