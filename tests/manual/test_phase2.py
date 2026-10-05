"""
Phase 0 test: Action verifier fail-closed + screen capture degradation.
Works on Windows and macOS.
"""
import os
import sys

# ─── Venv detection (cross-platform) ──────────────────────────
VENV_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "venv"))
if not os.path.isdir(VENV_PATH):
    VENV_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), ".venv"))

if sys.platform == "win32":
    python_exe = os.path.join(VENV_PATH, "Scripts", "python.exe")
else:
    python_exe = os.path.join(VENV_PATH, "bin", "python")

if os.path.isdir(VENV_PATH) and sys.prefix != VENV_PATH:
    if os.path.exists(python_exe):
        os.execv(python_exe, [python_exe] + sys.argv)
    else:
        print(f"⚠️  venv python not found at {python_exe}, running with system python")

# ─── Test 1: Action verifier fails closed ────────────────────
print("Testing app verification fail closed...")
from core.action_verifier import verify_action, BeforeState
import core.action_verifier as av

def bad_verifier(params, result, before):
    raise Exception("Simulated AX error")

# Temporarily inject bad verifier
av.VERIFIERS["test_action"] = bad_verifier

res = av.verify_action("test_action", {}, None, av.BeforeState())
assert res.ok is False, f"Expected ok=False on exception, got ok={res.ok}"
print("  ✔ App verification fails closed correctly.")

# Clean up
del av.VERIFIERS["test_action"]

# ─── Test 2: Screen capture degrades cleanly ─────────────────
print("Testing screen capture degrade cleanly...")
from perception.ocr import ocr_screen

try:
    ocr_res = ocr_screen()
    print(f"  OCR Result ok: {ocr_res.ok}, error: {ocr_res.error}")
    # On Windows without Tesseract, this should return ok=False with a clear error
    # On macOS without Screen Recording permission, same thing
    # The key is it NEVER raises an exception
except Exception as e:
    assert False, f"ocr_screen raised an exception: {e}"

print("  ✔ Screen capture degraded cleanly.")

# ─── Test 3: Runtime boot ────────────────────────────────────
print("Testing runtime.boot(voice=False)...")
import core.runtime as runtime
ok = runtime.boot(voice=False)
assert ok is True, f"Expected boot() to return True, got {ok}"
assert runtime._booted is True, "Expected _booted to be True"
print(f"  ✔ Runtime booted successfully. {len(runtime.ACTIONS)} actions loaded.")

print("\n✅ test_phase2.py passes.")
