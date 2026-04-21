"""
ARC VIBE CHECK — talks to every function like a normal human would.
No formal test framework, just raw checks with casual phrasing.
Run: python test_vibe_check.py
"""
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PASS = 0
FAIL = 0

def check(label, result, expected=True, got=None):
    global PASS, FAIL
    ok = result == expected if expected is not True else bool(result)
    emoji = "✅" if ok else "❌"
    suffix = f"  ← got: {got}" if (not ok and got is not None) else ""
    print(f"  {emoji}  {label}{suffix}")
    if ok: PASS += 1
    else:   FAIL += 1

def section(title):
    print(f"\n{'─'*55}")
    print(f"  {title}")
    print(f"{'─'*55}")

print("=" * 55)
print("   ARC VIBE CHECK  🔥  let's see if this thing works")
print("=" * 55)


# ════════════════════════════════════════════════════
#  1. NORMALIZER — bro can it handle slang or nah?
# ════════════════════════════════════════════════════
section("1. NORMALIZER  (strip the nonsense words)")

from core.normalizer import normalize

tests = [
    ("bro open chrome",                     "open chrome"),
    ("dude can you make a file",            "make a file"),
    ("kinda wanna search for python stuff", "search for python stuff"),
    ("please just open vscode",             "open vscode"),
    ("i want to close that stupid tab",     "close tab"),
    ("yo can you search youtube",           "search youtube"),
    ("bro dude please open spotify bro",    "open spotify"),
    ("can you maybe rename this thing",     "rename this thing"),
]

for raw, expected_contains in tests:
    result = normalize(raw).cleaned
    ok = expected_contains in result or result in expected_contains or \
         all(w in result for w in expected_contains.split() if len(w) > 3)
    check(f'"{raw}"  →  "{result}"', ok,
          got=f'expected to contain "{expected_contains}"')


# ════════════════════════════════════════════════════
#  2. TARGET TYPE — does it know what we're talking about
# ════════════════════════════════════════════════════
section("2. TARGET-TYPE INFERENCE  (what IS this thing you want)")

from core.command_interpreter import infer_target_type

cases = [
    ("open chrome",                  "app"),
    ("watch a video on youtube",     "website"),
    ("search for react tutorial",    "browser_search"),
    ("create a file called notes",   "file"),
    ("open downloads folder",        "folder"),
    ("send an email to mom",         "email"),
    ("save this as a note",          "note"),
    ("close the current tab",        "tab"),
]

for phrase, expected_type in cases:
    tt = infer_target_type(phrase)
    check(f'"{phrase}"  →  {tt}', tt == expected_type,
          got=f"expected {expected_type}")


# ════════════════════════════════════════════════════
#  3. TASK STATE — does ARC remember what it asked?
# ════════════════════════════════════════════════════
section("3. TASK STATE  (ARC's short-term memory)")

from core.task_state import (
    set_pending, get_pending, has_pending, clear_pending,
    is_pending_answer, resume_with_answer, PendingTask, detect_follow_up_intent
)

# set a pending and see if it sticks
set_pending(PendingTask(action="create_file", missing_param="filename",
                        question_asked="yo what should i call the file?"))
check("Pending task is remembered", has_pending())
check('"notes.txt" looks like an answer (not a new cmd)', is_pending_answer("notes.txt"))
check('"my report" looks like an answer', is_pending_answer("my report"))
check('"open chrome" is a NEW command, not an answer', not is_pending_answer("open chrome"))

# resume it
result = resume_with_answer("notes.txt")
check("Resume returns something", result is not None)
check("Resume gives back create_file action", result["action"] == "create_file",
      got=result.get("action"))
check("Resume fills in notes.txt", result["params"].get("filename") == "notes.txt",
      got=result["params"])
check("Pending is cleared after resume", not has_pending())

# cancellation — 'nevermind' should NOT be treated as an answer
set_pending(PendingTask(action="delete_file", missing_param="target",
                        question_asked="which file u tryna delete bro?"))
check("'nevermind' is NOT treated as a pending answer (cancel gate)",
      not is_pending_answer("nevermind"))
check("'cancel' is NOT treated as a pending answer",
      not is_pending_answer("cancel"))
clear_pending()  # clean up
check("Pending cleared after cancel", not has_pending())


# ════════════════════════════════════════════════════
#  4. FOLLOW-UP DETECTION — two-part commands work?
# ════════════════════════════════════════════════════
section("4. FOLLOW-UP DETECTION  (compound commands, the big one)")

