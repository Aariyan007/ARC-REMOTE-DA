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
    """
    out = path or str(Path(tempfile.gettempdir()) / "startup_screen_capture.png")

    if is_mac():
        subprocess.run(["screencapture", "-x", out], check=True, capture_output=True)
        return out

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
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            check=True,
            capture_output=True,
            text=True,
        )
        return out

    raise NotImplementedError("Screen capture not implemented for this platform.")


def capture_focused_window_to_file(path: Optional[str] = None) -> str:
    """
    Capture only the frontmost window on macOS.
    Falls back to full display capture if window capture fails.
    """
    out = path or str(Path(tempfile.gettempdir()) / "startup_window_capture.png")

    if is_mac():
        try:
            # -l <windowid> requires the window id; -w captures frontmost window interactively.
            # Use -o to capture only the front window without shadow.
            # screencapture -x -o -w does interactive pick, so instead we use:
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
        except Exception:
            pass

        # Fallback: full display
        return capture_primary_display_to_file(out)

    # Non-mac: full display
    return capture_primary_display_to_file(out)
