"""
Screen Reader — Gemini Vision layer for understanding what's on screen.

Answers questions like:
  "Where is the search bar?"
  "What is the text in the address bar?"
  "Is there a 'Send' button visible?"
  "What app is open?"

Uses screenshot + Gemini Vision (multimodal) for accurate UI element location.
Returns coordinates for clicking, text for verification.

Priority:
  1. Gemini Vision (best accuracy for UI elements)
  2. AX tree fallback (if vision fails)
  3. OCR fallback (if AX fails)
"""

import os
import json
import time
from dataclasses import dataclass, field
from typing import Optional, Tuple

# ─── Settings ────────────────────────────────────────────────
GEMINI_API_KEY = os.getenv("API_KEY")
VISION_MODEL   = "gemini-2.5-flash"
MAX_RETRIES    = 2
# ─────────────────────────────────────────────────────────────


@dataclass
class ScreenReadResult:
    """Result of a screen reading operation."""
    ok: bool
    text: str = ""              # Extracted text or answer
    x: Optional[int] = None    # Element X coordinate (if found)
    y: Optional[int] = None    # Element Y coordinate (if found)
    confidence: float = 0.0    # 0.0-1.0
    error: str = ""
    raw_response: str = ""

    @property
    def has_location(self) -> bool:
        return self.x is not None and self.y is not None

    def coords(self) -> Optional[Tuple[int, int]]:
        if self.has_location:
            return (self.x, self.y)
        return None


def _get_client():
    """Lazy Gemini client."""
    if not GEMINI_API_KEY:
        return None
    try:
        from google import genai
        return genai.Client(api_key=GEMINI_API_KEY)
    except ImportError:
        return None


def _screenshot_bytes() -> Optional[bytes]:
    """Take a screenshot and return as PNG bytes."""
    try:
        from control.computer_use import take_screenshot_to_bytes
        return take_screenshot_to_bytes()
    except Exception as e:
        print(f"⚠️  Screen reader screenshot error: {e}")
        return None


def read_screen(prompt: str, include_screenshot: bool = True) -> ScreenReadResult:
    """
    Ask Gemini Vision about the current screen.

    Args:
        prompt: Natural language question about the screen.
                Example: "What app is currently open?"
        include_screenshot: Whether to include a screenshot.

    Returns:
        ScreenReadResult with text answer.
    """
    client = _get_client()
    if client is None:
        return ScreenReadResult(ok=False, error="Gemini client unavailable")

    try:
        contents = []

        if include_screenshot:
            img_bytes = _screenshot_bytes()
            if img_bytes:
                from google.genai import types as genai_types
                contents.append(
                    genai_types.Part.from_bytes(data=img_bytes, mime_type="image/png")
                )

        contents.append(prompt)

        response = client.models.generate_content(
            model=VISION_MODEL,
            contents=contents,
        )
        text = (response.text or "").strip()
        return ScreenReadResult(ok=True, text=text, raw_response=text)

    except Exception as e:
        return ScreenReadResult(ok=False, error=str(e))


def find_element(description: str, screen_width: int = None, screen_height: int = None) -> ScreenReadResult:
    """
    Find a UI element on screen and return its coordinates.

    Args:
        description: What to find. Example: "the search bar", "the Send button", "Gmail logo"
        screen_width/height: Used for coordinate validation.

    Returns:
        ScreenReadResult with x, y set if element found.
    """
    client = _get_client()
    if client is None:
        return ScreenReadResult(ok=False, error="Gemini client unavailable")

    img_bytes = _screenshot_bytes()
    if img_bytes is None:
        return ScreenReadResult(ok=False, error="Screenshot failed")

    if screen_width is None or screen_height is None:
        try:
            from control.computer_use import get_screen_size
            screen_width, screen_height = get_screen_size()
        except Exception:
            screen_width, screen_height = 1920, 1080

    prompt = f"""Look at this screenshot of a macOS desktop.

Find: {description}

The screen resolution is {screen_width}x{screen_height} pixels.

If you can see the element, respond with ONLY a JSON object like:
{{"found": true, "x": 500, "y": 300, "confidence": 0.9, "description": "brief description of what you found"}}

If you cannot find it, respond with:
{{"found": false, "x": null, "y": null, "confidence": 0.0, "description": "what you see instead"}}

Rules:
- x and y must be the CENTER of the element in pixels
- Do NOT wrap in markdown code blocks
- Return ONLY the JSON, nothing else"""

    for attempt in range(MAX_RETRIES):
        try:
            from google.genai import types as genai_types
            response = client.models.generate_content(
                model=VISION_MODEL,
                contents=[
                    genai_types.Part.from_bytes(data=img_bytes, mime_type="image/png"),
                    prompt,
                ],
            )
            raw = (response.text or "").strip()
            raw = raw.replace("```json", "").replace("```", "").strip()

            data = json.loads(raw)
            found = data.get("found", False)

            if found and data.get("x") is not None:
                x = int(data["x"])
                y = int(data["y"])
                # Clamp to screen bounds
                x = max(0, min(x, screen_width - 1))
                y = max(0, min(y, screen_height - 1))
                return ScreenReadResult(
                    ok=True,
                    x=x,
                    y=y,
                    confidence=float(data.get("confidence", 0.8)),
                    text=data.get("description", ""),
                    raw_response=raw,
                )
            else:
                return ScreenReadResult(
                    ok=False,
                    text=data.get("description", "Element not found"),
                    confidence=0.0,
                    raw_response=raw,
                )
        except json.JSONDecodeError:
            if attempt == MAX_RETRIES - 1:
                return ScreenReadResult(ok=False, error=f"Invalid JSON: {raw[:100]}")
            time.sleep(0.5)
        except Exception as e:
            return ScreenReadResult(ok=False, error=str(e))

    return ScreenReadResult(ok=False, error="Max retries exceeded")


