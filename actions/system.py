"""
System-level actions (volume, brightness, tabs, etc.) — delegates to platform control modules.
"""

from __future__ import annotations

from typing import Any, Mapping

from core.platform_utils import is_mac, is_windows


def _controls_mod():
    if is_mac():
        import control.mac.system_controls as m

        return m
    if is_windows():
        import control.windows.system_controls as m

        return m
    raise NotImplementedError("Unsupported platform for system actions.")


def dispatch_system_action(action: str, params: Mapping[str, Any] | None = None) -> None:
    """
    Invoke a named system control. ``params`` may include ``amount``, ``app_name``, etc.
    Unknown actions raise AttributeError from getattr.
    """
    mod = _controls_mod()
    p = dict(params or {})
    fn = getattr(mod, action, None)
    if fn is None or not callable(fn):
        raise ValueError(f"Unknown system action: {action}")

    # Common arity patterns for this codebase
    if action in ("volume_up", "volume_down"):
        fn(int(p.get("amount", 10)))
        return
    if action in ("minimise_app", "close_app", "switch_to_app"):
        fn(str(p.get("app_name", p.get("target", ""))))
        return
    fn()
