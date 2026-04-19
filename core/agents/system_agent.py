"""
SystemControlAgent — handles all system-level operations.

Capabilities:
- Volume: up, down, mute, unmute, get_volume
- Brightness: up, down
- Screen: lock, screenshot, fullscreen, show_desktop, mission_control
- Power: shutdown, restart, sleep
- Apps: open, close, switch, minimize
- Battery: get_battery
- Window management: minimize_all, close_window, close_tab, new_tab
- Routines: start_work_day, end_work_day

This agent ONLY has access to system tools.
It cannot read files, send emails, or browse the web.
"""

from core.agents.base_agent import BaseAgent, AgentResult


class SystemControlAgent(BaseAgent):

    @property
    def name(self) -> str:
        return "system"

    @property
    def description(self) -> str:
        return (
            "Handles all system-level operations: volume, brightness, "
            "screen control, power management, app launching/closing, "
            "battery status, window management, and work routines."
        )

    def __init__(self, actions_map: dict = None):
        """
        Args:
            actions_map: The global ACTIONS dict from main.py
        """
        super().__init__()
        self._actions = actions_map or {}

        # ── Volume ───────────────────────────────────────────
        self.register_action("volume_up",       self._volume_up)
        self.register_action("volume_down",     self._volume_down)
        self.register_action("mute",            self._simple_action)
        self.register_action("unmute",          self._simple_action)
        self.register_action("get_volume",      self._simple_action)

        # ── Brightness ───────────────────────────────────────
        self.register_action("brightness_up",   self._brightness_up)
        self.register_action("brightness_down", self._brightness_down)

        # ── Screen ───────────────────────────────────────────
        self.register_action("lock_screen",     self._simple_action)
        self.register_action("take_screenshot", self._simple_action)
        self.register_action("fullscreen",      self._simple_action)
        self.register_action("show_desktop",    self._simple_action)
        self.register_action("mission_control", self._simple_action)

        # ── Power ────────────────────────────────────────────
        self.register_action("shutdown_pc",     self._simple_action)
        self.register_action("restart_pc",      self._simple_action)
        self.register_action("sleep_mac",       self._simple_action)

        # ── Apps ─────────────────────────────────────────────
        self.register_action("open_app",        self._open_app)
        self.register_action("close_app",       self._targeted_action)
        self.register_action("switch_to_app",   self._targeted_action)
        self.register_action("minimise_app",    self._targeted_action)

        # ── Battery ──────────────────────────────────────────
        self.register_action("get_battery",     self._get_battery)

        # ── Windows ──────────────────────────────────────────
        self.register_action("minimise_all",    self._simple_action)
        self.register_action("close_window",    self._simple_action)
        self.register_action("close_tab",       self._simple_action)
        self.register_action("new_tab",         self._simple_action)

        # ── Playwright browser (DOM automation) ─────────────
        self.register_action("open_url",        self._open_url)
        self.register_action("web_back",        self._simple_action)
        self.register_action("web_refresh",     self._simple_action)
        self.register_action("web_new_tab",     self._simple_action)
        self.register_action("web_close_tab",   self._simple_action)

        # ── Routines ─────────────────────────────────────────
        self.register_action("start_work_day",  self._simple_action)
        self.register_action("end_work_day",    self._simple_action)

    # ── Volume ───────────────────────────────────────────────
    def _volume_up(self, params: dict) -> AgentResult:
        """Increases system volume by the specified amount (default 10)."""
        amount = params.get("amount", 10)
        if "volume_up" in self._actions:
            self._actions["volume_up"](amount)
            return AgentResult(
                success=True, action="volume_up",
                result=f"Volume up by {amount}",
                data={"amount": amount},
            )
        return AgentResult(success=False, action="volume_up", error="Not available")

    def _volume_down(self, params: dict) -> AgentResult:
        """Decreases system volume by the specified amount (default 10)."""
        amount = params.get("amount", 10)
        if "volume_down" in self._actions:
            self._actions["volume_down"](amount)
            return AgentResult(
                success=True, action="volume_down",
                result=f"Volume down by {amount}",
                data={"amount": amount},
            )
        return AgentResult(success=False, action="volume_down", error="Not available")

    # ── Brightness ───────────────────────────────────────────
    def _brightness_up(self, params: dict) -> AgentResult:
        """Increases screen brightness."""
        amount = params.get("amount", 10)
        if "brightness_up" in self._actions:
            self._actions["brightness_up"](amount)
            return AgentResult(
                success=True, action="brightness_up",
                result=f"Brightness up by {amount}",
            )
        return AgentResult(success=False, action="brightness_up", error="Not available")

    def _brightness_down(self, params: dict) -> AgentResult:
        """Decreases screen brightness."""
        amount = params.get("amount", 10)
        if "brightness_down" in self._actions:
            self._actions["brightness_down"](amount)
            return AgentResult(
                success=True, action="brightness_down",
                result=f"Brightness down by {amount}",
            )
        return AgentResult(success=False, action="brightness_down", error="Not available")

    # ── App Control ──────────────────────────────────────────
    def _open_app(self, params: dict) -> AgentResult:
        """Opens an application by name."""
        target = params.get("target", params.get("name", ""))
        if not target:
            return AgentResult(
                success=False, action="open_app",
                error="No app name provided",
            )

        func_name = f"open_{target.lower().replace(' ', '_')}"
        if func_name in self._actions:
            self._actions[func_name]()
            return AgentResult(
                success=True, action="open_app",
                result=f"Opened {target}",
                data={"app": target},
            )

        # Try generic open
        try:
            from control.mac.open_apps import open_any_app
            open_any_app(target)
            return AgentResult(
                success=True, action="open_app",
                result=f"Opened {target}",
                data={"app": target},
            )
        except Exception as e:
            return AgentResult(
                success=False, action="open_app", error=str(e),
            )

    def _targeted_action(self, params: dict) -> AgentResult:
        """Executes actions that need a target app (close, switch, minimize)."""
        # Determine which action this is from the call context
        # We need to identify the action name from the registered methods
        target = params.get("target", params.get("name", ""))
        action = params.get("_action_name", "")

        # Try each possible targeted action
        for action_name in ["close_app", "switch_to_app", "minimise_app"]:
            if action_name in self._actions and target:
                try:
                    self._actions[action_name](target)
                    return AgentResult(
                        success=True, action=action_name,
                        result=f"{action_name.replace('_', ' ').title()}: {target}",
                        data={"app": target},
                    )
                except Exception:
                    continue

        return AgentResult(
            success=False, action="targeted_action",
            error=f"Could not execute on target: {target}",
        )

    # ── Battery ──────────────────────────────────────────────
    def _open_url(self, params: dict) -> AgentResult:
        """Navigate the Playwright automation browser to a URL."""
        url = params.get("url", params.get("query", ""))
        if not url:
            return AgentResult(
                success=False, action="open_url",
                error="No URL provided",
            )
        try:
            from control.playwright_browser import navigate

            final = navigate(url)
            return AgentResult(
                success=True, action="open_url",
                result=f"Opened {final}",
                data={"url": final},
            )
        except Exception as e:
            return AgentResult(success=False, action="open_url", error=str(e))

    def _get_battery(self, params: dict) -> AgentResult:
        """Returns current battery percentage."""
        import subprocess, re
        try:
            result = subprocess.run(
                ["pmset", "-g", "batt"],
                capture_output=True, text=True,
            )
            match = re.search(r'(\d+)%', result.stdout)
            if match:
                pct = match.group(1)
                return AgentResult(
                    success=True, action="get_battery",
                    result=f"Battery is at {pct}%",
                    data={"battery_percent": int(pct)},
                )
            return AgentResult(
                success=False, action="get_battery",
                error="Couldn't read battery",
            )
        except Exception as e:
            return AgentResult(
                success=False, action="get_battery", error=str(e),
            )

    # ── Simple Actions (no params needed) ────────────────────
    def _simple_action(self, params: dict) -> AgentResult:
        """Executes a parameterless system action."""
        # Find which action was called
        # We use a trick: look up the action name from the registered map
        for action_name, method in self._action_map.items():
            if method == self._simple_action and action_name in self._actions:
                try:
                    result = self._actions[action_name]()
                    return AgentResult(
                        success=True, action=action_name,
                        result=f"Executed {action_name}" + (f": {result}" if result else ""),
                    )
                except Exception as e:
                    return AgentResult(
                        success=False, action=action_name, error=str(e),
                    )

        return AgentResult(
            success=False, action="unknown",
            error="Action not found in actions map",
        )

    # Override execute to properly route simple/targeted actions
    def execute(self, action: str, params: dict) -> AgentResult:
        """Routes action to the correct handler with proper context."""
        # For simple actions, call the action directly from ACTIONS map
        simple_actions = {
            "mute", "unmute", "get_volume", "lock_screen",
            "take_screenshot", "fullscreen", "show_desktop",
            "mission_control", "shutdown_pc", "restart_pc",
            "sleep_mac", "minimise_all", "close_window",
            "close_tab", "new_tab", "start_work_day", "end_work_day",
            "web_back", "web_refresh", "web_new_tab", "web_close_tab",
        }

        if action == "open_url":
            return self._open_url(params)

        if action in simple_actions:
            if action in self._actions:
                try:
                    result = self._actions[action]()
                    return AgentResult(
                        success=True, action=action,
                        result=f"Executed {action}" + (f": {result}" if result else ""),
                    )
                except Exception as e:
                    return AgentResult(
                        success=False, action=action, error=str(e),
                    )
            return AgentResult(
                success=False, action=action,
                error=f"Action '{action}' not in ACTIONS map",
            )

        # For targeted actions (close_app, switch_to_app, minimise_app)
        if action in ("close_app", "switch_to_app", "minimise_app"):
            target = params.get("target", params.get("name", ""))
            if action in self._actions and target:
                try:
                    self._actions[action](target)
                    return AgentResult(
                        success=True, action=action,
                        result=f"{action}: {target}",
                        data={"app": target},
                    )
                except Exception as e:
                    return AgentResult(
                        success=False, action=action, error=str(e),
                    )
            return AgentResult(
                success=False, action=action,
                error=f"No target provided for {action}",
            )

        # Fall through to base class for volume/brightness/etc.
        return super().execute(action, params)
