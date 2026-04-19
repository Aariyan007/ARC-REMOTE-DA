"""Windows — browser automation via shared Playwright layer."""

from control.playwright_browser import (
    action_web_back,
    action_web_close_tab,
    action_web_new_tab,
    action_web_refresh,
    close_tab,
    dispatch,
    get_tabs,
    go_back,
    navigate,
    new_tab,
    refresh,
    search_google_in_browser,
)

__all__ = [
    "navigate",
    "new_tab",
    "close_tab",
    "go_back",
    "refresh",
    "get_tabs",
    "search_google_in_browser",
    "dispatch",
    "action_web_back",
    "action_web_refresh",
    "action_web_new_tab",
    "action_web_close_tab",
]
