import os
import sys

VENV_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "venv"))
if sys.prefix != VENV_PATH:
    python_exe = os.path.join(VENV_PATH, "bin", "python")
    if os.path.exists(python_exe):
        os.execv(python_exe, [python_exe] + sys.argv)
    else:
        print("venv not found")
        sys.exit(1)

import time
from perception.ui_accessibility import get_frontmost_app, get_focused_window_title

print("Testing AX API...")
app, err = get_frontmost_app()
assert isinstance(app, str) and isinstance(err, str), "get_frontmost_app must return tuple[str, str]"
title, err2 = get_focused_window_title()
assert isinstance(title, str) and isinstance(err2, str), "get_focused_window_title must return tuple[str, str]"
print("AX API types are correct.")

print("Testing intent model cold-start...")
from core.fast_intent import classify
t0 = time.time()
try:
    res = classify("open chrome")
    print(f"Classified: {res}")
except RuntimeError as e:
    print(f"Caught expected RuntimeError instead of hanging: {e}")
except Exception as e:
    print(f"Caught unexpected exception: {e}")
    sys.exit(1)
t1 = time.time()
assert (t1 - t0) < 25.0, "classify() took too long, it should fail fast or load from cache"
print("Intent model cold-start test passed.")
print("test_phase1.py passes.")
