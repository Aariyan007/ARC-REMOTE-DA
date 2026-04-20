"""
Phase 1 Smoke Tests — validates Understanding + Continuity.

Tests without requiring audio/STT/Gemini API — pure logic validation.

Run: python test_phase1.py
"""

import time
import sys
import os

# Ensure project root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

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
#  1. NORMALIZER: Casual Tone Stripping
# ═════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("  1. NORMALIZER: Casual Tone Stripping")
print("=" * 60)

from core.normalizer import normalize

# Basic filler stripping
n = normalize("dude make a file")
test("'dude' stripped", "dude" not in n.cleaned, f"got: '{n.cleaned}'")

n = normalize("bro can you open chrome")
test("'bro' + 'can you' stripped", "bro" not in n.cleaned and "can you" not in n.cleaned, f"got: '{n.cleaned}'")
test("'chrome' preserved", "chrome" in n.cleaned, f"got: '{n.cleaned}'")

# Casual adjective stripping
n = normalize("make a stupid file")
test("'stupid' stripped before target", "stupid" not in n.cleaned, f"got: '{n.cleaned}'")
test("'make' + 'file' preserved", "make" in n.cleaned and "file" in n.cleaned, f"got: '{n.cleaned}'")

# Positional awareness: "stupid" AFTER structural keyword → preserved
n = normalize("create a file called stupid ideas")
test("'stupid' preserved after 'called'", "stupid" in n.cleaned, f"got: '{n.cleaned}'")

n = normalize("make a dumb random file")
test("'dumb random' stripped", "dumb" not in n.cleaned and "random" not in n.cleaned, f"got: '{n.cleaned}'")

# Tone detection
n = normalize("dude open chrome")
test("Tone: casual", n.tone == "casual", f"got: '{n.tone}'")

n = normalize("stupid thing just open it")
test("Tone: frustrated", n.tone == "frustrated", f"got: '{n.tone}'")

n = normalize("please open chrome")
test("Tone: polite", n.tone == "polite", f"got: '{n.tone}'")

n = normalize("open chrome")
test("Tone: neutral", n.tone == "neutral", f"got: '{n.tone}'")

# Phrase stripping
n = normalize("you know open the important stuff in downloads")
test("'you know' + 'important stuff' stripped", "you know" not in n.cleaned and "important stuff" not in n.cleaned, f"got: '{n.cleaned}'")

n = normalize("kinda wanna search for python tutorials man")
test("'kinda' stripped", "kinda" not in n.cleaned, f"got: '{n.cleaned}'")
test("'search' preserved", "search" in n.cleaned, f"got: '{n.cleaned}'")


# ═════════════════════════════════════════════════════════════
#  2. TARGET-TYPE INFERENCE
# ═════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("  2. TARGET-TYPE INFERENCE")
print("=" * 60)

from core.command_interpreter import infer_target_type

test("open chrome → app", infer_target_type("open chrome", "open_app") == "app")
test("create a file → file", infer_target_type("create a file called notes", "create_file") == "file")
test("watch youtube → website", infer_target_type("watch something on youtube") == "website")
test("search for python → browser_search", infer_target_type("search for python tutorials", "search_google") == "browser_search")
test("open downloads → folder", infer_target_type("open downloads folder", "open_folder") == "folder")
test("send email → email", infer_target_type("send email to john", "send_email") == "email")
test("save note → note", infer_target_type("save a note", "save_note") == "note")
test("close tab → tab", infer_target_type("close that tab", "close_tab") == "tab")
test("youtube video → website (not app)", infer_target_type("play video on youtube") == "website")


# ═════════════════════════════════════════════════════════════
#  3. TASK STATE: Pending Clarification
# ═════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("  3. TASK STATE: Pending Clarification")
print("=" * 60)

from core.task_state import (
    PendingTask, set_pending, get_pending, clear_pending,
    has_pending, is_pending_answer, resume_with_answer,
)

# Set up a pending task
task = PendingTask(
    action="create_file",
    known_params={"location": "desktop"},
    missing_param="filename",
    question_asked="What should I name the file?",
    original_command="dude make a stupid file",
    normalized_command="make file",
    intent_source="builtin",
    confidence=0.85,
)
set_pending(task)
test("Pending exists", has_pending())

# Short answer should be treated as pending answer
test("'notes' is pending answer", is_pending_answer("notes"))
test("'project notes' is pending answer", is_pending_answer("project notes"))

# New command should NOT be treated as answer
set_pending(task)  # re-set since is_pending_answer may have been called
test("'open chrome' is NOT pending answer", not is_pending_answer("open chrome"))

# Resume with answer
set_pending(task)
result = resume_with_answer("my_notes")
test("Resume returns dict", result is not None)
test("Resume action correct", result["action"] == "create_file")
test("Resume fills filename", result["params"]["filename"] == "my_notes")
test("Resume keeps known params", result["params"].get("location") == "desktop")
test("Pending cleared after resume", not has_pending())