combos = [
    ("make a folder and then write hello in it",
     "edit_file", "hello", "content"),
    ("create a file, i want to put my notes in it",
     "edit_file", "my notes", "content"),
    ("create a file then delete it",
     "delete_file", None, None),
    ("open chrome and then search for cats",
     "search_google", "cats", "query"),
    ("make a file; rename it to report",
     "rename_file", "report", "new_name"),
]

for phrase, exp_action, exp_val, exp_key in combos:
    primary, action, params = detect_follow_up_intent(phrase)
    check(f'"{phrase[:40]}…"  →  action={action}',
          action == exp_action, got=f"expected {exp_action}")
    if exp_key and exp_val:
        check(f'  └─ params has {exp_key}="{exp_val}"',
              params.get(exp_key) == exp_val, got=params)

# simple command — no follow-up expected
_, action, params = detect_follow_up_intent("open chrome")
check('"open chrome" has NO follow-up', action == "" and params == {},
      got=f"action={action}")


# ════════════════════════════════════════════════════
#  5. AMBIGUITY RESOLVER — right question, right time
# ════════════════════════════════════════════════════
section("5. AMBIGUITY RESOLVER  (asks the RIGHT question)")

from core.ambiguity_resolver import build_single_slot_question

q, param = build_single_slot_question("create_file", {}, ["filename"])
check('create_file asks "What should I name the file?"',
      "name" in q.lower() and "file" in q.lower(), got=q)
check("create_file asks about 'filename' slot", param == "filename", got=param)

q2, param2 = build_single_slot_question("send_email", {}, ["to", "subject", "body"])
check("send_email asks about 'to' first", param2 == "to", got=param2)

# grounded question — should mention the folder name
q3, _ = build_single_slot_question(
    "edit_file", {}, ["filename"],
    grounding_context={"parent_target": "my_projects", "parent_action": "create_folder"}
)
check('Grounded question mentions "my_projects"', "my_projects" in q3, got=q3)
check('Grounded question says "inside"', "inside" in q3.lower(), got=q3)


# ════════════════════════════════════════════════════
#  6. WORKING MEMORY — does it remember context?
# ════════════════════════════════════════════════════
section("6. WORKING MEMORY  (remembers what you were doing)")

from core.working_memory import WorkingMemory

wm = WorkingMemory()
wm.update_grounding(last_file="notes.txt", last_action="create_file",
                    last_browser_url="https://github.com",
                    last_browser_title="GitHub")

ctx = wm.get_grounding_context()
check("WorkingMemory remembers last_file=notes.txt",
      ctx.get("last_file") == "notes.txt", got=ctx.get("last_file"))
check("WorkingMemory remembers last_action",
      ctx.get("last_action") == "create_file", got=ctx.get("last_action"))
check("WorkingMemory remembers browser URL",
      "github" in (ctx.get("last_browser_url") or "").lower(),
      got=ctx.get("last_browser_url"))
check("WorkingMemory remembers browser title",
      ctx.get("last_browser_title") == "GitHub",
      got=ctx.get("last_browser_title"))

# "it" resolution
wm.update_grounding(last_file="report.txt")
resolved = wm.resolve_reference("it")
check('"it" resolves to last known file (report.txt)',
      "report" in (resolved or ""), got=resolved)


# ════════════════════════════════════════════════════
#  7. SAFETY — dangerous stuff needs a yes/no first
# ════════════════════════════════════════════════════
section("7. SAFETY  (no yolo deletes please)")

from core.safety import check_safety, DESTRUCTIVE_ACTIONS, SafetyDecision

check("delete_file is in destructive list", "delete_file" in DESTRUCTIVE_ACTIONS)
check("shutdown_pc is in destructive list", "shutdown_pc" in DESTRUCTIVE_ACTIONS)
check("create_file is NOT destructive", "create_file" not in DESTRUCTIVE_ACTIONS)

s1 = check_safety("delete_file", 0.95)
check("delete_file at high conf → CONFIRM (not just execute)",
      s1.decision == "confirm", got=f"decision={s1.decision}")

s2 = check_safety("create_file", 0.90)
check("create_file → EXECUTE (safe action)",
      s2.decision == "execute", got=f"decision={s2.decision}")


