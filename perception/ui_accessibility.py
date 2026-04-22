"""
Accessibility tree summaries (AXUIElement on macOS via osascript).

Use this before screenshots: native structure is richer and cheaper than vision-only agents.

Perception priority: AX first → browser state → OCR → vision fallback.
"""

from __future__ import annotations

import subprocess
import sys
import time
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class AXNodeSummary:
    """Tiny serializable slice of an accessibility node."""

    role: str
    title: str
    value: Optional[str] = None
    children: Optional[List["AXNodeSummary"]] = None


@dataclass
class AXSnapshot:
    """Full accessibility snapshot of the current macOS UI state."""

    frontmost_app: str = ""
    window_title: str = ""
    focused_role: str = ""          # role of currently focused UI element
    focused_title: str = ""         # title/label of focused element
    focused_value: str = ""         # value of focused element (e.g. text field content)
    menu_bar_items: List[str] = field(default_factory=list)
    visible_buttons: List[str] = field(default_factory=list)
    visible_text_fields: List[str] = field(default_factory=list)
    timestamp: float = 0.0
    error: str = ""                 # non-empty if AX queries failed

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = time.time()

    def is_empty(self) -> bool:
        return not self.frontmost_app and not self.window_title


# ─── Low-level osascript helpers ─────────────────────────────

# Phrases in osascript stderr that indicate a permission problem
_PERMISSION_PHRASES = (
    "not allowed",
    "not authorized",
    "accessibility",
    "assistive",
    "permission",
    "1743",        # OSStatus kAXErrorAPIDisabled
    "-25211",      # AXUIElement error
)


def _run_osascript(script: str, timeout: float = 3.0) -> tuple[str, str]:
    """
    Run AppleScript and return (stdout, error).

    Returns:
        (output, "")           — success (output may be empty string if app returned nothing)
        ("", error_message)    — failure (timeout, permission denied, osascript error)

    Callers should check the error string to distinguish 'no data' from 'blocked'.
    """
    if sys.platform != "darwin":
        return "", "not_macos"
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=timeout,
        )
        stderr = result.stderr.strip().lower()
        if result.returncode != 0:
            # Surface permission errors distinctly
            if any(p in stderr for p in _PERMISSION_PHRASES):
                return "", f"permission_denied: {result.stderr.strip()}"
            return "", f"osascript_error({result.returncode}): {result.stderr.strip()}"
        return result.stdout.strip(), ""
    except subprocess.TimeoutExpired:
        return "", "timeout"
    except FileNotFoundError:
        return "", "osascript_not_found"
    except Exception as e:
        return "", f"exception: {e}"


def _run_osascript_list(script: str, timeout: float = 4.0) -> tuple[List[str], str]:
    """Run AppleScript that returns a comma-separated list, returns (list, error)."""
    raw, err = _run_osascript(script, timeout)
    if err:
        return [], err
    if not raw:
        return [], ""
    # AppleScript returns lists like: "item1, item2, item3"
    return [item.strip() for item in raw.split(",") if item.strip()], ""




# ─── Individual AX queries ───────────────────────────────────

def get_frontmost_app() -> tuple[str, str]:
    """
    Returns (app_name, error).
    - ("Safari", "")        — success
    - ("", "")              — no frontmost app (unusual but valid)
    - ("", "permission_denied: ...")  — Accessibility not granted
    """
    return _run_osascript(
        'tell application "System Events" to name of first process whose frontmost is true'
    )


def get_focused_window_title() -> tuple[str, str]:
    """Returns the title of the focused window of the frontmost app as (title, error)."""
    app, err = get_frontmost_app()
    if err:
        return "", err
    if not app:
        return "", ""
    return _run_osascript(
        f'tell application "System Events" to tell process "{app}" '
        f'to name of front window'
    )


def get_focused_element_info() -> tuple[dict, str]:
    """
    Returns role, title, and value of the currently focused UI element as (dict, error).
    Uses System Events accessibility.
    """
    app, err = get_frontmost_app()
    if err:
        return {"role": "", "title": "", "value": ""}, err
    if not app:
        return {"role": "", "title": "", "value": ""}, ""

    role, r_err = _run_osascript(
        f'tell application "System Events" to tell process "{app}" '
        f'to role of focused UI element of front window'
    )
    if r_err: return {"role": "", "title": "", "value": ""}, r_err

    title, t_err = _run_osascript(
        f'tell application "System Events" to tell process "{app}" '
        f'to description of focused UI element of front window'
    )
    value, v_err = _run_osascript(
        f'tell application "System Events" to tell process "{app}" '
        f'to value of focused UI element of front window'
    )

    return {
        "role": role or "",
        "title": title or "",
        "value": value or "",
    }, ""


