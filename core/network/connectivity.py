"""
Connectivity Check — ensures Jarvis tells the user to connect to the internet
rather than failing silently or hanging.

Used by:
- ManagerAgent before dispatching to Gemini
- WebScrapingAgent before fetching URLs
- EmailAgent before sending/reading emails
- BackgroundGemini before enhancement calls
"""

import socket
import time
from typing import Tuple


# ─── Settings ────────────────────────────────────────────────
CHECK_HOST     = "8.8.8.8"       # Google DNS
CHECK_PORT     = 53               # DNS port
CHECK_TIMEOUT  = 3.0              # seconds
CACHE_DURATION = 30.0             # Cache result for 30 seconds
# ─────────────────────────────────────────────────────────────

_last_check_time   = 0.0
_last_check_result = False


def is_online(use_cache: bool = True) -> bool:
    """
    Checks if the system has internet connectivity.
    Caches the result to avoid hammering the network on every call.

    Returns True if online, False if offline.
    """
    global _last_check_time, _last_check_result

    now = time.time()
    if use_cache and (now - _last_check_time) < CACHE_DURATION:
        return _last_check_result

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(CHECK_TIMEOUT)
        sock.connect((CHECK_HOST, CHECK_PORT))
        sock.close()
        _last_check_result = True
    except (socket.timeout, socket.error, OSError):
        _last_check_result = False

    _last_check_time = now
    return _last_check_result


def require_online(speak_func=None) -> bool:
    """
    Checks connectivity. If offline, speaks a message to the user.
    Returns True if online, False if offline (and message was spoken).

    Usage:
        if not require_online(speak):
            return  # Jarvis already told the user to connect
    """
    if is_online():
        return True

    message = "I need an internet connection for that. Please connect to the internet and try again."
    print(f"🌐 Offline — cannot proceed")

    if speak_func:
        speak_func(message)
    else:
        print(f"🔊 {message}")

    return False


def get_connection_status() -> Tuple[bool, float]:
    """
    Returns (is_online, latency_ms).
    Useful for deciding whether to use local-first or cloud fallback.
    """
    start = time.time()
    online = is_online(use_cache=False)
    latency = (time.time() - start) * 1000
    return online, latency


# ─── Quick test ──────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("  CONNECTIVITY CHECK TEST")
    print("=" * 60)

    online, latency = get_connection_status()
    print(f"  Online: {online}")
    print(f"  Latency: {latency:.1f}ms")

    # Test cached check
    start = time.time()
    cached_result = is_online(use_cache=True)
    cached_time = (time.time() - start) * 1000
    print(f"  Cached check: {cached_result} ({cached_time:.2f}ms)")

    # Test require_online
    result = require_online()
    print(f"  require_online: {result}")

    print("\n✅ Connectivity check passed!")