def find_and_click(description: str) -> ScreenReadResult:
    """
    Find a UI element and click it in one call.
    Returns the result of the find operation (with click performed if found).
    """
    result = find_element(description)
    if result.ok and result.has_location:
        try:
            from control.computer_use import click
            click_result = click(result.x, result.y)
            if not click_result.ok:
                result.error = click_result.error
                result.ok = False
        except Exception as e:
            result.error = str(e)
            result.ok = False
    return result


def get_screen_text() -> str:
    """
    Get all visible text on screen via Gemini Vision.
    Useful for reading content, finding values, confirming state.
    """
    result = read_screen(
        "Please read and return ALL visible text on this screen, "
        "preserving the approximate layout. Include UI labels, button text, "
        "address bar content, and any body text."
    )
    return result.text if result.ok else ""


def understand_screen(goal: str) -> ScreenReadResult:
    """
    High-level: given a goal, tell ARC what to do next on the current screen.

    Returns ScreenReadResult.text with a structured action description.
    Example goal: "I need to search for emails from mom in Gmail"
    Returns: "Click the search bar at approximately the top of the screen (around y=100)"
    """
    client = _get_client()
    if client is None:
        return ScreenReadResult(ok=False, error="Gemini client unavailable")

    img_bytes = _screenshot_bytes()
    if img_bytes is None:
        return ScreenReadResult(ok=False, error="Screenshot failed")

    try:
        from control.computer_use import get_screen_size
        w, h = get_screen_size()
    except Exception:
        w, h = 1920, 1080

    prompt = f"""You are controlling a macOS computer for the user.

Screen resolution: {w}x{h} pixels
User's goal: {goal}

Look at this screenshot and tell me EXACTLY what single action to take next to progress toward the goal.

Respond with ONLY JSON (no markdown):
{{
  "action": "click" | "type" | "press_key" | "hotkey" | "scroll" | "done" | "impossible",
  "x": <int or null>,
  "y": <int or null>,
  "text": "<text to type, if action is type>",
  "key": "<key name, if action is press_key>",
  "keys": ["<key1>", "<key2>"], /* if action is hotkey */
  "direction": "up" | "down" | null, /* if action is scroll */
  "reason": "<brief explanation of why this action>",
  "progress": "<what the goal state will look like after this action>"
}}

Rules:
- If goal is already achieved, use "done"
- If impossible from current screen, use "impossible"
- Be SPECIFIC about coordinates
- x,y must be exact pixel positions of the center of the target element"""

    try:
        from google.genai import types as genai_types
        response = client.models.generate_content(
            model=VISION_MODEL,
            contents=[
                genai_types.Part.from_bytes(data=img_bytes, mime_type="image/png"),
                prompt,
            ],
        )
        raw = (response.text or "").strip()
        raw = raw.replace("```json", "").replace("```", "").strip()
        data = json.loads(raw)

        return ScreenReadResult(
            ok=True,
            text=json.dumps(data),
            x=int(data["x"]) if data.get("x") is not None else None,
            y=int(data["y"]) if data.get("y") is not None else None,
            confidence=1.0,
            raw_response=raw,
        )
    except json.JSONDecodeError:
        return ScreenReadResult(ok=False, error=f"Non-JSON response: {raw[:100]}")
    except Exception as e:
        return ScreenReadResult(ok=False, error=str(e))


def verify_screen_state(expected_description: str) -> bool:
    """
    Check if the screen matches an expected description.
    Example: "Gmail is open and the inbox is visible"
    Returns True if the description matches current screen.
    """
    result = read_screen(
        f"Does the current screen match this description: '{expected_description}'?\n"
        f"Answer with ONLY 'yes' or 'no', nothing else."
    )
    if result.ok:
        return result.text.strip().lower().startswith("yes")
    return False
