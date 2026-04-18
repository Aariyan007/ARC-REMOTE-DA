"""
WindowAgent — Native window management for macOS.

Capabilities:
    - move_window:    Move app to left/right/center of screen
    - resize_window:  Resize app to percentage or fullscreen
    - tile_windows:   Side-by-side layout for two apps
    - snap_window:    Snap to edge (quarter/half)

Uses AppleScript for native macOS window control.
"""

import subprocess
import sys
from core.agents.base_agent import BaseAgent, AgentResult


class WindowAgent(BaseAgent):

    @property
    def name(self) -> str:
        return "window"

    @property
    def description(self) -> str:
        return (
            "Handles window management: moving, resizing, tiling, "
            "and snapping application windows on screen."
        )

    def __init__(self):
        super().__init__()
        self.register_action("move_window",   self._move_window)
        self.register_action("resize_window", self._resize_window)
        self.register_action("tile_windows",  self._tile_windows)

    @property
    def tools_description(self) -> str:
        return """Agent: window
Tools:
  - move_window(target, position)
    Moves a window to a screen position.
    REQUIRED: target (str) - app name e.g. "vscode", "chrome"
    REQUIRED: position (str) - "left", "right", "center", "top_left", "top_right", "bottom_left", "bottom_right"

  - resize_window(target, size)
    Resizes a window.
    REQUIRED: target (str) - app name
    REQUIRED: size (str) - "half", "full", "quarter", "75%", "50%", "25%"

  - tile_windows(left_app, right_app)
    Tiles two apps side by side.
    REQUIRED: left_app (str) - app for left half
    REQUIRED: right_app (str) - app for right half"""

    # ── Screen size helper ───────────────────────────────────
    def _get_screen_size(self) -> tuple:
        """Get main display resolution."""
        try:
            script = '''
            tell application "Finder"
                set _bounds to bounds of window of desktop
                return (item 3 of _bounds) & "," & (item 4 of _bounds)
            end tell'''
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True, text=True, timeout=5,
            )
            parts = result.stdout.strip().split(",")
            if len(parts) == 2:
                return int(parts[0].strip()), int(parts[1].strip())
        except Exception:
            pass
        return 1440, 900  # Fallback

    def _app_name_to_process(self, target: str) -> str:
        """Convert common nicknames to actual app process names."""
        aliases = {
            "vscode": "Visual Studio Code",
            "code": "Visual Studio Code",
            "vs code": "Visual Studio Code",
            "chrome": "Google Chrome",
            "firefox": "Firefox",
            "safari": "Safari",
            "terminal": "Terminal",
            "iterm": "iTerm2",
            "finder": "Finder",
            "slack": "Slack",
            "discord": "Discord",
            "spotify": "Spotify",
            "notes": "Notes",
            "messages": "Messages",
            "mail": "Mail",
        }
        return aliases.get(target.lower(), target)

    # ── Move Window ──────────────────────────────────────────
    def _move_window(self, params: dict) -> AgentResult:
        """Move a window to a screen position."""
        target = params.get("target", "")
        position = params.get("position", "left").lower()

        if not target:
            return AgentResult(
                success=False, action="move_window",
                error="No target app specified",
            )

        app_name = self._app_name_to_process(target)
        screen_w, screen_h = self._get_screen_size()

        # Calculate position bounds {x, y, width, height}
        positions = {
            "left":         (0, 0, screen_w // 2, screen_h),
            "right":        (screen_w // 2, 0, screen_w // 2, screen_h),
            "center":       (screen_w // 4, screen_h // 4, screen_w // 2, screen_h // 2),
            "top_left":     (0, 0, screen_w // 2, screen_h // 2),
            "top_right":    (screen_w // 2, 0, screen_w // 2, screen_h // 2),
            "bottom_left":  (0, screen_h // 2, screen_w // 2, screen_h // 2),
            "bottom_right": (screen_w // 2, screen_h // 2, screen_w // 2, screen_h // 2),
            "full":         (0, 0, screen_w, screen_h),
        }

        if position not in positions:
            return AgentResult(
                success=False, action="move_window",
                error=f"Unknown position: {position}. Use: {', '.join(positions.keys())}",
            )

        x, y, w, h = positions[position]

        try:
            script = f'''
            tell application "{app_name}"
                activate
                set bounds of front window to {{{x}, {y}, {x + w}, {y + h}}}
            end tell'''

            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True, text=True, timeout=5,
            )

            if result.returncode != 0:
                return AgentResult(
                    success=False, action="move_window",
                    error=f"Could not move {target}: {result.stderr.strip()}",
                )

            return AgentResult(
                success=True, action="move_window",
                result=f"Moved {target} to {position}",
                data={"app": target, "position": position},
            )
        except Exception as e:
            return AgentResult(
                success=False, action="move_window",
                error=f"Failed to move {target}: {e}",
            )

    # ── Resize Window ────────────────────────────────────────
    def _resize_window(self, params: dict) -> AgentResult:
        """Resize a window to a specific size."""
        target = params.get("target", "")
        size = params.get("size", "half").lower().replace("%", "")

        if not target:
            return AgentResult(
                success=False, action="resize_window",
                error="No target app specified",
            )

        app_name = self._app_name_to_process(target)
        screen_w, screen_h = self._get_screen_size()

        # Calculate size
        size_map = {
            "full": (0, 0, screen_w, screen_h),
            "half": (0, 0, screen_w // 2, screen_h),
            "50":   (0, 0, screen_w // 2, screen_h),
            "75":   (0, 0, int(screen_w * 0.75), screen_h),
            "25":   (0, 0, screen_w // 4, screen_h),
            "quarter": (0, 0, screen_w // 2, screen_h // 2),
        }

        bounds = size_map.get(size)
        if not bounds:
            # Try parsing as a number
            try:
                pct = int(size) / 100.0
                bounds = (0, 0, int(screen_w * pct), screen_h)
            except ValueError:
                return AgentResult(
                    success=False, action="resize_window",
                    error=f"Unknown size: {size}",
                )

        x, y, w, h = bounds

        try:
            script = f'''
            tell application "{app_name}"
                activate
                set bounds of front window to {{{x}, {y}, {x + w}, {y + h}}}
            end tell'''

            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True, text=True, timeout=5,
            )

            if result.returncode != 0:
                return AgentResult(
                    success=False, action="resize_window",
                    error=f"Could not resize {target}: {result.stderr.strip()}",
                )

            return AgentResult(
                success=True, action="resize_window",
                result=f"Resized {target} to {size}",
                data={"app": target, "size": size},
            )
        except Exception as e:
            return AgentResult(
                success=False, action="resize_window",
                error=f"Failed to resize {target}: {e}",
            )

    # ── Tile Windows ─────────────────────────────────────────
    def _tile_windows(self, params: dict) -> AgentResult:
        """Tile two apps side by side."""
        left_app  = params.get("left_app", "")
        right_app = params.get("right_app", "")

        if not left_app or not right_app:
            return AgentResult(
                success=False, action="tile_windows",
                error="Need both left_app and right_app",
            )

        # Move left app
        left_result = self._move_window({
            "target": left_app, "position": "left"
        })
        if not left_result.success:
            return left_result

        # Move right app
        right_result = self._move_window({
            "target": right_app, "position": "right"
        })
        if not right_result.success:
            return right_result

        return AgentResult(
            success=True, action="tile_windows",
            result=f"Tiled {left_app} (left) + {right_app} (right)",
            data={"left": left_app, "right": right_app},
        )


# ── Quick Test ───────────────────────────────────────────────
if __name__ == "__main__":
    agent = WindowAgent()
    print(f"Agent: {agent.name}")
    print(f"Actions: {list(agent._action_map.keys())}")
    print(f"\nTools:\n{agent.tools_description}")
