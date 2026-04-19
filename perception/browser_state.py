"""
Live browser tab state from the Playwright automation context when it is running.
Does not launch a browser by itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass
class BrowserTabState:
    browser: str
    title: str
    url: str
    active: bool = True


def get_browser_tabs() -> List[BrowserTabState]:
    from control.playwright_browser import get_tabs

    out: List[BrowserTabState] = []
    for row in get_tabs():
        out.append(
            BrowserTabState(
                browser="playwright",
                title=row.get("title") or "",
                url=row.get("url") or "",
                active=bool(row.get("active")),
            )
        )
    return out


def get_browser_tabs_placeholder() -> List[BrowserTabState]:
    """Alias for older imports — returns live tabs when Playwright is active."""
    return get_browser_tabs()
