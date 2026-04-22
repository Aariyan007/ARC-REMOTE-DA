"""
ComputerUseAgent — High-level computer use agent.

Chains Vision + Mouse/Keyboard control to execute arbitrary UI tasks.

Capabilities:
- computer_use: Execute any multi-step UI task via Gemini Vision + pyautogui
- click_element: Find and click a named UI element
- type_into: Click a field and type text
- open_app_ui: Open any app via Spotlight
- navigate_url_ui: Navigate browser to URL via address bar
- whatsapp_send: Send a WhatsApp Web message
- gmail_search: Search Gmail for emails

Architecture:
  Goal → understand_screen() → execute action → verify → repeat
  Max 12 steps per task. Aborts on "done" or "impossible".
"""

import json
import time
import sys
from core.agents.base_agent import BaseAgent, AgentResult
from core.voice_response import speak


MAX_STEPS = 12  # Max see-act iterations per task
STEP_DELAY = 0.8  # Seconds between steps


class ComputerUseAgent(BaseAgent):

    @property
    def name(self) -> str:
        return "computer_use"

    @property
    def description(self) -> str:
        return (
            "Controls the computer like a human — moves mouse, clicks buttons, "
            "types text, navigates apps and websites visually. Use for tasks that "
            "require UI interaction: sending WhatsApp messages, searching Gmail, "
            "filling forms, clicking buttons in any app."
        )

    def __init__(self):
        super().__init__()
        self.register_action("computer_use",    self._computer_use_task)
        self.register_action("click_element",   self._click_element)
        self.register_action("type_into",       self._type_into)
        self.register_action("open_app_ui",     self._open_app_ui)
        self.register_action("navigate_url_ui", self._navigate_url_ui)
        self.register_action("whatsapp_send",   self._whatsapp_send)
        self.register_action("gmail_search",    self._gmail_search)
        self.register_action("gmail_open_url",  self._gmail_open_url)

    # ─── Main: See-Act Loop ───────────────────────────────────

    def _computer_use_task(self, params: dict) -> AgentResult:
        """
        Execute an arbitrary UI task via Gemini Vision + pyautogui.

        Params:
            instruction: Natural language goal ("Search Gmail for emails from mom")
            max_steps:   Override max iterations (default: MAX_STEPS)
            announce:    Speak progress updates? (default: False)
        """
        instruction = (
            params.get("instruction")
            or params.get("task")
            or params.get("query")
            or params.get("goal", "")
        ).strip()

        if not instruction:
            return AgentResult(
                success=False, action="computer_use",
                error="No instruction provided for computer use task",
            )

        max_steps = int(params.get("max_steps", MAX_STEPS))
        announce  = params.get("announce", False)

        if not self._check_available():
            return AgentResult(
                success=False, action="computer_use",
                error="Computer use not available (pyautogui not installed or permissions missing)",
            )

        if announce:
            speak(f"Working on it.")

        print(f"🖱️  ComputerUse: {instruction}")

        from perception.screen_reader import understand_screen, verify_screen_state
        from control.computer_use import (
            click, double_click, type_text, press_key, hotkey, scroll,
        )

        steps_taken = []
        last_action_desc = ""

        for step in range(max_steps):
            print(f"  Step {step + 1}/{max_steps}...")

            # Ask Gemini what to do next
            result = understand_screen(instruction)

            if not result.ok:
                return AgentResult(
                    success=False, action="computer_use",
                    error=f"Screen reader failed: {result.error}",
                    data={"steps": steps_taken},
                )

            try:
                action_data = json.loads(result.text)
            except json.JSONDecodeError:
                return AgentResult(
                    success=False, action="computer_use",
                    error=f"Invalid action response: {result.text[:100]}",
                )

            action_type = action_data.get("action", "")
            reason = action_data.get("reason", "")
            print(f"    Action: {action_type} — {reason}")

            if action_type == "done":
                progress = action_data.get("progress", "Task completed")
                print(f"  ✅ Done: {progress}")
                return AgentResult(
                    success=True, action="computer_use",
                    result=progress,
                    data={"steps": steps_taken, "steps_count": step + 1},
                )

            if action_type == "impossible":
                return AgentResult(
                    success=False, action="computer_use",
                    error=f"Task impossible from current screen: {reason}",
                    data={"steps": steps_taken},
                )

            # Execute the action
            ctrl_result = None

            if action_type == "click":
                x, y = int(action_data.get("x", 0)), int(action_data.get("y", 0))
                ctrl_result = click(x, y)
                last_action_desc = f"Clicked ({x},{y})"

            elif action_type == "double_click":
                x, y = int(action_data.get("x", 0)), int(action_data.get("y", 0))
                ctrl_result = double_click(x, y)
                last_action_desc = f"Double-clicked ({x},{y})"

            elif action_type == "type":
                text = action_data.get("text", "")
                ctrl_result = type_text(text)
                last_action_desc = f"Typed: {text[:20]}"

            elif action_type == "press_key":
                key = action_data.get("key", "enter")
                ctrl_result = press_key(key)
                last_action_desc = f"Pressed: {key}"

            elif action_type == "hotkey":
                keys = action_data.get("keys", [])
                if keys:
                    ctrl_result = hotkey(*keys)
                    last_action_desc = f"Hotkey: {'+'.join(keys)}"

            elif action_type == "scroll":
                x = int(action_data.get("x", 0))
                y = int(action_data.get("y", 0))
                direction = action_data.get("direction", "down")
                clicks = 3 if direction == "down" else -3
                ctrl_result = scroll(x, y, clicks)
                last_action_desc = f"Scrolled {direction}"

            else:
                print(f"    ⚠️  Unknown action type: {action_type}")
                continue

            steps_taken.append({
                "step": step + 1,
                "action": action_type,
                "reason": reason,
                "result": ctrl_result.message if ctrl_result and ctrl_result.ok else (ctrl_result.error if ctrl_result else "?"),
            })

            if ctrl_result and not ctrl_result.ok:
                print(f"    ⚠️  Action failed: {ctrl_result.error}")

            # Wait for UI to respond
            time.sleep(STEP_DELAY)

        return AgentResult(
            success=False, action="computer_use",
            error=f"Max steps ({max_steps}) reached without completing task",
            data={"steps": steps_taken, "last_action": last_action_desc},
        )

    # ─── Targeted Helpers ────────────────────────────────────

    def _click_element(self, params: dict) -> AgentResult:
        """Find and click a named UI element."""
        description = params.get("element") or params.get("target") or params.get("description", "")
        if not description:
            return AgentResult(success=False, action="click_element", error="No element description")

        if not self._check_available():
            return AgentResult(success=False, action="click_element", error="Computer use not available")

        from perception.screen_reader import find_and_click
        result = find_and_click(description)
        if result.ok:
            return AgentResult(
                success=True, action="click_element",
                result=f"Clicked: {description} at ({result.x}, {result.y})",
                data={"x": result.x, "y": result.y},
            )
        return AgentResult(success=False, action="click_element", error=result.error or result.text)

    def _type_into(self, params: dict) -> AgentResult:
        """Find a field, click it, and type text."""
        field = params.get("field") or params.get("element", "")
        text  = params.get("text") or params.get("content", "")

        if not text:
            return AgentResult(success=False, action="type_into", error="No text to type")

        if not self._check_available():
            return AgentResult(success=False, action="type_into", error="Computer use not available")

        from perception.screen_reader import find_and_click
        from control.computer_use import type_text, press_key
        import time

        if field:
            result = find_and_click(field)
            if not result.ok:
                return AgentResult(success=False, action="type_into",
                                   error=f"Could not find field: {field}")
            time.sleep(0.2)

        r = type_text(text)
        if r.ok:
            return AgentResult(
                success=True, action="type_into",
                result=f"Typed '{text[:30]}' into {field or 'focused field'}",
            )
        return AgentResult(success=False, action="type_into", error=r.error)

    def _open_app_ui(self, params: dict) -> AgentResult:
        """Open an app using Spotlight search."""
        app = (
            params.get("app") or params.get("target") or
            params.get("name") or params.get("application", "")
        ).strip()

        if not app:
            return AgentResult(success=False, action="open_app_ui", error="No app name")

        if not self._check_available():
            return AgentResult(success=False, action="open_app_ui", error="Computer use not available")

        from control.computer_use import open_app_via_spotlight
        r = open_app_via_spotlight(app)
        if r.ok:
            return AgentResult(
                success=True, action="open_app_ui",
                result=f"Opened {app}",
                data={"app": app},
            )
        return AgentResult(success=False, action="open_app_ui", error=r.error)

    def _navigate_url_ui(self, params: dict) -> AgentResult:
        """Navigate browser to URL via address bar."""
        url = params.get("url") or params.get("target", "")
        if not url:
            return AgentResult(success=False, action="navigate_url_ui", error="No URL")

        if not self._check_available():
            return AgentResult(success=False, action="navigate_url_ui", error="Computer use not available")

        from control.computer_use import navigate_browser_to
        r = navigate_browser_to(url)
        if r.ok:
            return AgentResult(
                success=True, action="navigate_url_ui",
                result=f"Navigated to {url}",
                data={"url": url},
            )
        return AgentResult(success=False, action="navigate_url_ui", error=r.error)

    def _whatsapp_send(self, params: dict) -> AgentResult:
        """
        Send a WhatsApp message via WhatsApp Web.

        Params:
            contact: Name of the contact
            message: Message text to send
        """
        contact = params.get("contact") or params.get("to") or params.get("target", "")
        message = params.get("message") or params.get("text") or params.get("content", "")

        if not contact:
            return AgentResult(success=False, action="whatsapp_send", error="No contact specified")
        if not message:
            return AgentResult(success=False, action="whatsapp_send", error="No message to send")

        if not self._check_available():
            return AgentResult(success=False, action="whatsapp_send", error="Computer use not available")

        speak(f"Opening WhatsApp to message {contact}.")

        return self._computer_use_task({
            "instruction": (
                f"Send a WhatsApp Web message to my contact named '{contact}'. "
                f"The message is: '{message}'. "
                f"Steps: 1) Make sure web.whatsapp.com is open in the browser, navigate there if not. "
                f"2) Find {contact} in the left sidebar search. "
                f"3) Click on {contact}'s chat. "
                f"4) Type the message in the message box. "
                f"5) Press Enter to send. Done when message appears sent."
            ),
            "max_steps": 15,
            "announce": False,
        })

    def _gmail_search(self, params: dict) -> AgentResult:
        """
        Search Gmail for emails matching a query.

        Params:
            query: Search query (e.g. "from:mom", "about project")
        """
        query = (
            params.get("query") or params.get("search") or
            params.get("filter", "")
        ).strip()

        if not query:
            return AgentResult(success=False, action="gmail_search", error="No search query")

        if not self._check_available():
            return AgentResult(success=False, action="gmail_search", error="Computer use not available")

        speak(f"Searching Gmail for {query}.")

        return self._computer_use_task({
            "instruction": (
                f"Search Gmail for: '{query}'. "
                f"Steps: 1) Open gmail.com in the browser if not already open. "
                f"2) Find the Gmail search bar at the top. "
                f"3) Click the search bar. "
                f"4) Type the search query: '{query}'. "
                f"5) Press Enter. "
                f"Done when search results for '{query}' are visible."
            ),
            "max_steps": 10,
        })

    def _gmail_open_url(self, params: dict) -> AgentResult:
        """Navigate to gmail.com."""
        if not self._check_available():
            return AgentResult(success=False, action="gmail_open_url", error="Computer use not available")

        from control.computer_use import navigate_browser_to
        r = navigate_browser_to("https://gmail.com")
        if r.ok:
            time.sleep(2)  # Let Gmail load
            return AgentResult(success=True, action="gmail_open_url", result="Opened Gmail")
        return AgentResult(success=False, action="gmail_open_url", error=r.error)

    # ─── Utilities ───────────────────────────────────────────

    def _check_available(self) -> bool:
        """Verify pyautogui is available."""
        try:
            from control.computer_use import is_available
            return is_available()
        except Exception:
            return False
