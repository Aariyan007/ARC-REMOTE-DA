"""
Perception Engine — Cross-platform system state sensing.

Runs as a background daemon thread, polling system state every N seconds.
Publishes perception_update events to the EventBus.

Collects:
    - Active foreground application name
    - System idle time (seconds since last user input)
    - Time of day
    - System state classification: coding, browsing, idle, media, unknown
    - User behavior patterns (session duration, app switch frequency)

Platform support:
    - Windows: pywin32 (win32gui, win32process) + psutil + ctypes
    - macOS:   osascript (AppleScript) + ioreg
"""

import sys
import time
import threading
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from collections import deque


# ─── Perception State ────────────────────────────────────────
@dataclass
class PerceptionState:
    """Snapshot of the user's current system state."""
    active_app:      str   = ""          # e.g., "Code", "chrome", "Spotify"
    active_window:   str   = ""          # Window title
    idle_seconds:    float = 0.0         # Seconds since last input
    time_of_day:     str   = ""          # "morning", "afternoon", "evening", "night"
    hour:            int   = 0           # Current hour (0-23)
    system_state:    str   = "unknown"   # coding, browsing, idle, media, unknown
    session_start:   float = 0.0        # When user started current app session
    session_duration: float = 0.0       # How long in current app (seconds)
    app_switches:    int   = 0           # App switches in last 10 minutes
    timestamp:       float = 0.0        # When this state was captured

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = time.time()


# ─── App Classification Rules ────────────────────────────────
CODING_APPS = {
    "code", "visual studio code", "vscode", "pycharm", "intellij",
    "webstorm", "sublime_text", "sublime text", "atom", "vim", "nvim",
    "neovim", "emacs", "xcode", "android studio", "cursor",
    "windowsterminal", "terminal", "iterm2", "warp", "cmd", "powershell",
    "pwsh", "alacritty", "hyper", "wt",
}

BROWSER_APPS = {
    "chrome", "google chrome", "firefox", "safari", "edge",
    "microsoft edge", "msedge", "brave", "opera", "arc", "vivaldi",
}

MEDIA_APPS = {
    "spotify", "music", "apple music", "vlc", "iina", "mpv",
    "youtube music", "netflix", "prime video", "disney+",
    "quicktime player", "photos", "preview",
}

COMMUNICATION_APPS = {
    "slack", "discord", "teams", "microsoft teams", "zoom", "telegram",
    "whatsapp", "messages", "mail", "outlook", "thunderbird",
}


def _classify_app(app_name: str) -> str:
    """Classifies an app name into a system state."""
    if not app_name:
        return "unknown"

    app_lower = app_name.lower().strip()

    # Check each category
    for coding_app in CODING_APPS:
        if coding_app in app_lower or app_lower in coding_app:
            return "coding"

    for browser_app in BROWSER_APPS:
        if browser_app in app_lower or app_lower in browser_app:
            return "browsing"

    for media_app in MEDIA_APPS:
        if media_app in app_lower or app_lower in media_app:
            return "media"

    for comm_app in COMMUNICATION_APPS:
        if comm_app in app_lower or app_lower in comm_app:
            return "communication"

    return "unknown"


def _get_time_of_day() -> tuple:
    """Returns (time_of_day_str, hour)."""
    hour = datetime.now().hour
    if 6 <= hour < 12:
        return "morning", hour
    elif 12 <= hour < 17:
        return "afternoon", hour
    elif 17 <= hour < 21:
        return "evening", hour
    else:
        return "night", hour


# ─── Platform: Windows ───────────────────────────────────────
def _get_active_app_windows() -> tuple:
    """Returns (app_name, window_title) on Windows."""
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32

        # Get foreground window handle
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return "", ""

        # Get window title
        length = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        window_title = buf.value

        # Get process ID from window handle
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

        # Get process name from PID
        try:
            import psutil
            proc = psutil.Process(pid.value)
            app_name = proc.name().replace(".exe", "")
        except Exception:
            app_name = window_title.split(" - ")[-1] if " - " in window_title else window_title

        return app_name, window_title

    except Exception as e:
        return "", ""


def _get_idle_time_windows() -> float:
    """Returns seconds since last user input on Windows."""
    try:
        import ctypes
        import ctypes.wintypes

        class LASTINPUTINFO(ctypes.Structure):
            _fields_ = [
                ("cbSize", ctypes.c_uint),
                ("dwTime", ctypes.c_uint),
            ]

        lii = LASTINPUTINFO()
        lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
        ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii))

        millis = ctypes.windll.kernel32.GetTickCount() - lii.dwTime
        return millis / 1000.0

    except Exception:
        return 0.0


# ─── Platform: macOS ─────────────────────────────────────────
def _get_active_app_mac() -> tuple:
    """Returns (app_name, window_title) on macOS."""
    try:
        # Get active app
        result = subprocess.run(
            ["osascript", "-e",
             'tell application "System Events" to name of first process whose frontmost is true'],
            capture_output=True, text=True, timeout=3
        )
        app_name = result.stdout.strip()

        # Get window title
        try:
            result2 = subprocess.run(
                ["osascript", "-e",
                 f'tell application "System Events" to tell process "{app_name}" '
                 f'to name of front window'],
                capture_output=True, text=True, timeout=3
            )
            window_title = result2.stdout.strip()
        except Exception:
            window_title = app_name

        return app_name, window_title

    except Exception:
        return "", ""


def _get_idle_time_mac() -> float:
    """Returns seconds since last user input on macOS."""
    try:
        result = subprocess.run(
            ["ioreg", "-c", "IOHIDSystem"],
            capture_output=True, text=True, timeout=3
        )
        for line in result.stdout.split("\n"):
            if "HIDIdleTime" in line:
                # Extract nanoseconds value
                parts = line.split("=")
                if len(parts) >= 2:
                    ns = int(parts[-1].strip())
                    return ns / 1_000_000_000.0
        return 0.0
    except Exception:
        return 0.0


