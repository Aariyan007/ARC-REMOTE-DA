"""
Phase 2 Smoke Tests — validates Grounded Perception & Strict Verification.

Tests without requiring live audio/STT/Gemini API — pure logic validation.

Run: python test_phase2.py
"""

import os
import sys
import time
import tempfile

# Ensure project root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

PASS = 0
FAIL = 0


def test(name: str, result: bool, detail: str = ""):
    global PASS, FAIL
    if result:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name}" + (f" -- {detail}" if detail else ""))


# ═════════════════════════════════════════════════════════════
#  1. ACTION VERIFIER: File Verification
# ═════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("  1. ACTION VERIFIER: File Verification")
print("=" * 60)

from core.action_verifier import (
    BeforeState, verify_action, VERIFIERS, SAFE_TO_RETRY,
    verify_file_created, verify_file_renamed, verify_file_deleted,
    verify_file_edited, verify_file_copied, verify_folder_created,
    capture_before_state,
)
from core.action_result import ActionResult

# -- create_file: file exists → ok
with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
    tmp_path = f.name
    f.write(b"test content")

try:
    result = ActionResult.ok("create_file", f"Created test.txt",
                             data={"filename": os.path.basename(tmp_path)})
    before = BeforeState(file_path=tmp_path, file_exists=False)
    v = verify_file_created(
        {"filename": tmp_path}, result, before,
    )
    test("create_file: file exists → ok", v.ok, f"got: {v.message}")
finally:
    os.unlink(tmp_path)

# -- create_file: file missing → not ok
v = verify_file_created(
    {"filename": "/tmp/definitely_does_not_exist_342897.txt"},
    ActionResult.ok("create_file", "Created"),
    BeforeState(),
)
test("create_file: file missing → not ok", not v.ok, f"got: {v.message}")

# -- rename_file: old gone + new exists → ok
with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, prefix="new_") as f:
    new_path = f.name
    f.write(b"renamed")

old_path = new_path + "_old_gone"  # doesn't exist
v = verify_file_renamed(
    {"filename": os.path.basename(old_path), "new_name": os.path.basename(new_path)},
    ActionResult.ok("rename_file", "Renamed", data={"path": new_path}),
    BeforeState(file_path=old_path),
)
test("rename_file: old gone + new exists → ok", v.ok, f"got: {v.message}")
os.unlink(new_path)

# -- delete_file: file gone → ok
gone_path = "/tmp/test_delete_verification_gone_12345.txt"
before = BeforeState(file_path=gone_path, file_exists=True)
v = verify_file_deleted(
    {"filename": "test.txt"}, ActionResult.ok("delete_file", "Deleted"), before,
)
test("delete_file: file gone → ok", v.ok, f"got: {v.message}")

# -- delete_file: file still exists → not ok
with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
    still_exists_path = f.name
    f.write(b"still here")

before = BeforeState(file_path=still_exists_path, file_exists=True)
v = verify_file_deleted(
    {"filename": os.path.basename(still_exists_path)},
    ActionResult.ok("delete_file", "Deleted"),
    before,
)
test("delete_file: file still exists → not ok", not v.ok, f"got: {v.message}")
os.unlink(still_exists_path)

# -- edit_file: mtime changed → ok
with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
    edit_path = f.name
    f.write(b"original")

old_stat = os.stat(edit_path)
time.sleep(0.1)
with open(edit_path, "a") as f:
    f.write(" added")
new_stat = os.stat(edit_path)

before = BeforeState(file_path=edit_path, file_mtime=old_stat.st_mtime, file_size=old_stat.st_size)
v = verify_file_edited(
    {"filename": edit_path}, ActionResult.ok("edit_file", "Edited"), before,
)
test("edit_file: mtime changed → ok", v.ok, f"got: {v.message}")
os.unlink(edit_path)


# ═════════════════════════════════════════════════════════════
#  2. ACTION VERIFIER: Registry & Dispatch
# ═════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("  2. ACTION VERIFIER: Registry & Dispatch")
print("=" * 60)