# Cancellation
set_pending(task)
test("'nevermind' cancels pending", not is_pending_answer("nevermind"))
test("Pending cleared after cancel", not has_pending())

# Expiry
expired_task = PendingTask(
    action="create_file",
    missing_param="filename",
    timestamp=time.time() - 60,
)
import core.task_state as ts
with ts._lock:
    ts._pending = expired_task
test("Expired task returns None", get_pending() is None)


# ═════════════════════════════════════════════════════════════
#  4. AMBIGUITY RESOLVER: Single-Slot Questions
# ═════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("  4. AMBIGUITY RESOLVER: Single-Slot Questions")
print("=" * 60)

from core.ambiguity_resolver import build_single_slot_question, get_most_critical_missing

# Priority ordering
param = get_most_critical_missing("send_email", {}, ["body", "to", "subject"])
test("send_email priority: 'to' first", param == "to", f"got: '{param}'")

param = get_most_critical_missing("create_file", {}, ["content", "filename"])
test("create_file priority: 'filename' first", param == "filename", f"got: '{param}'")

# Question generation
q, p = build_single_slot_question("create_file", {}, ["filename"])
test("create_file → 'What should I name the file?'", "name" in q.lower(), f"got: '{q}'")
test("create_file asks about 'filename'", p == "filename")

q, p = build_single_slot_question("open_app", {}, ["target"])
test("open_app → 'Which app should I open?'", "app" in q.lower(), f"got: '{q}'")

q, p = build_single_slot_question("send_email", {}, ["to", "subject"])
test("send_email → asks about 'to' first", p == "to")

# No missing → returns None
q, p = build_single_slot_question("open_app", {"target": "chrome"}, [])
test("No missing → None", q is None and p is None)


# ═════════════════════════════════════════════════════════════
#  5. WORKING MEMORY: Grounding Context
# ═════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("  5. WORKING MEMORY: Grounding Context")
print("=" * 60)

from core.working_memory import WorkingMemory

wm = WorkingMemory()
wm.record_action(
    "create_file", {"filename": "notes.txt", "target": "notes.txt"},
    "User said create file", "success", confidence=0.95,
    command="create a file called notes", intent_source="builtin"
)
wm.update_grounding(last_file="notes.txt", last_action="create_file")

# Resolve references
resolved = wm.resolve_reference("it")
test("'it' → 'notes.txt'", resolved == "notes.txt", f"got: '{resolved}'")

resolved = wm.resolve_reference("this file")
test("'this file' → 'notes.txt'", resolved == "notes.txt", f"got: '{resolved}'")

# Browser grounding
wm.update_grounding(last_browser_title="GitHub", last_browser_url="https://github.com")
resolved = wm.resolve_reference("that tab")
test("'that tab' → 'GitHub'", resolved == "GitHub", f"got: '{resolved}'")

# Full context
ctx = wm.get_grounding_context()
test("Context has last_file", ctx.get("last_file") == "notes.txt")
test("Context has last_action", ctx.get("last_action") == "create_file")
test("Context has last_browser_url", ctx.get("last_browser_url") == "https://github.com")


# ═════════════════════════════════════════════════════════════
#  6. END-TO-END FLOW SIMULATION
# ═════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("  6. END-TO-END FLOW SIMULATION")
print("=" * 60)

# Simulate: "dude make a stupid file" → ARC asks → user says "notes" → resumes
from core.normalizer import normalize as norm
from core.response_policy import get_missing_params

# Step 1: Normalize
n = norm("dude make a stupid file")
test("E2E: normalized = 'make a file'", "make" in n.cleaned and "file" in n.cleaned and "stupid" not in n.cleaned,
     f"got: '{n.cleaned}'")

# Step 2: Would produce action=create_file, params={}
action = "create_file"
params = {}
missing = get_missing_params(action, params)
test("E2E: filename is missing", "filename" in missing)

# Step 3: Build question and create pending task
q, p = build_single_slot_question(action, params, missing)
test("E2E: question about filename", p == "filename")

pending = PendingTask(
    action=action,
    known_params=params,
    missing_param=p,
    question_asked=q,
    original_command="dude make a stupid file",
    normalized_command=n.cleaned,
)
set_pending(pending)

# Step 4: User answers "notes"
test("E2E: 'notes' is pending answer", is_pending_answer("notes"))

# Step 5: Resume
result = resume_with_answer("notes")
test("E2E: resumed action = create_file", result["action"] == "create_file")
test("E2E: filename = 'notes'", result["params"]["filename"] == "notes")
test("E2E: pending cleared", not has_pending())


# ═════════════════════════════════════════════════════════════
#  SUMMARY
# ═════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
total = PASS + FAIL
print(f"  RESULTS: {PASS}/{total} passed, {FAIL} failed")
if FAIL == 0:
    print("  ✅ ALL TESTS PASSED!")
else:
    print("  ⚠️  SOME TESTS FAILED")
print("=" * 60)

sys.exit(0 if FAIL == 0 else 1)
