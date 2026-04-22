"""
test_command_engine.py -- Smoke tests for the remote-command-first pipeline.

Run with:
    python test_command_engine.py

No mic / camera / Gmail session required.
"""

import sys
import os
import json
import traceback

# Force UTF-8 output on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

PASSED: list = []
FAILED: list = []


def run(name: str, fn):
    try:
        fn()
        PASSED.append(name)
        print(f"  [PASS] {name}")
    except Exception as e:
        FAILED.append((name, str(e)))
        print(f"  [FAIL] {name}: {e}")
        traceback.print_exc()


print("=" * 60)
print("  COMMAND ENGINE -- SMOKE TESTS")
print("=" * 60)

# ── 1. Command Models ─────────────────────────────────────────
print("\n-- 1. Command Models --")

def t_command_request():
    from core.command_models import CommandRequest
    req = CommandRequest(text="find uber.txt", source="api")
    assert req.text == "find uber.txt"
    assert req.source == "api"
    assert req.id
    assert req.timestamp
run("CommandRequest fields", t_command_request)

def t_command_response_ok():
    from core.command_models import CommandResponse, ExecutionStatus
    r = CommandResponse.ok("req-1", "find_file", "Done!", data={"path": "/foo/bar.txt"})
    assert r.status == ExecutionStatus.COMPLETED
    assert r.final_result == "Done!"
    assert r.data["path"] == "/foo/bar.txt"
run("CommandResponse.ok()", t_command_response_ok)

def t_command_response_fail():
    from core.command_models import CommandResponse, ExecutionStatus
    r = CommandResponse.fail("req-2", "find_file", "Not found")
    assert r.status == ExecutionStatus.FAILED
    assert "Not found" in r.errors
run("CommandResponse.fail()", t_command_response_fail)

def t_command_response_to_dict():
    from core.command_models import CommandResponse
    r = CommandResponse.ok("req-3", "open_app", "Opened Chrome")
    d = r.to_dict()
    assert d["status"] == "completed"
    assert isinstance(d["steps"], list)
run("CommandResponse.to_dict()", t_command_response_to_dict)

# ── 2. ActionResult enhancements ──────────────────────────────
print("\n-- 2. ActionResult --")

def t_action_result_fields():
    from core.action_result import ActionResult
    r = ActionResult(success=True, action="create_file", request_id="req-99", step_id=1)
    assert r.request_id == "req-99"
    assert r.step_id == 1
run("ActionResult request_id + step_id", t_action_result_fields)

def t_action_result_to_step():
    from core.action_result import ActionResult
    r = ActionResult.ok("rename_file", "Renamed foo.txt", data={"filename": "foo.txt"})
    sr = r.to_step_result()
    assert sr.action == "rename_file"
    assert sr.status == "done"
run("ActionResult.to_step_result()", t_action_result_to_step)

# ── 3. WorkflowEngine matching ────────────────────────────────
print("\n-- 3. WorkflowEngine --")

def t_workflow_find_email():
    from core.workflow_engine import get_workflow_engine
    e = get_workflow_engine()
    assert e.match("find uber.txt and email it to aariyan@gmail.com") == "find_and_email_file"
run("Match: find + email", t_workflow_find_email)

def t_workflow_email_pdf():
    from core.workflow_engine import get_workflow_engine
    e = get_workflow_engine()
    assert e.match("email resume.pdf to john@example.com") == "find_and_email_file"
run("Match: email PDF to address", t_workflow_email_pdf)

def t_workflow_find_open():
    from core.workflow_engine import get_workflow_engine
    e = get_workflow_engine()
    assert e.match("find notes.txt and open it") == "find_and_open_file"
run("Match: find + open", t_workflow_find_open)

def t_workflow_no_match():
    from core.workflow_engine import get_workflow_engine
    e = get_workflow_engine()
    assert e.match("open chrome") is None
    assert e.match("what time is it") is None
    assert e.match("volume up") is None
run("No match for simple commands", t_workflow_no_match)

# ── 4. Parameter extraction ───────────────────────────────────
print("\n-- 4. Parameter Extraction --")

def t_extract_email_and_file():
    from core.workflow_engine import _extract_find_email_params
    p = _extract_find_email_params("find uber.txt and email it to aariyan@gmail.com")
    assert p["filename"] == "uber.txt", f"Got: {p['filename']!r}"
    assert p["recipient"] == "aariyan@gmail.com"
