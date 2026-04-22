"""
Computer Use — Low-level mouse and keyboard control via pyautogui.

Provides the physical control layer for the ComputerUseAgent.
All functions are safe by default — pauses between actions,
never moves off-screen, handles permission errors cleanly.

macOS requirements:
  - System Preferences → Privacy & Security → Accessibility → grant python/terminal
  - System Preferences → Privacy & Security → Screen Recording → grant terminal
  - Install: pip install pyautogui
"""

import sys
import time
from dataclasses import dataclass
from typing import Optional, Tuple

# ─── Settings ────────────────────────────────────────────────
DEFAULT_MOVE_DURATION = 0.3   # seconds for smooth mouse movement
DEFAULT_TYPE_INTERVAL = 0.04  # seconds between keystrokes
CLICK_PAUSE          = 0.1   # pause after each click
_AVAILABLE           = False  # set True once pyautogui loads ok

# ─────────────────────────────────────────────────────────────

@dataclass
class ControlResult:
    """Result of a computer control action."""
    ok: bool
    message: str = ""
    error: str = ""

    @classmethod
    def success(cls, message: str = "OK") -> "ControlResult":
        return cls(ok=True, message=message)

    @classmethod
    def fail(cls, error: str) -> "ControlResult":
        return cls(ok=False, error=error)


def _get_pyautogui():
    """Lazy-load pyautogui with permission check."""
    global _AVAILABLE
    try:
        import pyautogui
        pyautogui.FAILSAFE = True     # Move mouse to corner to abort
        pyautogui.PAUSE    = 0.05     # Small pause after each action
        _AVAILABLE = True
        return pyautogui
    except ImportError:
        raise RuntimeError(
            "pyautogui not installed. Run: pip install pyautogui"
        )
    except Exception as e:
        raise RuntimeError(f"pyautogui unavailable: {e}")


def is_available() -> bool:
    """Check if computer use is available."""
    try:
        _get_pyautogui()
        return True
    except Exception:
        return False


def get_screen_size() -> Tuple[int, int]:
    """Returns (width, height) of the primary screen."""
    try:
        pag = _get_pyautogui()
        return pag.size()
    except Exception:
        return (1920, 1080)


def get_mouse_position() -> Tuple[int, int]:
    """Returns current (x, y) mouse position."""
    try:
        pag = _get_pyautogui()
        pos = pag.position()
        return (pos.x, pos.y)
    except Exception:
        return (0, 0)


# ─── Mouse Actions ───────────────────────────────────────────


def move_to(x: int, y: int, duration: float = DEFAULT_MOVE_DURATION) -> ControlResult:
    """Move mouse to (x, y) with smooth animation."""
    try:
        pag = _get_pyautogui()
        w, h = pag.size()
        # Clamp slightly inward to avoid triggering PyAutoGUI's corner fail-safe
        x = max(2, min(x, w - 3))
        y = max(2, min(y, h - 3))
        pag.moveTo(x, y, duration=duration)
        return ControlResult.success(f"Moved to ({x}, {y})")
    except Exception as e:
        return ControlResult.fail(str(e))


def click(x: int, y: int, button: str = "left", clicks: int = 1) -> ControlResult:
    """Click at (x, y). button: 'left', 'right', 'middle'."""
    try:
        pag = _get_pyautogui()
        w, h = pag.size()
        # Clamp slightly inward to avoid triggering PyAutoGUI's corner fail-safe
        x = max(2, min(x, w - 3))
        y = max(2, min(y, h - 3))
        pag.click(x, y, button=button, clicks=clicks, interval=0.1)
        time.sleep(CLICK_PAUSE)
        return ControlResult.success(f"Clicked ({x}, {y}) [{button}]")
    except Exception as e:
        return ControlResult.fail(str(e))


def double_click(x: int, y: int) -> ControlResult:
    """Double-click at (x, y)."""
    return click(x, y, clicks=2)


def right_click(x: int, y: int) -> ControlResult:
    """Right-click at (x, y)."""
    return click(x, y, button="right")


def drag(x1: int, y1: int, x2: int, y2: int, duration: float = 0.5) -> ControlResult:
    """Drag from (x1,y1) to (x2,y2)."""
    try:
        pag = _get_pyautogui()
        pag.moveTo(x1, y1, duration=0.2)
        pag.dragTo(x2, y2, duration=duration, button="left")
        return ControlResult.success(f"Dragged ({x1},{y1}) → ({x2},{y2})")
    except Exception as e:
        return ControlResult.fail(str(e))


def scroll(x: int, y: int, clicks: int = 3) -> ControlResult:
    """Scroll at (x, y). Positive = up, negative = down."""
    try:
        pag = _get_pyautogui()
        pag.scroll(clicks, x=x, y=y)
        return ControlResult.success(f"Scrolled {clicks} at ({x},{y})")
    except Exception as e:
        return ControlResult.fail(str(e))


# ─── Keyboard Actions ────────────────────────────────────────