# ─── Perception Engine ───────────────────────────────────────
class PerceptionEngine:
    """
    Background daemon that continuously senses system state.

    Usage:
        engine = PerceptionEngine()
        engine.start()
        state = engine.get_state()  # PerceptionState
        engine.stop()
    """

    def __init__(self, poll_interval: float = 5.0):
        self._poll_interval = poll_interval
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._state = PerceptionState()
        self._lock = threading.Lock()

        # Tracking
        self._session_start = time.time()
        self._last_app = ""
        self._app_switch_times: deque = deque(maxlen=60)  # Last 60 switches

        # Platform-specific functions
        if sys.platform == "win32":
            self._get_active_app = _get_active_app_windows
            self._get_idle_time = _get_idle_time_windows
        elif sys.platform == "darwin":
            self._get_active_app = _get_active_app_mac
            self._get_idle_time = _get_idle_time_mac
        else:
            # Linux fallback (basic)
            self._get_active_app = lambda: ("", "")
            self._get_idle_time = lambda: 0.0

    def start(self) -> None:
        """Starts the background perception polling thread."""
        if self._running:
            return

        self._running = True
        self._session_start = time.time()
        self._thread = threading.Thread(
            target=self._poll_loop,
            daemon=True,
            name="jarvis_perception"
        )
        self._thread.start()
        print("👁️  PerceptionEngine started")

    def stop(self) -> None:
        """Stops the perception polling thread."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        print("👁️  PerceptionEngine stopped")

    def get_state(self) -> PerceptionState:
        """Returns the latest perception state snapshot."""
        with self._lock:
            return PerceptionState(
                active_app=self._state.active_app,
                active_window=self._state.active_window,
                idle_seconds=self._state.idle_seconds,
                time_of_day=self._state.time_of_day,
                hour=self._state.hour,
                system_state=self._state.system_state,
                session_start=self._state.session_start,
                session_duration=self._state.session_duration,
                app_switches=self._state.app_switches,
                timestamp=self._state.timestamp,
            )

    def _poll_loop(self) -> None:
        """Main polling loop — runs on background thread."""
        while self._running:
            try:
                self._update_state()
            except Exception as e:
                print(f"⚠️  PerceptionEngine poll error: {e}")

            time.sleep(self._poll_interval)

    def _update_state(self) -> None:
        """Polls system state and updates internal state."""
        # Get active app
        app_name, window_title = self._get_active_app()

        # Detect app switch
        if app_name and app_name != self._last_app:
            self._app_switch_times.append(time.time())
            self._session_start = time.time()
            self._last_app = app_name

        # Count app switches in last 10 minutes
        cutoff = time.time() - 600
        recent_switches = sum(1 for t in self._app_switch_times if t > cutoff)

        # Get idle time
        idle_sec = self._get_idle_time()

        # Time of day
        tod, hour = _get_time_of_day()

        # Classify system state
        if idle_sec > 300:  # >5 min idle
            system_state = "idle"
        else:
            system_state = _classify_app(app_name)

        # Session duration
        session_duration = time.time() - self._session_start

        # Build new state
        new_state = PerceptionState(
            active_app=app_name,
            active_window=window_title,
            idle_seconds=round(idle_sec, 1),
            time_of_day=tod,
            hour=hour,
            system_state=system_state,
            session_start=self._session_start,
            session_duration=round(session_duration, 1),
            app_switches=recent_switches,
        )

        # Update with lock
        with self._lock:
            self._state = new_state

        # Publish to event bus
        try:
            from core.event_bus import get_event_bus
            bus = get_event_bus()
            bus.publish("perception_update", {
                "active_app":      new_state.active_app,
                "active_window":   new_state.active_window,
                "idle_seconds":    new_state.idle_seconds,
                "time_of_day":     new_state.time_of_day,
                "system_state":    new_state.system_state,
                "session_duration": new_state.session_duration,
                "app_switches":    new_state.app_switches,
            }, source="perception_engine")
        except Exception:
            pass  # EventBus not initialized yet — skip silently

    @property
    def is_running(self) -> bool:
        return self._running


# ─── Singleton ───────────────────────────────────────────────
_engine_instance: Optional[PerceptionEngine] = None
_engine_lock = threading.Lock()


def get_perception_engine() -> PerceptionEngine:
    """Returns the global PerceptionEngine singleton."""
    global _engine_instance
    if _engine_instance is None:
        with _engine_lock:
            if _engine_instance is None:
                _engine_instance = PerceptionEngine()
    return _engine_instance


# ─── Quick Test ──────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("  PERCEPTION ENGINE TEST")
    print("=" * 60)

    engine = get_perception_engine()

    # Single poll test (no background thread)
    engine._update_state()
    state = engine.get_state()

    print(f"\n📱 Active App:      {state.active_app}")
    print(f"🪟  Window Title:   {state.active_window}")
    print(f"⏱️  Idle Seconds:    {state.idle_seconds}")
    print(f"🕐 Time of Day:     {state.time_of_day} (hour={state.hour})")
    print(f"🎯 System State:    {state.system_state}")
    print(f"📊 App Switches:    {state.app_switches}")

    # Background poll test
    print("\nStarting background polling (10 seconds)...")
    engine.start()
    time.sleep(10)

    state = engine.get_state()
    print(f"\nAfter 10s:")
    print(f"  App: {state.active_app}")
    print(f"  State: {state.system_state}")
    print(f"  Session: {state.session_duration:.0f}s")

    engine.stop()
    print("\n✅ PerceptionEngine test passed!")