run("Extract filename + recipient", t_extract_email_and_file)

def t_extract_name_without_extension():
    from core.workflow_engine import _extract_find_email_params
    p = _extract_find_email_params("search the file resume and email to john@x.com")
    assert "resume" in p["filename"].lower(), f"Got: {p['filename']!r}"
    assert p["recipient"] == "john@x.com"
run("Extract filename without extension", t_extract_name_without_extension)

# ── 5. File resolution ────────────────────────────────────────
# Stub google-auth so control.__init__ -> email_control doesn't crash
import types as _types

def _make_stub(name):
    m = _types.ModuleType(name)
    m.Request = object
    m.Credentials = object
    m.InstalledAppFlow = object
    m.build = lambda *a, **kw: None
    m.genai = _types.ModuleType("google.genai")   # for pdf_summariser
    return m

for _mod_name in [
    "google", "google.auth", "google.auth.transport",
    "google.auth.transport.requests", "google.oauth2",
    "google.oauth2.credentials", "google_auth_oauthlib",
    "google_auth_oauthlib.flow", "googleapiclient",
    "googleapiclient.discovery",
]:
    if _mod_name not in sys.modules:
        sys.modules[_mod_name] = _make_stub(_mod_name)

print("\n-- 5. File Resolution --")

def t_find_files_returns_list():
    import importlib
    fc = importlib.import_module("control.windows.folder_control")
    results = fc.find_files("__nonexistent_test_xyz_abc__.txt")
    assert isinstance(results, list)
    assert len(results) == 0
run("find_files() returns empty list for missing file", t_find_files_returns_list)

def t_resolve_not_found():
    import importlib
    fc = importlib.import_module("control.windows.folder_control")
    r = fc.resolve_best_file("__nonexistent_xyz_file_abc__.txt")
    assert r.resolved is False
    assert r.reason == "not_found"
run("resolve_best_file() not_found", t_resolve_not_found)

def t_file_match_dataclass():
    import importlib
    fc = importlib.import_module("control.windows.folder_control")
    m = fc.FileMatch(path="/foo/bar.txt", name="bar.txt", score=1.0)
    assert m.path == "/foo/bar.txt"
    assert m.score == 1.0
run("FileMatch dataclass fields", t_file_match_dataclass)

# ── 6. Response policy ────────────────────────────────────────
print("\n-- 6. format_for_source() --")

def t_format_api():
    from core.command_models import CommandResponse
    from core.response_policy import format_for_source
    r = CommandResponse.ok("req-5", "open_app", "Opened Chrome")
    out = format_for_source(r, "api")
    parsed = json.loads(out)
    assert parsed["status"] == "completed"
run("format_for_source api -> JSON", t_format_api)

def t_format_phone():
    from core.command_models import CommandResponse
    from core.response_policy import format_for_source
    r = CommandResponse.ok("req-6", "open_app", "Opened Chrome")
    out = format_for_source(r, "phone")
    assert "Opened Chrome" in out
run("format_for_source phone -> text", t_format_phone)

def t_format_voice():
    from core.command_models import CommandResponse
    from core.response_policy import format_for_source
    r = CommandResponse.ok("req-7", "tell_time", "It's 9:45 PM.")
    assert format_for_source(r, "voice") == "It's 9:45 PM."
run("format_for_source voice -> plain text", t_format_voice)

# ── 7. TaskPlanner injection rules ────────────────────────────
print("\n-- 7. TaskPlanner --")

def t_task_planner_injection():
    from core.task_planner import RESULT_FORWARD_RULES
    assert "search_file" in RESULT_FORWARD_RULES
    rule = RESULT_FORWARD_RULES["search_file"]
    assert rule["inject_from"] == "path"
    assert rule["inject_as"] == "attachment_path"
run("RESULT_FORWARD_RULES: search_file → attachment_path", t_task_planner_injection)

# ── Summary ───────────────────────────────────────────────────
print(f"\n{'='*60}")
total = len(PASSED) + len(FAILED)
print(f"  Results: {len(PASSED)}/{total} passed")
if FAILED:
    print("\n  Failed tests:")
    for name, err in FAILED:
        print(f"    [FAIL] {name}: {err}")
else:
    print("  All tests passed!")
print("=" * 60)

sys.exit(1 if FAILED else 0)
