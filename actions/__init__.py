"""Action facades: thin entry points over control/* and future Playwright / AX bridges."""

from actions.browser import BrowserActionError, dispatch_browser_action
from actions.system import dispatch_system_action

__all__ = [
    "BrowserActionError",
    "dispatch_browser_action",
    "dispatch_system_action",
]
