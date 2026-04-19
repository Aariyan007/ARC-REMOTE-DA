"""
OCR for screenshots: Pillow + pytesseract when available, else Tesseract CLI.

macOS Vision bridge can replace this later for zero-Homebrew setups.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def ocr_image_file(image_path: str) -> str:
    path = Path(image_path)
    if not path.is_file():
        raise FileNotFoundError(image_path)

    try:
        import pytesseract
        from PIL import Image

        text = pytesseract.image_to_string(Image.open(path))
        if text and text.strip():
            return text.strip()
    except ImportError:
        pass
    except Exception:
        pass

    tess = shutil.which("tesseract")
    if tess:
        result = subprocess.run(
            [tess, str(path), "stdout"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0 and (result.stdout or "").strip():
            return result.stdout.strip()

    raise RuntimeError(
        "OCR unavailable: install Tesseract (e.g. brew install tesseract) "
        "and pip install pytesseract pillow, or ensure `tesseract` is on PATH."
    )
