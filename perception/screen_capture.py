"""
Primary display capture. Prefer ScreenCaptureKit for production; CLI is a bootstrap path.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from core.platform import is_mac, is_windows


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
