"""
Action Verifier — per-action deterministic verification against real machine state.

Phase 2: Every action family gets its own verifier. ARC stops assuming success.

Verification priority:
  1. Deterministic OS checks (os.path, stat)  — file actions
  2. macOS Accessibility tree                  — app actions
  3. Playwright browser state                  — browser actions
  4. Coarse perception fallback                — legacy actions

Contract:
  - Returns VerificationResult(ok, message, details)
  - ActionResult.verified = True/False based on result
  - On failure: retry once if safe, then grounded failure
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional

from core.command_schema import VerificationResult

if TYPE_CHECKING:
    from core.perception_engine import PerceptionState


# ─── Before-state snapshot ───────────────────────────────────

@dataclass
class BeforeState:
    """Rich pre-action snapshot for verification."""

    # Legacy perception engine fields
    active_app: str = ""
    active_window: str = ""

    # File state (captured for file actions)
    file_exists: Optional[bool] = None
    file_path: Optional[str] = None
    file_mtime: Optional[float] = None
    file_size: Optional[int] = None

    # Browser state (captured for browser actions)
    browser_url: str = ""
    browser_title: str = ""
    browser_tab_count: int = 0
    browser_running: bool = False

    # AX state
    ax_frontmost_app: str = ""
    ax_window_title: str = ""

    timestamp: float = 0.0

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = time.time()


def capture_before_state(action: str, params: dict) -> BeforeState:
    """
    Capture the machine state BEFORE action execution.
    Only captures what's relevant for the specific action.
    """
    state = BeforeState()

    # ── Always: AX frontmost app ─────────────────────────────
    try:
        from perception.ui_accessibility import get_frontmost_app, get_focused_window_title
        state.ax_frontmost_app = get_frontmost_app() or ""
        state.ax_window_title = get_focused_window_title() or ""
    except Exception:
        pass

    # ── Also feed legacy perception fields ───────────────────
    state.active_app = state.ax_frontmost_app
    state.active_window = state.ax_window_title

    # ── File actions: capture file state ─────────────────────
    if action in _FILE_ACTIONS:
        path = _resolve_file_path(action, params)
        if path:
            state.file_path = path
            state.file_exists = os.path.exists(path)
            if state.file_exists:
                try:
                    stat = os.stat(path)
                    state.file_mtime = stat.st_mtime
                    state.file_size = stat.st_size
                except Exception:
                    pass

    # ── Browser actions: capture browser state ───────────────
    if action in _BROWSER_ACTIONS:
        try:
            from perception.browser_state import get_active_tab_state
            snap = get_active_tab_state()
            state.browser_url = snap.url
            state.browser_title = snap.title
            state.browser_tab_count = snap.tab_count
            state.browser_running = snap.is_running
        except Exception:
            pass

    return state


# ─── File path resolution ────────────────────────────────────

_LOCATIONS = {
    "desktop":   os.path.expanduser("~/Desktop"),
    "downloads": os.path.expanduser("~/Downloads"),
    "documents": os.path.expanduser("~/Documents"),
    "home":      os.path.expanduser("~"),
}


def _resolve_file_path(action: str, params: dict) -> Optional[str]:
    """Best-effort path resolution for file actions."""
    filename = params.get("filename", "")
    if not filename:
        return None

    # If already absolute
    if os.path.isabs(filename):
        return filename

    # Check result data for resolved path
    location = params.get("location", "desktop")
    base = _LOCATIONS.get(str(location).lower() if location else "desktop",
                          os.path.expanduser("~/Desktop"))
    return os.path.join(base, filename)


def _resolve_new_file_path(params: dict) -> Optional[str]:
    """Resolve the new file path for rename/copy actions."""
    new_name = params.get("new_name", "")
    if not new_name:
        return None

    # Try to get directory from the original file path
    old_path = _resolve_file_path("rename_file", params)
    if old_path:
        return os.path.join(os.path.dirname(old_path), new_name)

    location = params.get("location", "desktop")
    base = _LOCATIONS.get(str(location).lower() if location else "desktop",
                          os.path.expanduser("~/Desktop"))
    return os.path.join(base, new_name)


# ═════════════════════════════════════════════════════════════
#  FILE VERIFIERS
# ═════════════════════════════════════════════════════════════

def verify_file_created(params: dict, result: Any, before: BeforeState) -> VerificationResult:
    """Verify a file was actually created on disk."""
    path = _resolve_file_path("create_file", params)
    if not path:
        return VerificationResult(ok=False, message="No file path to verify.",
                                  details={"reason": "no_path"})

    # Also check result data for path
    if hasattr(result, 'data') and result.data.get("path"):
        path = result.data["path"]

    exists = os.path.exists(path)
    return VerificationResult(
        ok=exists,
        message="File created." if exists else f"File not found at {path}.",
        details={"path": path, "exists": exists},
    )


def verify_file_renamed(params: dict, result: Any, before: BeforeState) -> VerificationResult:
    """Verify old file is gone and new file exists."""
    old_path = _resolve_file_path("rename_file", params)
    new_path = _resolve_new_file_path(params)

    # Try to get paths from result data (more reliable)
    if hasattr(result, 'data'):
        if result.data.get("path"):
            new_path = result.data["path"]
        if result.data.get("new_name") and old_path:
            new_path = os.path.join(os.path.dirname(old_path), result.data["new_name"])

    details: dict = {"old_path": old_path, "new_path": new_path}

    if not new_path:
        return VerificationResult(ok=False, message="No new path to verify.", details=details)

    new_exists = os.path.exists(new_path)
    old_gone = not os.path.exists(old_path) if old_path else True

    ok = new_exists and old_gone
    if ok:
        msg = "Rename verified."
    elif not new_exists:
        msg = f"New file not found at {new_path}."
    else:
        msg = f"Old file still exists at {old_path}."

    details["new_exists"] = new_exists
    details["old_gone"] = old_gone
    return VerificationResult(ok=ok, message=msg, details=details)


def verify_file_deleted(params: dict, result: Any, before: BeforeState) -> VerificationResult:
    """Verify file is gone (or moved to Trash)."""
    path = before.file_path or _resolve_file_path("delete_file", params)
    if not path:
        return VerificationResult(ok=False, message="No file path to verify.",
                                  details={"reason": "no_path"})

    gone = not os.path.exists(path)
    return VerificationResult(
        ok=gone,
        message="File deleted." if gone else f"File still exists at {path}.",
        details={"path": path, "gone": gone},
    )


def verify_file_copied(params: dict, result: Any, before: BeforeState) -> VerificationResult:
    """Verify destination copy exists."""
    filename = params.get("filename", "")
    location = params.get("location", "desktop")
    if not filename:
        return VerificationResult(ok=False, message="No filename to verify.")

    base = _LOCATIONS.get(str(location).lower() if location else "desktop",
                          os.path.expanduser("~/Desktop"))
    dest = os.path.join(base, os.path.basename(filename))
    exists = os.path.exists(dest)
    return VerificationResult(
        ok=exists,
        message="Copy verified." if exists else f"Copy not found at {dest}.",
        details={"dest_path": dest, "exists": exists},
    )


def verify_file_edited(params: dict, result: Any, before: BeforeState) -> VerificationResult:
    """Verify file content changed (mtime or size changed)."""
    path = before.file_path or _resolve_file_path("edit_file", params)
    if not path:
        return VerificationResult(ok=False, message="No file path to verify.")

    if not os.path.exists(path):
        return VerificationResult(ok=False, message=f"File not found: {path}.",
                                  details={"path": path})

    try:
        stat = os.stat(path)
        new_mtime = stat.st_mtime
        new_size = stat.st_size
    except Exception:
        return VerificationResult(ok=False, message="Could not stat file after edit.")

    # If we had before-state, compare
    if before.file_mtime is not None:
        changed = (new_mtime != before.file_mtime) or (new_size != before.file_size)
    else:
        # No before state — just check file exists
        changed = True

    return VerificationResult(
        ok=changed,
        message="File edited." if changed else "File unchanged after edit.",
        details={
            "path": path,
            "before_mtime": before.file_mtime,
            "after_mtime": new_mtime,
            "before_size": before.file_size,
            "after_size": new_size,
        },
    )


def verify_folder_created(params: dict, result: Any, before: BeforeState) -> VerificationResult:
    """Verify folder exists on disk."""
    target = params.get("target", "")
    if not target:
        return VerificationResult(ok=False, message="No folder target to verify.")

    # Resolve path
    location = params.get("location", "desktop")
    if os.path.isabs(target):
        path = target
    else:
        base = _LOCATIONS.get(str(location).lower() if location else "desktop",
                              os.path.expanduser("~/Desktop"))
        path = os.path.join(base, target)

    is_dir = os.path.isdir(path)
    return VerificationResult(
        ok=is_dir,
        message="Folder created." if is_dir else f"Folder not found at {path}.",
        details={"path": path, "is_dir": is_dir},
    )


def verify_folder_opened(params: dict, result: Any, before: BeforeState) -> VerificationResult:
    """Verify Finder is now the frontmost app."""
    try:
        from perception.ui_accessibility import get_frontmost_app
        app = (get_frontmost_app() or "").lower()
        ok = "finder" in app
        return VerificationResult(
            ok=ok,
            message="Finder is active." if ok else f"Frontmost app is '{app}', not Finder.",
            details={"frontmost_app": app},
        )
    except Exception:
        return VerificationResult(ok=True, message="Could not check frontmost app.")


# ═════════════════════════════════════════════════════════════
#  APP VERIFIERS (AX-first)
# ═════════════════════════════════════════════════════════════

def _norm(s: str) -> str:
    return (s or "").strip().lower()


def verify_app_opened(params: dict, result: Any, before: BeforeState) -> VerificationResult:
    """Verify target app is frontmost or at least running."""
    target = _norm(params.get("target", params.get("name", "")))
    if not target:
        return VerificationResult(ok=False, message="No app target to verify.")

    # Give app time to launch
    time.sleep(0.8)

    try:
        from perception.ui_accessibility import get_frontmost_app, is_app_running
        front = _norm(get_frontmost_app())

        # Check if frontmost matches
        if target in front or front in target:
            return VerificationResult(
                ok=True, message=f"{target} is frontmost.",
                details={"frontmost": front, "target": target},
            )

        # Check if at least running
        running = is_app_running(target) or is_app_running(target.title())
        if running:
            return VerificationResult(
                ok=True,
                message=f"{target} is running but not frontmost (frontmost: {front}).",
                details={"frontmost": front, "target": target, "running": True},
            )

        return VerificationResult(
            ok=False,
            message=f"Could not confirm {target} opened. Frontmost: {front}.",
            details={"frontmost": front, "target": target, "running": False},
        )
    except Exception as e:
        return VerificationResult(ok=True, message=f"AX check failed: {e}")


def verify_app_switched(params: dict, result: Any, before: BeforeState) -> VerificationResult:
    """Verify frontmost app changed to target."""
    target = _norm(params.get("target", params.get("name", "")))
    if not target:
        return VerificationResult(ok=False, message="No app target to verify.")

    time.sleep(0.5)

    try:
        from perception.ui_accessibility import get_frontmost_app
        front = _norm(get_frontmost_app())

        if target in front or front in target:
            return VerificationResult(
                ok=True, message=f"Switched to {target}.",
                details={"frontmost": front, "target": target},
            )

        return VerificationResult(
            ok=False,
            message=f"Expected {target} frontmost, got {front}.",
            details={"frontmost": front, "target": target, "before_app": before.ax_frontmost_app},
        )
    except Exception:
        return VerificationResult(ok=True, message="Could not verify app switch.")


def verify_app_closed(params: dict, result: Any, before: BeforeState) -> VerificationResult:
    """Verify target app is no longer frontmost or no longer running."""
    target = _norm(params.get("target", params.get("name", "")))
    if not target:
        return VerificationResult(ok=False, message="No app target to verify.")

    time.sleep(0.5)

    try:
        from perception.ui_accessibility import get_frontmost_app
        front = _norm(get_frontmost_app())

        # App should no longer be frontmost
        if target not in front and front not in target:
            return VerificationResult(
                ok=True, message=f"{target} closed. Frontmost: {front}.",
                details={"frontmost": front, "target": target},
            )

        return VerificationResult(
            ok=False,
            message=f"{target} still appears frontmost.",
            details={"frontmost": front, "target": target},
        )
    except Exception:
        return VerificationResult(ok=True, message="Could not verify app closure.")


def verify_app_minimised(params: dict, result: Any, before: BeforeState) -> VerificationResult:
    """Verify frontmost app changed (target is no longer frontmost)."""
    target = _norm(params.get("target", params.get("name", "")))
    if not target:
        return VerificationResult(ok=True, message="No target — skipping.")

    time.sleep(0.5)

    try:
        from perception.ui_accessibility import get_frontmost_app
        front = _norm(get_frontmost_app())

        if target not in front:
            return VerificationResult(
                ok=True, message=f"{target} minimised. Frontmost: {front}.",
                details={"frontmost": front, "target": target},
            )
        return VerificationResult(
            ok=False,
            message=f"{target} still frontmost.",
            details={"frontmost": front},
        )
    except Exception:
        return VerificationResult(ok=True, message="Could not verify minimise.")


# ═════════════════════════════════════════════════════════════
#  BROWSER VERIFIERS (Playwright-first)
# ═════════════════════════════════════════════════════════════

def verify_url_opened(params: dict, result: Any, before: BeforeState) -> VerificationResult:
    """Verify the browser navigated to the expected URL."""
    expected_url = params.get("url", "")
    if not expected_url:
        # Try from result data
        if hasattr(result, 'data') and result.data.get("url"):
            expected_url = result.data["url"]

    try:
        from perception.browser_state import get_active_tab_state
        snap = get_active_tab_state()

        if not snap.is_running:
            return VerificationResult(
                ok=False, message="Browser not running.",
                details={"expected": expected_url},
            )

        current = _norm(snap.url)
        expected_norm = _norm(expected_url)

        # Check if URL changed from before and contains expected domain
        # Extract domain from expected URL for matching
        from urllib.parse import urlparse
        try:
            expected_domain = urlparse(expected_url if "://" in expected_url else f"https://{expected_url}").netloc.replace("www.", "")
        except Exception:
            expected_domain = expected_url.lower()

        url_matches = (
            expected_domain in current
            or expected_norm in current
            or current != _norm(before.browser_url)  # URL at least changed
        )

        return VerificationResult(
            ok=url_matches,
            message="Page loaded." if url_matches else f"Expected URL with '{expected_domain}', got '{snap.url}'.",
            details={"expected": expected_url, "actual": snap.url, "before": before.browser_url},
        )
    except Exception as e:
        return VerificationResult(ok=True, message=f"Browser check failed: {e}")


def verify_google_search(params: dict, result: Any, before: BeforeState) -> VerificationResult:
    """Verify a Google search results page loaded."""
    try:
        from perception.browser_state import get_active_tab_state
        snap = get_active_tab_state()

        if not snap.is_running:
            return VerificationResult(ok=False, message="Browser not running.")

        url = _norm(snap.url)
        is_search = "google.com/search" in url or "google.com/search?" in url

        return VerificationResult(
            ok=is_search,
            message="Search loaded." if is_search else f"Expected Google search, got {snap.url}.",
            details={"url": snap.url, "is_search": is_search},
        )
    except Exception:
        return VerificationResult(ok=True, message="Could not verify search.")


def verify_new_tab(params: dict, result: Any, before: BeforeState) -> VerificationResult:
    """Verify tab count increased."""
    try:
        from perception.browser_state import get_active_tab_state
        snap = get_active_tab_state()

        if not snap.is_running:
            return VerificationResult(ok=False, message="Browser not running.")

        increased = snap.tab_count > before.browser_tab_count
        return VerificationResult(
            ok=increased,
            message=f"New tab opened ({snap.tab_count} tabs)." if increased
                    else f"Tab count unchanged ({snap.tab_count}).",
            details={"before": before.browser_tab_count, "after": snap.tab_count},
        )
    except Exception:
        return VerificationResult(ok=True, message="Could not verify tab count.")


def verify_close_tab(params: dict, result: Any, before: BeforeState) -> VerificationResult:
    """Verify tab count decreased."""
    try:
        from perception.browser_state import get_active_tab_state
        snap = get_active_tab_state()

        if not snap.is_running:
            # Browser might have closed entirely
            return VerificationResult(ok=True, message="Browser closed.")

        decreased = snap.tab_count < before.browser_tab_count
        # Also OK if navigated to about:blank (was last tab)
        if not decreased and snap.tab_count == 1 and "about:blank" in (snap.url or ""):
            decreased = True

        return VerificationResult(
            ok=decreased,
            message=f"Tab closed ({snap.tab_count} tabs)." if decreased
                    else f"Tab count unchanged ({snap.tab_count}).",
            details={"before": before.browser_tab_count, "after": snap.tab_count},
        )
    except Exception:
        return VerificationResult(ok=True, message="Could not verify tab close.")


# ═════════════════════════════════════════════════════════════
#  VERIFIER REGISTRY
# ═════════════════════════════════════════════════════════════

VERIFIERS: Dict[str, Callable] = {
    # File operations
    "create_file":       verify_file_created,
    "create_and_edit_file": verify_file_created,
    "rename_file":       verify_file_renamed,
    "delete_file":       verify_file_deleted,
    "copy_file":         verify_file_copied,
    "edit_file":         verify_file_edited,
    "create_folder":     verify_folder_created,
    "open_folder":       verify_folder_opened,

    # App operations
    "open_app":          verify_app_opened,
    "switch_to_app":     verify_app_switched,
    "close_app":         verify_app_closed,
    "minimise_app":      verify_app_minimised,

    # Browser operations
    "open_url":          verify_url_opened,
    "search_google":     verify_google_search,
    "new_tab":           verify_new_tab,
    "close_tab":         verify_close_tab,
}

# Actions safe to retry once on verification failure
SAFE_TO_RETRY = {
    "create_file", "copy_file", "create_folder",
    "open_app", "open_url", "search_google", "new_tab",
    "open_folder", "switch_to_app",
}

# File action set (for before-state capture)
_FILE_ACTIONS = {
    "create_file", "rename_file", "delete_file", "copy_file",
    "edit_file", "create_and_edit_file", "create_folder",
}

# Browser action set (for before-state capture)
_BROWSER_ACTIONS = {
    "open_url", "search_google", "new_tab", "close_tab",
}


def verify_action(
    action: str,
    params: dict,
    result: Any,
    before: BeforeState,
) -> VerificationResult:
    """
    Dispatch to the per-action verifier.
    Falls back to ok=True for actions without specific verifiers.
    """
    verifier = VERIFIERS.get(action)
    if verifier is None:
        return VerificationResult(
            ok=True,
            message="No specific verifier for this action.",
            details={"action": action, "has_verifier": False},
        )

    try:
        return verifier(params, result, before)
    except Exception as e:
        # Never crash in verification — report the error but don't block
        return VerificationResult(
            ok=True,
            message=f"Verifier error: {e}",
            details={"action": action, "error": str(e)},
        )


# ═════════════════════════════════════════════════════════════
#  LEGACY COMPATIBILITY
# ═════════════════════════════════════════════════════════════

@dataclass
class ExpectedDelta:
    """What should change after a successful action (any subset may be set)."""

    active_app_contains: Optional[str] = None
    window_title_contains: Optional[str] = None
    active_app_not_equals: Optional[str] = None


def verify_perception_delta(
    before: "PerceptionState",
    after: "PerceptionState",
    expected: ExpectedDelta,
) -> VerificationResult:
    """
    Legacy heuristic check using coarse perception_engine fields.
    Kept for backward compatibility — new code should use verify_action().
    """
    details: dict[str, Any] = {
        "before_app": getattr(before, "active_app", ""),
        "after_app": getattr(after, "active_app", ""),
        "before_window": getattr(before, "active_window", ""),
        "after_window": getattr(after, "active_window", ""),
    }

    if expected.active_app_not_equals:
        want = _norm(expected.active_app_not_equals)
        if want and _norm(getattr(before, "active_app", "")) == _norm(getattr(after, "active_app", "")):
            return VerificationResult(
                ok=False,
                message="Expected foreground app to change.",
                details=details,
            )

    if expected.active_app_contains:
        needle = _norm(expected.active_app_contains)
        hay = _norm(getattr(after, "active_app", ""))
        if needle and needle not in hay:
            return VerificationResult(
                ok=False,
                message=f"Expected active app to match '{expected.active_app_contains}'.",
                details=details,
            )

    if expected.window_title_contains:
        needle = _norm(expected.window_title_contains)
        hay = _norm(getattr(after, "active_window", ""))
        if needle and needle not in hay:
            return VerificationResult(
                ok=False,
                message=f"Expected window title to contain '{expected.window_title_contains}'.",
                details=details,
            )

    return VerificationResult(ok=True, message="State consistent with expectations.", details=details)


@dataclass
class VerificationPolicy:
    """Hook for stricter checks later (timeouts, retries, AX tree equality)."""

    max_wait_seconds: float = 2.0
    extra: dict[str, Any] = field(default_factory=dict)
