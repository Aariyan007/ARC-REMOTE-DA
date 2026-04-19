"""
Filesystem actions — delegates to existing control/*/file_ops implementations.
"""

from __future__ import annotations

from typing import Any, Mapping

from core.platform import is_mac, is_windows


def _file_ops():
    if is_mac():
        import control.mac.file_ops as m

        return m
    if is_windows():
        import control.windows.file_ops as m

        return m
    raise NotImplementedError("Unsupported platform for filesystem actions.")


def dispatch_filesystem_action(action: str, params: Mapping[str, Any] | None = None) -> Any:
    """
    Pass-through to legacy file_ops functions. Extend with a single router table over time.
    """
    mod = _file_ops()
    fn = getattr(mod, action, None)
    if fn is None or not callable(fn):
        raise ValueError(f"Unknown filesystem action: {action}")
    p = dict(params or {})
    # Most file_ops APIs take positional names; callers should pack kwargs carefully.
    return fn(**p) if p else fn()
