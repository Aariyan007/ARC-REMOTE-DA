"""
Window operations — maps to system_controls where possible; extend for tiling / multi-monitor.
"""

from __future__ import annotations

from typing import Any, Mapping

from actions.system import dispatch_system_action


def dispatch_window_action(action: str, params: Mapping[str, Any] | None = None) -> None:
    p = dict(params or {})
    if action in ("close_window", "fullscreen", "mission_control", "minimise_all", "show_desktop"):
        dispatch_system_action(action, p)
        return
    if action == "minimise_app":
        dispatch_system_action(
            "minimise_app",
            {"app_name": p.get("app_name", p.get("target", ""))},
        )
        return
    raise ValueError(f"Unknown window action: {action}")
