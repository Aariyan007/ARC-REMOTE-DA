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
_owner_thread_id = None


def _headless() -> bool:
    return os.environ.get("STARTUP_PLAYWRIGHT_HEADLESS", "").lower() in ("1", "true", "yes")


def _shutdown() -> None:
    global _pw, _browser, _context, _owner_thread_id
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
        _owner_thread_id = None


atexit.register(_shutdown)


def _running_context():
    """Return the live BrowserContext if Playwright is already running, else None (no launch)."""
    global _owner_thread_id
    with _lock:
        if _context is None:
            return None
        
        # If the thread that created the Playwright instance has changed or exited,
        # Playwright's sync_api will crash. We must detect this.
        if _owner_thread_id != threading.get_ident():
            print(f"  ⚠️ Playwright thread mismatch (Owner: {_owner_thread_id}, Current: {threading.get_ident()}). Restarting...")
            return None

        try:
            # Check if there are any pages to verify it's still alive
            _ = _context.pages
        except Exception:
            return None
        return _context


def _ensure_browser():
    """Start Playwright + browser + context on first automation call."""
    global _pw, _browser, _context, _owner_thread_id
    with _lock:
        ctx = _running_context()
        if ctx is not None:
            return ctx

        # If we got here, either it's not started or the thread changed.
        # Clean up old dead references first.
        if _pw:
            try: _shutdown()
            except: pass

        from playwright.sync_api import sync_playwright

        print(f"  🚀 Starting Playwright in thread {threading.get_ident()}...")
        _pw = sync_playwright().start()
        _owner_thread_id = threading.get_ident()
        
        # Use a persistent profile so logins (like Gmail) are saved across runs
        profile_dir = os.path.expanduser("~/.friend/chrome_profile")
        os.makedirs(profile_dir, exist_ok=True)

        launch_kwargs: Dict[str, Any] = {
            "headless": _headless(),
            "viewport": {"width": 1280, "height": 800},
            "ignore_https_errors": True,
            "args": ["--disable-blink-features=AutomationControlled"],
        }
        
        try:
            # First try local Chrome installation
            _context = _pw.chromium.launch_persistent_context(
                user_data_dir=profile_dir,
                channel="chrome",
                **launch_kwargs
            )
        except Exception as e:
            print(f"  ⚠️ Chrome launch failed, falling back to bundled Chromium: {e}")
            # Fallback to Playwright's bundled Chromium
            _context = _pw.chromium.launch_persistent_context(
                user_data_dir=profile_dir,
                **launch_kwargs
            )
            
        # launch_persistent_context creates a default page, grab it
        if _context.pages:
            page = _context.pages[0]
        else:
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


# ─── Gmail compose + attachment ──────────────────────────────

