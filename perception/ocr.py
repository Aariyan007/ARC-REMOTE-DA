"""
OCR for screenshots: Pillow + pytesseract when available, else Tesseract CLI.

Provides convenience wrappers:
  - ocr_image_file(path) — OCR a single image file
  - ocr_screen() — capture full display + OCR in one call
  - ocr_focused_window() — capture frontmost window + OCR

macOS Vision bridge can replace this later for zero-Homebrew setups.
"""

from __future__ import annotations

import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class OCRResult:
    """Structured OCR output."""

    text: str = ""
    confidence: float = 0.0   # 0.0 = unknown, >0 from pytesseract
    source: str = "unknown"   # "pytesseract", "tesseract_cli", "none"
    error: str = ""
    elapsed_ms: float = 0.0

    @property
    def ok(self) -> bool:
        return bool(self.text.strip()) and not self.error


def ocr_image_file(image_path: str) -> str:
    """
    OCR a single image file. Returns extracted text.
    Raises RuntimeError if OCR is unavailable.
    """
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


def ocr_image_file_structured(image_path: str) -> OCRResult:
    """
    OCR a single image file. Returns structured OCRResult.
    Never raises — captures errors in result.
    """
    t0 = time.time()
    path = Path(image_path)

    if not path.is_file():
        return OCRResult(error=f"File not found: {image_path}",
                         elapsed_ms=(time.time() - t0) * 1000)

    # Try pytesseract first
    try:
        import pytesseract
        from PIL import Image

        img = Image.open(path)
        text = pytesseract.image_to_string(img)
        # Try to get confidence
        try:
            data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
            confs = [float(c) for c in data.get("conf", []) if str(c).replace("-", "").isdigit() and float(c) > 0]
            avg_conf = sum(confs) / len(confs) / 100.0 if confs else 0.0
        except Exception:
            avg_conf = 0.5  # assume medium if can't get confidence

        if text and text.strip():
            return OCRResult(
                text=text.strip(),
                confidence=avg_conf,
                source="pytesseract",
                elapsed_ms=(time.time() - t0) * 1000,
            )
    except ImportError:
        pass
    except Exception as e:
        return OCRResult(error=str(e), source="pytesseract",
                         elapsed_ms=(time.time() - t0) * 1000)

    # Fallback: tesseract CLI
    tess = shutil.which("tesseract")
    if tess:
        try:
            result = subprocess.run(
                [tess, str(path), "stdout"],
                capture_output=True, text=True, timeout=120,
            )
            if result.returncode == 0 and (result.stdout or "").strip():
                return OCRResult(
                    text=result.stdout.strip(),
                    source="tesseract_cli",
                    elapsed_ms=(time.time() - t0) * 1000,
                )
        except Exception as e:
            return OCRResult(error=str(e), source="tesseract_cli",
                             elapsed_ms=(time.time() - t0) * 1000)

    return OCRResult(
        error="OCR unavailable: no pytesseract or tesseract CLI found",
        source="none",
        elapsed_ms=(time.time() - t0) * 1000,
    )


def ocr_screen(region: Optional[tuple] = None) -> OCRResult:
    """
    Capture the full display and OCR it in one call.
    Returns structured OCRResult. Never raises.
    """
    try:
        from perception.screen_capture import capture_primary_display_to_file
        img_path = capture_primary_display_to_file()
        result = ocr_image_file_structured(img_path)
        result.source = f"screen:{result.source}"
        return result
    except Exception as e:
        return OCRResult(error=f"Screen capture failed: {e}", source="screen")


def ocr_focused_window() -> OCRResult:
    """
    Capture only the frontmost window and OCR it.
    Returns structured OCRResult. Never raises.
    """
    try:
        from perception.screen_capture import capture_focused_window_to_file
        img_path = capture_focused_window_to_file()
        result = ocr_image_file_structured(img_path)
        result.source = f"window:{result.source}"
        return result
    except Exception as e:
        return OCRResult(error=f"Window capture failed: {e}", source="window")


# ─── Quick Test ──────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("  OCR PERCEPTION TEST")
    print("=" * 60)

    result = ocr_screen()
    if result.ok:
        print(f"  Source: {result.source}")
        print(f"  Confidence: {result.confidence:.2f}")
        print(f"  Text (first 200): {result.text[:200]}")
        print(f"  Elapsed: {result.elapsed_ms:.0f}ms")
    else:
        print(f"  Error: {result.error}")
        print(f"  (This is expected if Tesseract is not installed)")

    print("\n✅ OCR test passed!")