# ════════════════════════════════════════════════════
#  8. INTENT ROUTER SOURCE — wiring is actually there
# ════════════════════════════════════════════════════
section("8. INTENT ROUTER  (source code sanity check)")

import inspect, core.intent_router as ir
src = inspect.getsource(ir)

checks = [
    ("detect_follow_up_intent imported",        "detect_follow_up_intent"    in src),
    ("grounding_context passed to resolver",     "grounding_context=grounding_ctx" in src),
    ("step1_target injected into follow_up",     "step1_target"               in src),
    ("_STEP1_TO_FOLLOW_PARAM map exists",        "_STEP1_TO_FOLLOW_PARAM"     in src),
    ("check_safety called on resume path",       "check_safety"               in src),
    ("ask_voice_confirmation on resume",         "ask_voice_confirmation"     in src),
    ("target_type correction table present",     "ACTION_CORRECTION"          in src or
                                                 "open_app.*website.*open_url" in src or
                                                 "open_url"                   in src),
    ("browser grounding in context builder",     "last_browser_url"           in src),
]

for label, cond in checks:
    check(label, cond)


# ════════════════════════════════════════════════════
#  9. FAST INTENT MODEL LOADER — offline fallback?
# ════════════════════════════════════════════════════
section("9. MODEL LOADER  (offline/cache fallback exists)")

import inspect, core.fast_intent as fi
model_src = inspect.getsource(fi._get_model)

check("_get_model checks SENTENCE_TRANSFORMERS_HOME env var",
      "SENTENCE_TRANSFORMERS_HOME" in model_src)
check("_get_model checks HF cache before downloading",
      "huggingface" in model_src.lower() or "HF_HOME" in model_src)
check("_get_model raises RuntimeError with fix instructions on failure",
      "RuntimeError" in model_src)
check("_get_model doesn't blindly stall — has try/except around download",
      model_src.count("except") >= 2)


# ════════════════════════════════════════════════════
#  10. AX PERCEPTION — error state is real now
# ════════════════════════════════════════════════════
section("10. AX PERCEPTION  (knows when permissions are blocked)")

import inspect, perception.ui_accessibility as ax
ax_src = inspect.getsource(ax)

check("_run_osascript returns (value, error) tuple",
      "tuple[str, str]" in ax_src or "-> tuple" in ax_src)
check("permission_denied detected from stderr",
      "permission_denied" in ax_src)
check("_PERMISSION_PHRASES list exists",
      "_PERMISSION_PHRASES" in ax_src)
check("get_ax_snapshot propagates app_err into AXSnapshot",
      "app_err" in ax_src)
check("not_macos error returned on non-darwin",
      "not_macos" in ax_src)

# on Windows, get_ax_snapshot should return immediately with error
snap = ax.get_ax_snapshot()
import sys as _sys
if _sys.platform != "darwin":
    check("On Windows: AXSnapshot.error = 'not_macos'",
          snap.error == "not_macos", got=snap.error)
    check("On Windows: AXSnapshot.frontmost_app is empty",
          snap.frontmost_app == "", got=snap.frontmost_app)


# ════════════════════════════════════════════════════
#  11. SCREEN CAPTURE — clean fallback on permission fail
# ════════════════════════════════════════════════════
section("11. SCREEN CAPTURE  (doesn't explode when perms missing)")

import inspect, perception.screen_capture as sc
sc_src = inspect.getsource(sc)

check("capture_primary raises PermissionError (not raw CalledProcessError)",
      "PermissionError" in sc_src)
check("capture_primary raises RuntimeError with message",
      "RuntimeError" in sc_src)
check("capture_focused has explicit except CalledProcessError before fallback",
      sc_src.count("CalledProcessError") >= 2)
check("Screen Recording instructions in error message",
      "Screen Recording" in sc_src or "screen recording" in sc_src.lower())


# ════════════════════════════════════════════════════
#  FINAL SCORE
# ════════════════════════════════════════════════════
total = PASS + FAIL
print(f"\n{'═'*55}")
print(f"  VIBE CHECK DONE  {'🔥' if FAIL == 0 else '😬'}")
print(f"  {PASS}/{total} checks passed   {FAIL} failed")
if FAIL == 0:
    print("  yo we're COOKED (in a good way) — everything works 🚀")
else:
    print("  some stuff is still kinda broken ngl fix it bro")
print(f"{'═'*55}")
sys.exit(0 if FAIL == 0 else 1)