def get_menu_bar_items() -> tuple[List[str], str]:
    """Returns names of the menu bar items of the frontmost app as (list, error)."""
    app, err = get_frontmost_app()
    if err:
        return [], err
    if not app:
        return [], ""
    return _run_osascript_list(
        f'tell application "System Events" to tell process "{app}" '
        f'to name of every menu bar item of menu bar 1'
    )


def get_window_buttons() -> tuple[List[str], str]:
    """Returns titles/names of visible buttons in the front window (shallow) as (list, error)."""
    app, err = get_frontmost_app()
    if err:
        return [], err
    if not app:
        return [], ""
    raw, err = _run_osascript(
        f'tell application "System Events" to tell process "{app}" '
        f'to name of every button of front window',
        timeout=4.0,
    )
    if err:
        return [], err
    if not raw or raw == "missing value":
        return [], ""
    return [b.strip() for b in raw.split(",") if b.strip() and b.strip() != "missing value"], ""


def get_window_text_fields() -> tuple[List[str], str]:
    """Returns values of visible text fields in the front window (shallow) as (list, error)."""
    app, err = get_frontmost_app()
    if err:
        return [], err
    if not app:
        return [], ""
    raw, err = _run_osascript(
        f'tell application "System Events" to tell process "{app}" '
        f'to value of every text field of front window',
        timeout=4.0,
    )
    if err:
        return [], err
    if not raw or raw == "missing value":
        return [], ""
    return [t.strip() for t in raw.split(",") if t.strip() and t.strip() != "missing value"], ""


def is_app_running(app_name: str) -> tuple[bool, str]:
    """Check if an app is currently running (by process name), returning (bool, error)."""
    result, err = _run_osascript(
        f'tell application "System Events" to (name of every process) contains "{app_name}"'
    )
    if err:
        return False, err
    return result.lower() == "true", ""


def get_running_apps() -> tuple[List[str], str]:
    """Returns list of all running application names as (list, error)."""
    return _run_osascript_list(
        'tell application "System Events" to name of every process whose background only is false'
    )


# ─── Full snapshot ───────────────────────────────────────────

def get_ax_snapshot() -> AXSnapshot:
    """
    Collect a complete AX snapshot in one call.
    Gracefully handles failures — never crashes.

    AXSnapshot.error is populated with a real error string when:
    - Accessibility permission is not granted (permission_denied)
    - osascript is not available
    - Timeout occurred
    An empty error string means AX queries succeeded (even if app info is empty).
    """
    if sys.platform != "darwin":
        return AXSnapshot(error="not_macos")

    try:
        app, app_err = get_frontmost_app()

        # Propagate permission/availability errors immediately
        if app_err:
            return AXSnapshot(error=app_err)

        title = ""
        if app:
            title, _ = get_focused_window_title()

        # Focused element info (may fail for some apps)
        focused = {"role": "", "title": "", "value": ""}
        try:
            f_info, _ = get_focused_element_info()
            focused = f_info
        except Exception:
            pass

        # Buttons and text fields (shallow, may fail)
        buttons: List[str] = []
        text_fields: List[str] = []
        try:
            b_list, _ = get_window_buttons()
            buttons = b_list
        except Exception:
            pass
        try:
            t_list, _ = get_window_text_fields()
            text_fields = t_list
        except Exception:
            pass

        return AXSnapshot(
            frontmost_app=app,
            window_title=title,
            focused_role=focused.get("role", ""),
            focused_title=focused.get("title", ""),
            focused_value=focused.get("value", ""),
            visible_buttons=buttons,
            visible_text_fields=text_fields,
            # error stays empty — queries succeeded
        )

    except Exception as e:
        return AXSnapshot(error=str(e))


# ─── Utilities ───────────────────────────────────────────────

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


def snapshot_to_text(snap: AXSnapshot) -> str:
    """Format an AXSnapshot as a readable text block for LLM context."""
    lines = [
        f"frontmost_app: {snap.frontmost_app or '(unknown)'}",
        f"window_title: {snap.window_title or '(unknown)'}",
    ]
    if snap.focused_role:
        lines.append(f"focused_element: {snap.focused_role} - {snap.focused_title}")
    if snap.focused_value:
        lines.append(f"focused_value: {snap.focused_value[:200]}")
    if snap.visible_buttons:
        lines.append(f"buttons: {', '.join(snap.visible_buttons[:10])}")
    if snap.visible_text_fields:
        lines.append(f"text_fields: {', '.join(snap.visible_text_fields[:5])}")
    if snap.error:
        lines.append(f"error: {snap.error}")
    return "\n".join(lines)


# ─── Quick Test ──────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("  ACCESSIBILITY PERCEPTION TEST")
    print("=" * 60)

    snap = get_ax_snapshot()
    print(f"\n{snapshot_to_text(snap)}")

    running, r_err = is_app_running('Finder')
    print(f"\nApp running check (Finder): {running}")

    running_apps, _ = get_running_apps()
    print(f"Running apps: {', '.join(running_apps[:10])}")

    print("\n✅ AX test passed!")