def type_text(text: str, interval: float = DEFAULT_TYPE_INTERVAL) -> ControlResult:
    """Type text character by character. Handles special chars."""
    try:
        pag = _get_pyautogui()
        # pyautogui.write can't handle unicode well — use clipboard for safety
        # For simple ASCII, use write; for unicode, use clipboard paste
        if all(ord(c) < 128 for c in text):
            pag.write(text, interval=interval)
        else:
            # Use clipboard for unicode characters (e.g. emoji, non-ASCII)
            _paste_text(text)
        return ControlResult.success(f"Typed: {text[:30]}{'...' if len(text) > 30 else ''}")
    except Exception as e:
        return ControlResult.fail(str(e))


def _paste_text(text: str) -> None:
    """Paste text via clipboard (handles unicode)."""
    import subprocess
    # Copy to macOS clipboard
    proc = subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=True)
    time.sleep(0.1)
    import pyautogui
    pyautogui.hotkey("command", "v")
    time.sleep(0.1)


def press_key(key: str) -> ControlResult:
    """Press a single key. Examples: 'enter', 'tab', 'escape', 'space'."""
    try:
        pag = _get_pyautogui()
        pag.press(key)
        return ControlResult.success(f"Pressed: {key}")
    except Exception as e:
        return ControlResult.fail(str(e))


def hotkey(*keys: str) -> ControlResult:
    """Press key combination. Example: hotkey('command', 'c')."""
    try:
        pag = _get_pyautogui()
        pag.hotkey(*keys)
        return ControlResult.success(f"Hotkey: {'+'.join(keys)}")
    except Exception as e:
        return ControlResult.fail(str(e))


def key_down(key: str) -> ControlResult:
    """Hold key down."""
    try:
        pag = _get_pyautogui()
        pag.keyDown(key)
        return ControlResult.success(f"Key down: {key}")
    except Exception as e:
        return ControlResult.fail(str(e))


def key_up(key: str) -> ControlResult:
    """Release held key."""
    try:
        pag = _get_pyautogui()
        pag.keyUp(key)
        return ControlResult.success(f"Key up: {key}")
    except Exception as e:
        return ControlResult.fail(str(e))


# ─── Compound Helpers ────────────────────────────────────────


def click_and_type(x: int, y: int, text: str, clear_first: bool = True) -> ControlResult:
    """
    Click a field then type text.
    If clear_first=True, selects all and deletes before typing.
    """
    r = click(x, y)
    if not r.ok:
        return r

    time.sleep(0.15)

    if clear_first:
        hotkey("command", "a")
        time.sleep(0.05)
        press_key("delete")
        time.sleep(0.05)

    return type_text(text)


def open_spotlight() -> ControlResult:
    """Open macOS Spotlight search."""
    return hotkey("command", "space")


def open_app_via_spotlight(app_name: str) -> ControlResult:
    """Open an app using Spotlight (most reliable method on macOS)."""
    try:
        r = open_spotlight()
        if not r.ok:
            return r
        time.sleep(0.6)
        r = type_text(app_name)
        if not r.ok:
            return r
        time.sleep(0.5)
        r = press_key("enter")
        time.sleep(1.5)  # Give app time to open/focus
        return ControlResult.success(f"Opened {app_name} via Spotlight")
    except Exception as e:
        return ControlResult.fail(str(e))


def focus_address_bar() -> ControlResult:
    """Focus the browser address bar (Cmd+L on macOS)."""
    return hotkey("command", "l")


def navigate_browser_to(url: str) -> ControlResult:
    """Navigate browser to URL via address bar."""
    try:
        r = focus_address_bar()
        if not r.ok:
            return r
        time.sleep(0.3)
        r = type_text(url)
        if not r.ok:
            return r
        time.sleep(0.1)
        return press_key("enter")
    except Exception as e:
        return ControlResult.fail(str(e))


def take_screenshot_to_bytes() -> Optional[bytes]:
    """Take a screenshot and return as PNG bytes."""
    try:
        pag = _get_pyautogui()
        img = pag.screenshot()
        import io
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception as e:
        print(f"⚠️  Screenshot error: {e}")
        return None


def take_screenshot_to_file(path: Optional[str] = None) -> Optional[str]:
    """Take screenshot and save to file. Returns path."""
    import tempfile, os
    try:
        pag = _get_pyautogui()
        if not path:
            tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False, prefix="arc_cu_")
            path = tmp.name
            tmp.close()
        pag.screenshot(path)
        return path
    except Exception as e:
        print(f"⚠️  Screenshot to file error: {e}")
        return None


# ─── Quick Test ──────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("  COMPUTER USE MODULE TEST")
    print("=" * 60)

    if not is_available():
        print("  ⚠️  pyautogui not available — install it: pip install pyautogui")
        exit(1)

    w, h = get_screen_size()
    print(f"  Screen: {w}x{h}")
    print(f"  Mouse:  {get_mouse_position()}")

    print("\n  Testing screenshot...")
    path = take_screenshot_to_file()
    if path:
        print(f"  ✅ Screenshot saved: {path}")
        import os; os.unlink(path)
    else:
        print("  ❌ Screenshot failed")

    print("\n✅ Computer use module ready")
