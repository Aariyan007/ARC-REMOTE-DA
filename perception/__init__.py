"""Perception stack: screen, OCR, browser, and accessibility (native first, vision fallback)."""

from .screen_capture import capture_primary_display_to_file
from .browser_state import BrowserTabState, get_browser_tabs, get_browser_tabs_placeholder

__all__ = [
    "capture_primary_display_to_file",
    "BrowserTabState",
    "get_browser_tabs",
    "get_browser_tabs_placeholder",
]
