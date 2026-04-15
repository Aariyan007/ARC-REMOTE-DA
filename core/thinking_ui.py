"""
Floating Thinking UI — shows Jarvis's internal state in real-time.

Displays:
  - Current command being processed
  - Detected intent / action
  - Confidence score
  - Pipeline stage

Runs in a separate daemon thread. Non-blocking.
Gracefully skips if Tkinter or display not available.
"""

import threading
import time
import sys

# ─── Availability check ─────────────────────────────────────
_tk_available = False
try:
    import tkinter as tk
    from tkinter import font as tkfont
    _tk_available = True
except ImportError:
    pass


class ThinkingUI:
    """
    Floating overlay window that shows Jarvis's thinking process.
    Thread-safe — call update() from any thread.
    """

    def __init__(self):
        self._root = None
        self._thread = None
        self._running = False
        self._pending_update = None
        self._lock = threading.Lock()
        self._last_update_time = 0
        self._auto_hide_seconds = 5

        # State
        self._command = ""
        self._intent = ""
        self._action = ""
        self._confidence = 0.0
        self._stage = ""

    def start(self):
        """Start the UI in a background thread."""
        if not _tk_available:
            print("⚠️  Tkinter not available — Thinking UI disabled")
            return

        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """Stop the UI."""
        self._running = False

    def update(self, command: str = "", intent: str = "", action: str = "",
               confidence: float = 0.0, stage: str = ""):
        """
        Update the UI state. Thread-safe.
        Call from route() or anywhere in the pipeline.
        """
        with self._lock:
            self._pending_update = {
                "command": command,
                "intent": intent,
                "action": action,
                "confidence": confidence,
                "stage": stage,
            }
            self._last_update_time = time.time()

    def _run_loop(self):
        """Main Tkinter loop — runs in its own thread."""
        try:
            self._root = tk.Tk()
            self._root.title("Jarvis • Thinking")
            self._root.overrideredirect(True)       # No title bar
            self._root.attributes("-topmost", True)  # Always on top

            # ── Transparency ─────────────────────────────────
            if sys.platform == "win32":
                self._root.attributes("-alpha", 0.92)
            elif sys.platform == "darwin":
                self._root.attributes("-alpha", 0.92)

            # ── Geometry — bottom-right corner ───────────────
            width, height = 380, 160
            screen_w = self._root.winfo_screenwidth()
            screen_h = self._root.winfo_screenheight()
            x = screen_w - width - 20
            y = screen_h - height - 60
            self._root.geometry(f"{width}x{height}+{x}+{y}")

            # ── Styling ──────────────────────────────────────
            bg_color = "#1a1a2e"
            fg_color = "#e0e0ff"
            accent   = "#7c3aed"
            dim      = "#6b7280"

            self._root.configure(bg=bg_color)

            # Try to use a modern font
            try:
                main_font = tkfont.Font(family="Segoe UI", size=10)
                title_font = tkfont.Font(family="Segoe UI", size=11, weight="bold")
                small_font = tkfont.Font(family="Segoe UI", size=9)
            except Exception:
                main_font = tkfont.Font(size=10)
                title_font = tkfont.Font(size=11, weight="bold")
                small_font = tkfont.Font(size=9)

            # ── Header ───────────────────────────────────────
            header = tk.Frame(self._root, bg=accent, height=28)
            header.pack(fill="x")
            header.pack_propagate(False)

            tk.Label(
                header, text="🧠  JARVIS THINKING", font=title_font,
                bg=accent, fg="white", anchor="w", padx=10
            ).pack(fill="x", expand=True)

            # ── Content frame ────────────────────────────────
            content = tk.Frame(self._root, bg=bg_color, padx=12, pady=8)
            content.pack(fill="both", expand=True)

            # Labels
            self._lbl_stage = tk.Label(
                content, text="⏳ Idle", font=small_font,
                bg=bg_color, fg=dim, anchor="w"
            )
            self._lbl_stage.pack(fill="x")

            self._lbl_command = tk.Label(
                content, text="📝 —", font=main_font,
                bg=bg_color, fg=fg_color, anchor="w", wraplength=350
            )
            self._lbl_command.pack(fill="x", pady=(4, 0))

            self._lbl_intent = tk.Label(
                content, text="🎯 —", font=main_font,
                bg=bg_color, fg=fg_color, anchor="w"
            )
            self._lbl_intent.pack(fill="x", pady=(2, 0))

            self._lbl_confidence = tk.Label(
                content, text="📊 —", font=small_font,
                bg=bg_color, fg=dim, anchor="w"
            )
            self._lbl_confidence.pack(fill="x", pady=(2, 0))

            # Start hidden
            self._root.withdraw()

            # ── Poll for updates ─────────────────────────────
            self._poll()
            self._root.mainloop()

        except Exception as e:
            print(f"⚠️  Thinking UI failed to start: {e}")
            self._running = False

    def _poll(self):
        """Check for pending updates every 100ms."""
        if not self._running:
            try:
                self._root.destroy()
            except Exception:
                pass
            return

        with self._lock:
            update = self._pending_update
            self._pending_update = None

        if update:
            self._apply_update(update)
            self._root.deiconify()  # Show window

        # Auto-hide after inactivity
        if (time.time() - self._last_update_time) > self._auto_hide_seconds:
            self._root.withdraw()

        self._root.after(100, self._poll)

    def _apply_update(self, data: dict):
        """Apply state update to labels."""
        if data.get("stage"):
            self._lbl_stage.config(text=f"⏳ {data['stage']}")

        if data.get("command"):
            cmd = data["command"]
            if len(cmd) > 60:
                cmd = cmd[:57] + "..."
            self._lbl_command.config(text=f"📝 \"{cmd}\"")

        if data.get("intent") or data.get("action"):
            intent_text = data.get("intent") or data.get("action") or "—"
            self._lbl_intent.config(text=f"🎯 {intent_text}")

        if data.get("confidence", 0) > 0:
            conf = data["confidence"]
            bar_len = int(conf * 20)
            bar = "█" * bar_len + "░" * (20 - bar_len)
            self._lbl_confidence.config(text=f"📊 {bar} {conf:.0%}")


# ─── Module-level singleton ─────────────────────────────────
_ui_instance = None


def get_thinking_ui() -> ThinkingUI:
    """Get or create the singleton ThinkingUI instance."""
    global _ui_instance
    if _ui_instance is None:
        _ui_instance = ThinkingUI()
    return _ui_instance


def init_thinking_ui():
    """Initialize and start the thinking UI."""
    ui = get_thinking_ui()
    ui.start()
    return ui


def update_thinking(command: str = "", intent: str = "", action: str = "",
                    confidence: float = 0.0, stage: str = ""):
    """Convenience function to update the thinking UI from anywhere."""
    if _ui_instance is not None:
        _ui_instance.update(command=command, intent=intent, action=action,
                            confidence=confidence, stage=stage)
