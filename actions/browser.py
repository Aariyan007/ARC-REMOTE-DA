"""
Browser automation — Playwright-backed (see control.playwright_browser).
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

from control.playwright_browser import dispatch


class BrowserActionError(RuntimeError):
    pass


def dispatch_browser_action(action: str, params: Optional[Mapping[str, Any]] = None) -> Any:
    try:
        return dispatch(action, dict(params or {}))
    except ValueError as e:
        raise BrowserActionError(str(e)) from e
    except Exception as e:
        raise BrowserActionError(f"Browser action failed: {e}") from e
