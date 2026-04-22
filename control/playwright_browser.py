"""
Playwright-backed browser automation (DOM-first).

Uses Google Chrome when available (`channel="chrome"`), else bundled Chromium.
Install browsers once: `playwright install chrome` or `playwright install chromium`
"""

from __future__ import annotations

import atexit
import os
import re
import threading
from typing import Any, Dict, List, Optional
from urllib.parse import quote, urlparse

_lock = threading.RLock()
_pw = None
_browser = None
_context = None


def _headless() -> bool:
    return os.environ.get("STARTUP_PLAYWRIGHT_HEADLESS", "").lower() in ("1", "true", "yes")


def _shutdown() -> None:
    global _pw, _browser, _context
    with _lock:
        try:
            if _context:
                _context.close()
        except Exception:
            pass
        try:
            if _browser:
                _browser.close()
        except Exception:
            pass
        try:
            if _pw:
                _pw.stop()
        except Exception:
            pass
        _context = None
        _browser = None
        _pw = None


atexit.register(_shutdown)


def _running_context():
    """Return the live BrowserContext if Playwright is already running, else None (no launch)."""
    with _lock:
        if _context is None or _browser is None:
            return None
        try:
            if not _browser.is_connected():
                return None
        except Exception:
            return None
        return _context


def _ensure_browser():
    """Start Playwright + browser + context on first automation call."""
    global _pw, _browser, _context
    with _lock:
        ctx = _running_context()
        if ctx is not None:
            return ctx

        from playwright.sync_api import sync_playwright

        _pw = sync_playwright().start()
        launch_kwargs: Dict[str, Any] = {
            "headless": _headless(),
        }
        try:
            _browser = _pw.chromium.launch(channel="chrome", **launch_kwargs)
        except Exception:
            _browser = _pw.chromium.launch(**launch_kwargs)

        _context = _browser.new_context(
            viewport={"width": 1280, "height": 800},
            ignore_https_errors=True,
        )
        page = _context.new_page()
        page.set_default_timeout(30_000)
        return _context


def active_page():
    """Focused page: last page in context."""
    ctx = _ensure_browser()
    if not ctx.pages:
        p = ctx.new_page()
        p.set_default_timeout(30_000)
        return p
    return ctx.pages[-1]


def _normalize_url(url: str) -> str:
    u = (url or "").strip()
    if not u:
        raise ValueError("Empty URL")
    low = u.lower()
    if low.startswith("javascript:"):
        raise ValueError("Blocked URL scheme")
    if not re.match(r"^https?://", low, re.I):
        u = "https://" + u.lstrip("/")
    parsed = urlparse(u)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Only http/https URLs are allowed")
    return u


def navigate(url: str) -> str:
    u = _normalize_url(url)
    page = active_page()
    page.goto(u, wait_until="domcontentloaded")
    return page.url


def new_tab(url: Optional[str] = None) -> str:
    ctx = _ensure_browser()
    page = ctx.new_page()
    page.set_default_timeout(30_000)
    if url:
        page.goto(_normalize_url(url), wait_until="domcontentloaded")
    else:
        page.goto("about:blank")
    return page.url


def close_tab() -> None:
    page = active_page()
    ctx = page.context
    if len(ctx.pages) <= 1:
        page.goto("about:blank")
        return
    page.close()


def go_back() -> None:
    active_page().go_back()


def refresh() -> None:
    active_page().reload()


def get_tabs() -> List[Dict[str, Any]]:
    """Tab list for perception / LLM context. Does not start the browser."""
    ctx = _running_context()
    if ctx is None:
        return []
    out: List[Dict[str, Any]] = []
    for i, p in enumerate(ctx.pages):
        try:
            title = p.title() or ""
        except Exception:
            title = ""
        try:
            url = p.url or ""
        except Exception:
            url = ""
        out.append(
            {
                "index": i,
                "title": title,
                "url": url,
                "active": i == len(ctx.pages) - 1,
            }
        )
    return out


def search_google_in_browser(query: str) -> str:
    """Open Google search results in the automation browser."""
    q = (query or "").strip()
    if not q:
        raise ValueError("Empty search query")
    url = "https://www.google.com/search?q=" + quote(q, safe="")
    return navigate(url)


# ─── Read-only query methods (no-launch, safe) ──────────────

def is_browser_running() -> bool:
    """Check if a Playwright browser context is actively running."""
    return _running_context() is not None


def get_active_url() -> Optional[str]:
    """Returns the URL of the active tab, or None if no browser running."""
    ctx = _running_context()
    if ctx is None or not ctx.pages:
        return None
    try:
        return ctx.pages[-1].url
    except Exception:
        return None


def get_active_title() -> Optional[str]:
    """Returns the title of the active tab, or None if no browser running."""
    ctx = _running_context()
    if ctx is None or not ctx.pages:
        return None
    try:
        return ctx.pages[-1].title()
    except Exception:
        return None


def get_tab_count() -> int:
    """Returns the number of open tabs, or 0 if no browser running."""
    ctx = _running_context()
    if ctx is None:
        return 0
    try:
        return len(ctx.pages)
    except Exception:
        return 0


# ─── Structured dispatch ────────────────────────────────────

def dispatch(action: str, params: Optional[Dict[str, Any]] = None) -> Any:
    """Structured entry used by actions.browser."""
    p = dict(params or {})
    a = (action or "").strip().lower()
    if a in ("navigate", "open_url", "goto"):
        return navigate(str(p.get("url") or p.get("target") or ""))
    if a in ("new_tab", "open_new_tab"):
        return new_tab(p.get("url"))
    if a in ("close_tab", "close_page"):
        close_tab()
        return True
    if a in ("back", "go_back"):
        go_back()
        return True
    if a in ("refresh", "reload"):
        refresh()
        return True
    if a in ("search", "search_google"):
        return search_google_in_browser(str(p.get("query") or p.get("q") or ""))
    raise ValueError(f"Unknown browser action: {action}")


# ── Zero-arg shims for main.ACTIONS generic dispatch ─────────
def action_web_back() -> None:
    go_back()


def action_web_refresh() -> None:
    refresh()


def action_web_new_tab() -> None:
    new_tab(None)


def action_web_close_tab() -> None:
    close_tab()
