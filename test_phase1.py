"""
Phase 0 test: AX API types + intent model cold-start.
Works on Windows and macOS.
"""
import os
import sys
import time

# ─── Venv detection (cross-platform) ──────────────────────────
VENV_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "venv"))
if not os.path.isdir(VENV_PATH):
    # Try .venv (common convention)
    VENV_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), ".venv"))

if sys.platform == "win32":
    python_exe = os.path.join(VENV_PATH, "Scripts", "python.exe")
else:
    python_exe = os.path.join(VENV_PATH, "bin", "python")

# Re-exec under venv if not already running inside it
if os.path.isdir(VENV_PATH) and sys.prefix != VENV_PATH:
    if os.path.exists(python_exe):
        os.execv(python_exe, [python_exe] + sys.argv)
    else:
        print(f"⚠️  venv python not found at {python_exe}, running with system python")

# ─── Test 1: AX API types ────────────────────────────────────
print("Testing AX API...")
if sys.platform == "darwin":
    from perception.ui_accessibility import get_frontmost_app, get_focused_window_title
    app, err = get_frontmost_app()
    assert isinstance(app, str) and isinstance(err, str), \
        "get_frontmost_app must return tuple[str, str]"
    title, err2 = get_focused_window_title()
    assert isinstance(title, str) and isinstance(err2, str), \
        "get_focused_window_title must return tuple[str, str]"
    print("  ✔ AX API types are correct.")
else:
    from perception.ui_accessibility import get_frontmost_app
    app, err = get_frontmost_app()
    assert app == "" and err == "not_macos", \
        f"Expected ('', 'not_macos') on Windows, got ({app!r}, {err!r})"
    print("  ✔ AX API correctly returns 'not_macos' on Windows.")

# ─── Test 2: Intent model cold-start ─────────────────────────
print("Testing intent model cold-start...")
from core.fast_intent import classify
t0 = time.time()
try:
    res = classify("open chrome")
    print(f"  Classified: {res}")
except RuntimeError as e:
    print(f"  Caught expected RuntimeError instead of hanging: {e}")
except Exception as e:
    print(f"  Caught unexpected exception: {e}")
    sys.exit(1)
t1 = time.time()
assert (t1 - t0) < 60.0, "classify() took too long, it should fail fast or load from cache"
print("  ✔ Intent model cold-start test passed.")

print("\n✅ test_phase1.py passes.")
