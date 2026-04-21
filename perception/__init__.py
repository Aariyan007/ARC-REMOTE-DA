"""Perception stack: screen, OCR, browser, and accessibility (native first, vision fallback)."""

from .screen_capture import capture_primary_display_to_file, capture_focused_window_to_file
from .browser_state import (
    BrowserTabState, BrowserSnapshot,
    get_browser_tabs, get_browser_tabs_placeholder,
    get_active_tab_state, get_page_text_snippet, element_exists,
)
from .ui_accessibility import (
    AXNodeSummary, AXSnapshot,
    get_ax_snapshot, get_frontmost_app, get_focused_window_title,
    is_app_running, get_running_apps, snapshot_to_text,
)
from .ocr import OCRResult, ocr_image_file, ocr_screen, ocr_focused_window

__all__ = [
    # Screen capture
    "capture_primary_display_to_file",
    "capture_focused_window_to_file",
    # Browser
    "BrowserTabState",
    "BrowserSnapshot",
    "get_browser_tabs",
    "get_browser_tabs_placeholder",
    "get_active_tab_state",
    "get_page_text_snippet",
    "element_exists",
    # Accessibility
    "AXNodeSummary",
    "AXSnapshot",
    "get_ax_snapshot",
    "get_frontmost_app",
    "get_focused_window_title",
    "is_app_running",
    "get_running_apps",
    "snapshot_to_text",
    # OCR
    "OCRResult",
    "ocr_image_file",
    "ocr_screen",
    "ocr_focused_window",
]