# All expected verifiers registered
expected_verifiers = [
    "create_file", "rename_file", "delete_file", "copy_file", "edit_file",
    "create_folder", "open_folder",
    "open_app", "switch_to_app", "close_app", "minimise_app",
    "open_url", "search_google", "new_tab", "close_tab",
]
for action in expected_verifiers:
    test(f"Verifier registered: {action}", action in VERIFIERS)

# Safe-to-retry set makes sense
test("create_file is safe to retry", "create_file" in SAFE_TO_RETRY)
test("open_app is safe to retry", "open_app" in SAFE_TO_RETRY)
test("delete_file is NOT safe to retry", "delete_file" not in SAFE_TO_RETRY)
test("rename_file is NOT safe to retry", "rename_file" not in SAFE_TO_RETRY)
test("close_tab is NOT safe to retry", "close_tab" not in SAFE_TO_RETRY)

# Dispatch to verifier returns VerificationResult
v = verify_action(
    "create_file",
    {"filename": "/tmp/not_exists_test_87654.txt"},
    ActionResult.ok("create_file", "Test"),
    BeforeState(),
)
test("verify_action returns VerificationResult", hasattr(v, "ok") and hasattr(v, "message"))

# Unknown action → ok=True (no specific verifier)
v = verify_action("tell_time", {}, ActionResult.ok("tell_time", "Time"), BeforeState())
test("Unknown action → ok=True", v.ok)


# ═════════════════════════════════════════════════════════════
#  3. PERCEPTION: Accessibility (macOS only)
# ═════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("  3. PERCEPTION: Accessibility")
print("=" * 60)

from perception.ui_accessibility import (
    AXSnapshot, get_ax_snapshot, get_frontmost_app,
    get_focused_window_title, is_app_running, snapshot_to_text,
)

if sys.platform == "darwin":
    # get_frontmost_app should return non-empty on macOS
    app = get_frontmost_app()
    test("[LIVE] get_frontmost_app returns something", bool(app), f"got: '{app}'")

    # get_ax_snapshot should not crash
    snap = get_ax_snapshot()
    test("[LIVE] get_ax_snapshot returns AXSnapshot", isinstance(snap, AXSnapshot))
    test("[LIVE] AXSnapshot has frontmost_app", bool(snap.frontmost_app), f"got: '{snap.frontmost_app}'")
    test("[LIVE] snapshot_to_text works", bool(snapshot_to_text(snap)))

    # is_app_running for Finder (always running)
    test("[LIVE] Finder is running", is_app_running("Finder"))
else:
    snap = get_ax_snapshot()
    test("Non-macOS: AXSnapshot has error", bool(snap.error), f"got: '{snap.error}'")


# ═════════════════════════════════════════════════════════════
#  4. PERCEPTION: Browser State
# ═════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("  4. PERCEPTION: Browser State")
print("=" * 60)

from perception.browser_state import BrowserSnapshot, get_active_tab_state

# Should not crash even when Playwright isn't running
snap = get_active_tab_state()
test("get_active_tab_state returns BrowserSnapshot", isinstance(snap, BrowserSnapshot))
test("BrowserSnapshot has is_running field", hasattr(snap, "is_running"))
test("BrowserSnapshot has tab_count field", hasattr(snap, "tab_count"))
test("BrowserSnapshot has url field", hasattr(snap, "url"))
test("BrowserSnapshot has title field", hasattr(snap, "title"))


# ═════════════════════════════════════════════════════════════
#  5. PERCEPTION: OCR
# ═════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("  5. PERCEPTION: OCR")
print("=" * 60)

from perception.ocr import OCRResult, ocr_image_file_structured

# OCRResult structure
r = OCRResult(text="hello", confidence=0.9, source="test")
test("OCRResult.ok = True when text present", r.ok)
r2 = OCRResult(error="No tesseract")
test("OCRResult.ok = False when error", not r2.ok)

