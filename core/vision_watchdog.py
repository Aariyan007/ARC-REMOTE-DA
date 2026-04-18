"""
Vision Watchdog — Screenshot context for ambiguous commands.

When a command has low confidence (0.40-0.70), takes a silent screenshot
and sends it to Gemini Vision to understand what the user is looking at.

Uses: gemini-2.0-flash (vision-capable model)
"""

import os
import time
import json
import subprocess
import tempfile
from typing import Optional
from dotenv import load_dotenv

load_dotenv()


# ── Settings ─────────────────────────────────────────────────
VISION_MODEL = "gemini-2.0-flash"
SCREENSHOT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "data", "screenshots"
)
# ─────────────────────────────────────────────────────────────


class VisionWatchdog:
    """
    Silent screenshot + Gemini vision for ambiguous commands.

    Usage:
        watchdog = VisionWatchdog()
        context = watchdog.get_screen_context("what is this app")
        # Returns: {"active_app": "VSCode", "content_type": "code", ...}
    """

    def __init__(self):
        os.makedirs(SCREENSHOT_DIR, exist_ok=True)
        self._client = None

    def _get_client(self):
        """Lazy-load Gemini client."""
        if self._client is None:
            from google import genai
            self._client = genai.Client(api_key=os.getenv("API_KEY"))
        return self._client

    def capture_screen(self) -> Optional[str]:
        """
        Take a silent screenshot. Returns path to the image file.

        Uses:
            - macOS: screencapture (built-in)
            - Fallback: mss library
        """
        timestamp = int(time.time())
        path = os.path.join(SCREENSHOT_DIR, f"screen_{timestamp}.png")

        try:
            # macOS native screenshot (silent, no UI)
            result = subprocess.run(
                ["screencapture", "-x", "-C", path],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0 and os.path.exists(path):
                return path
        except FileNotFoundError:
            pass  # Not macOS

        # Fallback: mss library
        try:
            import mss
            with mss.mss() as sct:
                monitor = sct.monitors[1]  # Primary monitor
                screenshot = sct.grab(monitor)
                mss.tools.to_png(screenshot.rgb, screenshot.size, output=path)
                return path
        except Exception as e:
            print(f"[Vision] Screenshot failed: {e}")

        return None

    def get_screen_context(self, command: str) -> dict:
        """
        Take a screenshot and ask Gemini Vision to understand the context.

        Args:
            command: The user's command (for context)

        Returns:
            Dict with screen context info:
            {
                "active_app": "VSCode",
                "content_type": "python_code",
                "context": "User is editing a Python file",
                "suggested_intent": "take_screenshot" or None
            }
        """
        screenshot_path = self.capture_screen()
        if not screenshot_path:
            return {"error": "Could not capture screen"}

        try:
            client = self._get_client()

            # Read the screenshot
            with open(screenshot_path, "rb") as f:
                image_bytes = f.read()

            # Upload the image
            import io
            from google.genai import types

            prompt = f"""You are Jarvis's vision system. The user just said: "{command}"

Look at this screenshot and provide context to help understand their command.

Return ONLY a JSON object (no markdown):
{{
    "active_app": "name of the app in focus",
    "content_type": "what kind of content (code, document, browser, video, etc)",
    "context": "brief description of what's on screen (max 20 words)",
    "suggested_intent": "if you can determine what the user wants, suggest an intent from: take_screenshot, answer_question, move_window, resize_window, open_app, close_app, general_chat. Or null if unsure."
}}"""

            response = client.models.generate_content(
                model=VISION_MODEL,
                contents=[
                    prompt,
                    types.Part.from_bytes(data=image_bytes, mime_type="image/png"),
                ],
            )

            text = response.text.strip()
            clean = text.replace("```json", "").replace("```", "").strip()
            context = json.loads(clean)

            # Clean up screenshot (don't hoard disk space)
            try:
                os.remove(screenshot_path)
            except Exception:
                pass

            return context

        except Exception as e:
            print(f"[Vision] Gemini analysis failed: {e}")
            # Clean up
            try:
                os.remove(screenshot_path)
            except Exception:
                pass
            return {"error": str(e)}

    def enrich_command(self, command: str, context: dict) -> str:
        """
        Enrich a command with vision context for better routing.

        Args:
            command: Original command
            context: Output from get_screen_context()

        Returns:
            Enriched command string with context hints
        """
        if "error" in context:
            return command

        app = context.get("active_app", "")
        content = context.get("content_type", "")

        # Add context hints to the command
        enriched = command
        if app:
            enriched += f" [active_app: {app}]"
        if content:
            enriched += f" [content: {content}]"

        return enriched


# ── Singleton ────────────────────────────────────────────────
_watchdog = None

def get_vision_watchdog() -> VisionWatchdog:
    """Get or create the singleton VisionWatchdog."""
    global _watchdog
    if _watchdog is None:
        _watchdog = VisionWatchdog()
    return _watchdog


# ── Quick Test ───────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 50)
    print("  VISION WATCHDOG TEST")
    print("=" * 50)

    watchdog = VisionWatchdog()

    # Test screenshot
    print("\n-- Taking screenshot --")
    path = watchdog.capture_screen()
    if path:
        size = os.path.getsize(path)
        print(f"  Screenshot saved: {path} ({size} bytes)")
        os.remove(path)
    else:
        print("  Screenshot failed")

    print("\nDone. For full test with Gemini Vision, run:")
    print("  python -c \"from core.vision_watchdog import *; print(get_vision_watchdog().get_screen_context('what is this'))\"")
