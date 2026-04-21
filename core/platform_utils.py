import sys
import os

def is_mac() -> bool:
    return sys.platform == "darwin"

def is_windows() -> bool:
    return sys.platform == "win32"

def is_linux() -> bool:
    return sys.platform.startswith("linux")

def get_platform() -> str:
    if is_mac():     return "mac"
    if is_windows(): return "windows"
    return "linux"

def get_downloads() -> str:
    return os.path.expanduser("~/Downloads")

def get_desktop() -> str:
    return os.path.expanduser("~/Desktop")

def get_documents() -> str:
    return os.path.expanduser("~/Documents")