# OCR on non-existent file → error in result
r3 = ocr_image_file_structured("/tmp/definitely_not_an_image_file.png")
test("OCR on missing file → error result", bool(r3.error))


# ═════════════════════════════════════════════════════════════
#  6. PLAYWRIGHT: Read-only Methods
# ═════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("  6. PLAYWRIGHT: Read-only Methods")
print("=" * 60)

# Import directly to avoid control/__init__.py transitive imports
import importlib
_pw_mod = importlib.import_module("control.playwright_browser")
is_browser_running = _pw_mod.is_browser_running
get_active_url = _pw_mod.get_active_url
get_active_title = _pw_mod.get_active_title
get_tab_count = _pw_mod.get_tab_count

# When no browser started, these should return safe defaults
test("is_browser_running returns False (no browser)", not is_browser_running())
test("get_active_url returns None (no browser)", get_active_url() is None)
test("get_active_title returns None (no browser)", get_active_title() is None)
test("get_tab_count returns 0 (no browser)", get_tab_count() == 0)


# ═════════════════════════════════════════════════════════════
#  7. RESPONSE POLICY: Verification Failures
# ═════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("  7. RESPONSE POLICY: Verification Failures")
print("=" * 60)

from core.response_policy import get_verification_failure, VERIFICATION_FAILURE_TEMPLATES

# Templates exist for key actions
for action in ["open_app", "rename_file", "delete_file", "open_url", "close_tab"]:
    test(f"Verification failure template exists: {action}", action in VERIFICATION_FAILURE_TEMPLATES)

# Generates grounded message
msg = get_verification_failure("open_app", {"target": "Chrome"})
test("Verification failure message for open_app", "Chrome" in msg and "couldn't confirm" in msg.lower(),
     f"got: '{msg}'")

msg = get_verification_failure("rename_file", {"filename": "notes.txt"})
test("Verification failure message for rename_file", "couldn't verify" in msg.lower(),
     f"got: '{msg}'")

# Unknown action → empty string
msg = get_verification_failure("tell_time", {})
test("Unknown action → empty message", msg == "")


# ═════════════════════════════════════════════════════════════
#  8. BEFORE-STATE CAPTURE
# ═════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("  8. BEFORE-STATE CAPTURE")
print("=" * 60)

# capture_before_state should not crash
before = capture_before_state("create_file", {"filename": "test.txt"})
test("capture_before_state returns BeforeState", isinstance(before, BeforeState))
test("BeforeState has timestamp", before.timestamp > 0)

if sys.platform == "darwin":
    test("[LIVE] BeforeState captures AX app", bool(before.ax_frontmost_app),
         f"got: '{before.ax_frontmost_app}'")

# File action captures file state
before_file = capture_before_state("edit_file", {"filename": __file__})
test("File action captures file_exists", before_file.file_exists is not None)

# Browser action captures browser state
before_browser = capture_before_state("open_url", {"url": "https://test.com"})
test("Browser action captures browser_running", hasattr(before_browser, "browser_running"))


# ═════════════════════════════════════════════════════════════
#  9. ROUTER: Verification Integration
# ═════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("  9. ROUTER: Verification Integration")
print("=" * 60)

import inspect
from core import intent_router

route_source = inspect.getsource(intent_router.route)

# Phase 2 verifier is wired in
test("Router imports capture_before_state",
     "capture_before_state" in inspect.getsource(intent_router))
test("Router imports verify_action",
     "verify_action" in inspect.getsource(intent_router))
test("Router imports SAFE_TO_RETRY",
     "SAFE_TO_RETRY" in inspect.getsource(intent_router))

# Router uses _capture_before_state (not just _capture_perception_state)
test("Router uses _capture_before_state",
     "_capture_before_state" in route_source)

# Router passes actions and text to _verify_action_result for retry
test("Router passes actions= to _verify_action_result",
     "actions=actions" in route_source)

# Retry logic exists
verify_source = inspect.getsource(intent_router._verify_action_result)
test("_verify_action_result has retry logic",
     "SAFE_TO_RETRY" in verify_source and "retry" in verify_source.lower())
