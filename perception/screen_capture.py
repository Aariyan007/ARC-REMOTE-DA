"""
Primary display and window capture.
macOS: screencapture CLI.
Windows: PowerShell + System.Drawing.

Supports both full display and focused-window capture.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from core.platform_utils import is_mac, is_windows


def capture_primary_display_to_file(path: Optional[str] = None) -> str:
    """
    Write a screenshot of the main display to ``path`` (PNG).
    If ``path`` is None, uses a temp file.

    macOS: ``screencapture`` (requires screen-recording permission when sandboxed).
    Windows: PowerShell + .NET System.Drawing (best-effort; replace with DXGI/WGC later).

    Raises:
        PermissionError  — screen-recording permission not granted (macOS)
        NotImplementedError — unsupported platform
        RuntimeError     — capture failed for another reason
    """
    out = path or str(Path(tempfile.gettempdir()) / "startup_screen_capture.png")

    if is_mac():
        try:
            subprocess.run(["screencapture", "-x", out], check=True, capture_output=True)
            return out
        except subprocess.CalledProcessError as e:
            stderr = (e.stderr or b"").decode(errors="replace").lower()
            if "permission" in stderr or "not permitted" in stderr or e.returncode in (1, 255):
                raise PermissionError(
                    "Screen capture failed — Screen Recording permission may not be granted. "
                    "Go to System Settings > Privacy & Security > Screen Recording and enable "
                    "access for this application."
                ) from e
            raise RuntimeError(
                f"screencapture exited with code {e.returncode}: "
                f"{(e.stderr or b'').decode(errors='replace').strip()}"
            ) from e

    if is_windows():
        path_lit = json.dumps(out)
        ps = f"""
Add-Type -AssemblyName System.Windows.Forms,System.Drawing
$bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
$bmp = New-Object System.Drawing.Bitmap $bounds.Width, $bounds.Height
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($bounds.Location, [System.Drawing.Point]::Empty, $bounds.Size)
$bmp.Save({path_lit}, [System.Drawing.Imaging.ImageFormat]::Png)
$g.Dispose(); $bmp.Dispose()
"""
        try:
            subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps],
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as e:
            raise RuntimeError(
                f"Windows screen capture failed (exit {e.returncode}): {e.stderr.strip()}"
            ) from e
        return out

    raise NotImplementedError("Screen capture not implemented for this platform.")


def capture_focused_window_to_file(path: Optional[str] = None) -> str:
    """
    Capture only the frontmost window on macOS.
    Falls back to full display capture if window capture fails.

    Raises:
        PermissionError  — screen-recording permission not granted
        RuntimeError     — capture failed for another reason
    """
    out = path or str(Path(tempfile.gettempdir()) / "startup_window_capture.png")

    if is_mac():
        try:
            # Get the frontmost window ID via AppleScript, then capture by window ID.
            wid_result = subprocess.run(
                ["osascript", "-e",
                 'tell application "System Events" to tell (first process whose frontmost is true) '
                 'to id of front window'],
                capture_output=True, text=True, timeout=3,
            )
            wid = wid_result.stdout.strip()

            if wid and wid.isdigit():
                subprocess.run(
                    ["screencapture", "-x", "-l", wid, out],
                    check=True, capture_output=True, timeout=10,
                )
                if Path(out).is_file():
                    return out
        except subprocess.CalledProcessError:
            # Window capture failed (permission or no window) — fall through to full display
            pass
        except Exception:
            pass

        # Fallback: full display — propagates PermissionError if also blocked
        return capture_primary_display_to_file(out)

    # Non-mac: full display
    return capture_primary_display_to_file(out)

