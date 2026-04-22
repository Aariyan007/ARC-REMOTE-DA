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

from core.action_verifier import verify_action, BeforeState
from perception.ocr import ocr_screen

print("Testing app verification fail closed...")
def bad_verifier(params, result, before):
    raise Exception("Simulated AX error")

# Temporarily inject bad verifier
import core.action_verifier as av
av.VERIFIERS["test_action"] = bad_verifier

res = av.verify_action("test_action", {}, None, av.BeforeState())
assert res.ok is False, f"Expected ok=False on exception, got ok={res.ok}"
print("App verification fails closed correctly.")

print("Testing screen capture degrade cleanly...")
try:
    ocr_res = ocr_screen()
    print(f"OCR Result ok: {ocr_res.ok}, error: {ocr_res.error}")
except Exception as e:
    assert False, f"ocr_screen raised an exception: {e}"

print("Screen capture degraded cleanly.")
print("test_phase2.py passes.")