def open_gmail_compose_with_attachment(
    to: str,
    subject: str = "",
    body: str = "",
    file_path: str = None,
    timeout_ms: int = 30_000,
    auto_send: bool = False,
) -> dict:
    """
    Opens Gmail compose in the Playwright browser (using the existing
    logged-in session) and optionally attaches a file.

    The browser MUST already be logged into Gmail — no OAuth needed.
    Uses the file input element triggered by the attachment button.

    Returns:
        { "draft_opened": bool, "attachment_verified": bool, "sent": bool, "error": str }
    """
    from urllib.parse import urlencode, quote
    import os

    result = {"draft_opened": False, "attachment_verified": False, "sent": False, "error": ""}

    try:
        ctx = _ensure_browser()
        # Reuse existing page (persistent context always starts with one) to avoid about:blank tab
        pages = ctx.pages
        page = pages[0] if pages else ctx.new_page()
        page.set_default_timeout(timeout_ms)

        # Build Gmail compose URL
        params = urlencode(
            {"to": to, "su": subject, "body": body},
            quote_via=quote,
        )
        compose_url = f"https://mail.google.com/mail/?view=cm&fs=1&{params}"
        print(f"  ➡️  Navigating to Gmail compose...")
        page.goto(compose_url, wait_until="domcontentloaded")

        # Wait for the compose window to appear
        # Gmail's "To" field is a hidden div — we wait for it to be attached (not visible)
        try:
            page.wait_for_selector(
                '[aria-label="To"], input[name="to"], .Am.Al.editable, [role="textbox"]',
                state="attached",
                timeout=20_000
            )
            result["draft_opened"] = True
            print("  ✔ Gmail compose window loaded")
        except Exception as e:
            result["error"] = f"Gmail compose window did not load: {e}"
            print(f"  ❌ Gmail compose selector not found: {e}")
            return result

        # Give Gmail a moment to stabilize (don't use networkidle — Gmail never reaches it)
        import time
        time.sleep(3)
        print("  ✔ Waited 3s for Gmail to stabilize")

        # ── Attach file ──────────────────────────────────────
        print(f"  🔍 file_path = {repr(file_path)}")
        if file_path:
            abs_path = os.path.abspath(file_path)
            file_name = os.path.basename(abs_path)
            print(f"  🔍 abs_path = {repr(abs_path)}, exists = {os.path.exists(abs_path)}")
            
            if not os.path.exists(abs_path):
                result["error"] = f"File not found: {abs_path}"
                print(f"  ❌ File not found: {abs_path}")
                return result

            print(f"  📎 Attaching: {abs_path}")

            # Strategy 1: Direct file input (most reliable for Gmail)
            try:
                file_inputs = page.locator('input[type="file"]')
                count = file_inputs.count()
                print(f"  🔍 Found {count} file input(s) on page")
                
                if count > 0:
                    file_inputs.first.set_input_files(abs_path, timeout=10_000)
                    result["attachment_verified"] = True
                    print(f"  ✔ Attached '{file_name}' via direct file input")
                else:
                    # Strategy 2: Click attach button to trigger file chooser
                    print("  🖱️ No file inputs found. Trying button click...")
                    with page.expect_file_chooser(timeout=15_000) as fc_info:
                        attach_btn = page.locator(
                            '[data-tooltip*="Attach"], [aria-label*="Attach"]'
                        ).first
                        attach_btn.click(force=True, timeout=10_000)
                    
                    file_chooser = fc_info.value
                    file_chooser.set_files(abs_path)
                    result["attachment_verified"] = True
                    print(f"  ✔ Attached '{file_name}' via file chooser")

            except Exception as e:
                print(f"  ❌ Attachment error: {e}")
                result["error"] = f"Attachment failed: {e}"

            # Wait for the upload to fully complete before proceeding
            if result["attachment_verified"]:
                print("  ⏳ Waiting for upload to complete...")
                try:
                    # Wait for the filename to appear as text (upload complete indicator)
                    page.wait_for_selector(
                        f'text="{file_name}"',
                        state="visible",
                        timeout=30_000
                    )
                    print(f"  ✔ Upload confirmed: '{file_name}' visible in compose")
                except Exception:
                    # Fallback: just wait a generous amount of time
                    print("  ⏳ Could not confirm upload visually, waiting 8s...")
                    time.sleep(8)
            else:
                time.sleep(2)

        else:
            print("  ⚠️ No file_path provided, skipping attachment")

        # ── Auto-send ────────────────────────────────────────
        if auto_send:
            print("  📤 Auto-send enabled, clicking Send button...")
            try:
                # Focus the compose body first
                body_area = page.locator('[aria-label*="Message Body"], [role="textbox"], .Am.Al.editable, textarea[name="body"]').first
                try:
                    body_area.focus(timeout=5_000)
                except Exception:
                    page.keyboard.press("Tab")
                    page.keyboard.press("Tab")
                
                time.sleep(0.5)
                
                # Strategy 1: Click the Send button directly (most reliable)
                sent_via_button = False
                try:
                    send_btn = page.locator(
                        '[aria-label*="Send"] >> visible=true, '
                        '[data-tooltip*="Send"] >> visible=true, '
                        'div[role="button"]:has-text("Send") >> visible=true'
                    ).first
                    send_btn.click(timeout=5_000)
                    sent_via_button = True
                    print("  ✔ Clicked Send button")
                except Exception as e:
                    print(f"  ⚠️ Send button click failed: {e}")
                
                # Strategy 2: Keyboard shortcut fallback
                if not sent_via_button:
                    import sys as _sys
                    shortcut = "Meta+Enter" if _sys.platform == "darwin" else "Control+Enter"
                    print(f"  📤 Using keyboard shortcut: {shortcut}")
                    page.keyboard.press(shortcut)
                
                # Wait for Gmail to process the send
                time.sleep(5)
                
                # Verify: check if compose window closed or "Message sent" banner appeared
                try:
                    sent_banner = page.locator('text="Message sent"', 'text="Your message has been sent"').first
                    sent_banner.wait_for(state="visible", timeout=8_000)
                    result["sent"] = True
                    print("  ✔ Send confirmed: 'Message sent' banner visible")
                except Exception:
                    # If compose window is gone, assume it was sent
                    try:
                        compose_still_open = page.locator('[aria-label*="Message Body"], .Am.Al.editable').first
                        compose_still_open.wait_for(state="visible", timeout=2_000)
                        # Still open — send probably failed
                        print("  ⚠️ Compose still open — send may have failed")
                        result["error"] = "Send button clicked but compose window still open"
                    except Exception:
                        # Compose is gone — likely sent!
                        result["sent"] = True
                        print("  ✔ Send confirmed: compose window closed")
                
                if result["sent"]:
                    # Close the browser window after successful send
                    _shutdown()
                    print("  ✔ Gmail window and Playwright closed.")
            except Exception as e:
                print(f"  ⚠️ Auto-send failed: {e}. Draft is still open for manual send.")
                result["error"] = f"Auto-send failed: {e}"

        result["draft_opened"] = True
        return result

    except Exception as e:
        result["error"] = str(e)
        print(f"  ❌ Gmail compose error: {e}")
        return result


# ── Zero-arg shims for main.ACTIONS generic dispatch ─────────
def action_web_back() -> None:
    go_back()


def action_web_refresh() -> None:
    refresh()


def action_web_new_tab() -> None:
    new_tab(None)


def action_web_close_tab() -> None:
    close_tab()