test("_verify_action_result never fakes success",
     "result.success = False" in verify_source)


# ═════════════════════════════════════════════════════════════
#  10. PERCEPTION PRIORITY ORDER
# ═════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("  10. PERCEPTION PRIORITY ORDER")
print("=" * 60)

# App verifiers use AX (not just perception_engine)
app_verifier_source = inspect.getsource(
    __import__("core.action_verifier", fromlist=["verify_app_opened"]).verify_app_opened
)
test("App verifier uses get_frontmost_app (AX first)",
     "get_frontmost_app" in app_verifier_source)
test("App verifier uses is_app_running (AX check)",
     "is_app_running" in app_verifier_source)

# Browser verifiers use get_active_tab_state (Playwright first)
browser_verifier_source = inspect.getsource(
    __import__("core.action_verifier", fromlist=["verify_url_opened"]).verify_url_opened
)
test("Browser verifier uses get_active_tab_state",
     "get_active_tab_state" in browser_verifier_source)

# File verifiers use os.path (deterministic first)
file_verifier_source = inspect.getsource(
    __import__("core.action_verifier", fromlist=["verify_file_created"]).verify_file_created
)
test("File verifier uses os.path.exists (deterministic)",
     "os.path.exists" in file_verifier_source)


# ═════════════════════════════════════════════════════════════
#  11. SCREEN CAPTURE MODULE
# ═════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("  11. SCREEN CAPTURE MODULE")
print("=" * 60)

from perception.screen_capture import capture_focused_window_to_file

# Function exists and is callable
test("capture_focused_window_to_file exists", callable(capture_focused_window_to_file))

# On macOS, should be able to capture (requires screen recording permission)
if sys.platform == "darwin":
    try:
        path = capture_focused_window_to_file()
        test("[LIVE] Window capture produces file", os.path.isfile(path), f"path: {path}")
        if os.path.isfile(path):
            os.unlink(path)
    except Exception as e:
        test("[LIVE] Window capture (may need permission)", False, str(e))


# ═════════════════════════════════════════════════════════════
#  PHASE 1 REGRESSION: Quick checks
# ═════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("  PHASE 1 REGRESSION: Quick Checks")
print("=" * 60)

# ActionResult structure preserved
r = ActionResult.ok("open_app", "Opened Chrome", data={"target": "Chrome"})
test("ActionResult.verified exists", hasattr(r, "verified"))
test("ActionResult.verified defaults False", r.verified is False)

# Response policy still works
from core.response_policy import get_ack, get_result, get_failure

ack = get_ack("open_app")
test("get_ack still works", bool(ack))

result_text = get_result(ActionResult.ok("rename_file", "Renamed",
                                         data={"old_name": "a.txt", "new_name": "b.txt"}))
test("get_result still works", "b.txt" in result_text, f"got: '{result_text}'")

fail_text = get_failure(ActionResult.fail("open_app", "Not found", data={"target": "blah"}))
test("get_failure still works", "blah" in fail_text.lower() or "couldn't" in fail_text.lower(),
     f"got: '{fail_text}'")

# Task state preserved
from core.task_state import PendingTask, set_pending, has_pending, clear_pending
p = PendingTask(action="create_file", missing_param="filename")
set_pending(p)
test("PendingTask preserved", has_pending())
clear_pending()

# ExpectedDelta legacy still importable
from core.action_verifier import ExpectedDelta, verify_perception_delta
test("ExpectedDelta legacy preserved", ExpectedDelta is not None)
test("verify_perception_delta legacy preserved", callable(verify_perception_delta))


# ═════════════════════════════════════════════════════════════
#  SUMMARY
# ═════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
total = PASS + FAIL
print(f"  RESULTS: {PASS}/{total} passed, {FAIL} failed")
if FAIL == 0:
    print("  [PASS] ALL PHASE 2 TESTS PASSED!")
else:
    print("  [WARN] SOME TESTS FAILED")
print("=" * 60)

sys.exit(0 if FAIL == 0 else 1)
