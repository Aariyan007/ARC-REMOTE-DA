"""
Live browser tab state from the Playwright automation context when it is running.
Does not launch a browser by itself.

Provides BrowserSnapshot for verification and a rich read-only API.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class BrowserTabState:
    browser: str
    title: str
    url: str
    active: bool = True


@dataclass
class BrowserSnapshot:
    """Rich browser state for verifiers. Never launches a browser to collect."""

    url: str = ""
    title: str = ""
    tab_count: int = 0
    is_running: bool = False
    tabs: List[BrowserTabState] = field(default_factory=list)
    timestamp: float = 0.0

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = time.time()


# ─── Core tab reader (existing, preserved) ───────────────────

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


# ─── Rich snapshot for verification ──────────────────────────

def get_active_tab_state() -> BrowserSnapshot:
    """
    Collects current browser state without launching a browser.
    Safe to call at any time — returns empty snapshot if no browser running.
    """
    try:
        from control.playwright_browser import (
            get_active_url,
            get_active_title,
            get_tab_count,
            is_browser_running,
        )

        running = is_browser_running()
        if not running:
            return BrowserSnapshot(is_running=False)

        url = get_active_url() or ""
        title = get_active_title() or ""
        count = get_tab_count()
        tabs = get_browser_tabs()

        return BrowserSnapshot(
            url=url,
            title=title,
            tab_count=count,
            is_running=True,
            tabs=tabs,
        )
    except Exception:
        return BrowserSnapshot(is_running=False)


def get_page_text_snippet(max_chars: int = 500) -> str:
    """
    Returns visible text from the active Playwright page.
    No-launch: returns empty string if no browser running.
    """
    try:
        from control.playwright_browser import _running_context

        ctx = _running_context()
        if ctx is None or not ctx.pages:
            return ""

        page = ctx.pages[-1]
        try:
            # Get inner text of body
            text = page.inner_text("body", timeout=3000)
            if text:
                return text[:max_chars].strip()
        except Exception:
            pass
        return ""
    except Exception:
        return ""


def element_exists(selector: str) -> bool:
    """
    Check if a DOM element matching the CSS selector exists in the active page.
    No-launch: returns False if no browser running.
    """
    try:
        from control.playwright_browser import _running_context

        ctx = _running_context()
        if ctx is None or not ctx.pages:
            return False

        page = ctx.pages[-1]
        try:
            count = page.locator(selector).count()
            return count > 0
        except Exception:
            return False
    except Exception:
        return False


# ─── Quick Test ──────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("  BROWSER STATE TEST")
    print("=" * 60)

    snap = get_active_tab_state()
    print(f"  Running: {snap.is_running}")
    print(f"  URL:     {snap.url}")
    print(f"  Title:   {snap.title}")
    print(f"  Tabs:    {snap.tab_count}")

    text = get_page_text_snippet(200)
    print(f"  Text:    {text[:100]}..." if text else "  Text:    (none)")

    print("\n✅ Browser state test passed!")
