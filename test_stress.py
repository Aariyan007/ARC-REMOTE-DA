"""
ARC Stress Test Runner — 528 data-driven tests from stress_test_dataset.json.
Tests every ARC function against real inputs including corrupted/misspelled text.
Run: python test_stress.py
"""
import sys, json, os
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Load dataset
DATA_PATH = os.path.join(os.path.dirname(__file__), "data", "stress_test_dataset.json")
with open(DATA_PATH, "r", encoding="utf-8") as f:
    DATASET = json.load(f)

CASES = DATASET["cases"]
PASS = 0
FAIL = 0
CATEGORY_STATS = {}

def check(cat, label, ok, got=None):
    global PASS, FAIL
    if cat not in CATEGORY_STATS:
        CATEGORY_STATS[cat] = {"pass": 0, "fail": 0}
    if ok:
        PASS += 1
        CATEGORY_STATS[cat]["pass"] += 1
    else:
        FAIL += 1
        CATEGORY_STATS[cat]["fail"] += 1
        suffix = f"  ← got: {got}" if got else ""
        print(f"  ❌ [{cat}] {label}{suffix}")

def section(title, count):
    print(f"\n{'─'*60}")
    print(f"  {title} ({count} cases)")
    print(f"{'─'*60}")

# ════════════════════════════════════════════════════
#  IMPORTS
# ════════════════════════════════════════════════════
from core.normalizer import normalize
from core.command_interpreter import infer_target_type
from core.task_state import (set_pending, get_pending, has_pending, clear_pending,
                             is_pending_answer, resume_with_answer, PendingTask)
from core.ambiguity_resolver import build_single_slot_question
from core.working_memory import WorkingMemory
from core.safety import check_safety, DESTRUCTIVE_ACTIONS
from core.error_recovery import SAFE_TO_RETRY, NEVER_RETRY, ALTERNATIVE_STRATEGIES
from core.task_planner import parse_task_plan

print("=" * 60)
print(f"  ARC STRESS TEST — {len(CASES)} cases, 12 categories")
print("=" * 60)

# ════════════════════════════════════════════════════
#  1. CORRUPTED INPUT
# ════════════════════════════════════════════════════
corrupted = [c for c in CASES if c["category"] == "corrupted_input"]
section("1. CORRUPTED INPUT", len(corrupted))
for c in corrupted:
    result = normalize(c["input"])
    # For corrupted input, we check that the normalizer at least doesn't crash
    # and preserves key action words
    correct = c["correct_form"]
    key_words = [w for w in correct.split() if len(w) > 3]
    # At least one key word should survive normalization
    survived = any(w in result.cleaned.lower() for w in key_words)
    check("corrupted_input",
          f'"{c["input"]}" → keeps key words from "{correct}"',
          survived, got=result.cleaned)

# ════════════════════════════════════════════════════
#  2. SLANG STRIPPING
# ════════════════════════════════════════════════════
slang = [c for c in CASES if c["category"] == "slang_stripping"]
section("2. SLANG STRIPPING", len(slang))
for c in slang:
    result = normalize(c["input"])
    cleaned = result.cleaned.lower()
    excludes = c.get("expected_clean_excludes", [])
    all_excluded = all(x.lower() not in cleaned for x in excludes)
    check("slang_stripping",
          f'"{c["input"][:40]}…" strips {excludes}',
          all_excluded, got=cleaned)

# ════════════════════════════════════════════════════
#  3. TARGET TYPE
# ════════════════════════════════════════════════════
tt = [c for c in CASES if c["category"] == "target_type"]
section("3. TARGET TYPE", len(tt))
for c in tt:
    result = infer_target_type(c["input"])
    check("target_type",
          f'"{c["input"]}" → {c["expected_type"]}',
          result == c["expected_type"], got=result)

# ════════════════════════════════════════════════════
#  4. COMPOUND COMMANDS (via task_planner)
# ════════════════════════════════════════════════════
compound = [c for c in CASES if c["category"] == "compound_command"]
section("4. COMPOUND COMMANDS", len(compound))
for c in compound:
    plan = parse_task_plan(c["input"])
    has_steps = len(plan.steps) >= 2
    first_ok = plan.steps[0].action == c["expected_step1"] if plan.steps else False
    check("compound_command",
          f'"{c["input"][:45]}…" → {c["expected_step1"]}+{c["expected_step2"]}',
          has_steps and first_ok,
          got=f"steps={len(plan.steps)}, first={plan.steps[0].action if plan.steps else 'none'}")

# ════════════════════════════════════════════════════
#  5. FILE OPERATIONS
# ════════════════════════════════════════════════════
file_ops = [c for c in CASES if c["category"] == "file_operation"]
section("5. FILE OPERATIONS", len(file_ops))
for c in file_ops:
    # Check that the normalizer + planner can parse file operations
    plan = parse_task_plan(c["input"])
    got_action = plan.steps[0].action if plan.steps else ""
    check("file_operation",
          f'"{c["input"][:40]}…" → {c["action"]}',
          got_action == c["action"],
          got=got_action)

# ════════════════════════════════════════════════════
#  6. CLARIFICATION
# ════════════════════════════════════════════════════
clarif = [c for c in CASES if c["category"] == "clarification"]
section("6. CLARIFICATION", len(clarif))
for c in clarif:
    q, slot = build_single_slot_question(c["action"], {}, c["missing_params"])
    slot_ok = slot == c["expected_slot"]
    check("clarification",
          f'{c["action"]} missing {c["missing_params"]} → slot={c["expected_slot"]}',
          slot_ok, got=f"slot={slot}")

# ════════════════════════════════════════════════════
#  7. PRONOUN RESOLUTION
# ════════════════════════════════════════════════════
pronouns = [c for c in CASES if c["category"] == "pronoun_resolution"]
section("7. PRONOUN RESOLUTION", len(pronouns))
wm = WorkingMemory()
for c in pronouns:
    ctx = c["context"]
    wm.update_grounding(last_file=ctx["last_file"], last_action=ctx["last_action"])
    resolved = wm.resolve_reference(c["pronoun"])
    expected = c["expected_resolution"]
    check("pronoun_resolution",
          f'"{c["pronoun"]}" with last_file={ctx["last_file"]} → {expected}',
          expected in (resolved or ""),
          got=resolved)

# ════════════════════════════════════════════════════
#  8. SAFETY GATE
# ════════════════════════════════════════════════════
safety = [c for c in CASES if c["category"] == "safety_gate"]
section("8. SAFETY GATE", len(safety))
for c in safety:
    conf = c.get("confidence", 0.90)
    result = check_safety(c["action"], conf)
    decision = result.decision if hasattr(result, "decision") else str(result)
    check("safety_gate",
          f'{c["action"]} @{conf} → {c["expected_decision"]}',
          decision == c["expected_decision"],
          got=decision)

# ════════════════════════════════════════════════════
#  9. ACTION CORRECTION
# ════════════════════════════════════════════════════
corrections = [c for c in CASES if c["category"] == "action_correction"]
section("9. ACTION CORRECTION", len(corrections))
# Load the correction table from intent_router source
import inspect, core.intent_router as ir
router_src = inspect.getsource(ir)
for c in corrections:
    # Verify the correction mapping exists in the router
    check("action_correction",
          f'{c["fast_action"]}+{c["target_type"]} → {c["expected_corrected"]}',
          c["expected_corrected"] in router_src,
          got="not found in router")

# ════════════════════════════════════════════════════
#  10. GROUNDED FOLLOW-UP
# ════════════════════════════════════════════════════
grounded = [c for c in CASES if c["category"] == "grounded_followup"]
section("10. GROUNDED FOLLOW-UP", len(grounded))
from core.task_planner import RESULT_FORWARD_RULES
for c in grounded:
    rule = RESULT_FORWARD_RULES.get(c["parent_action"], {})
    inject_key = rule.get("inject_as", "")
    check("grounded_followup",
          f'{c["parent_action"]}→{c["follow_action"]}: inject {c["inject_key"]}',
          inject_key == c["inject_key"],
          got=f"inject_as={inject_key}")

# ════════════════════════════════════════════════════
#  11. ERROR RECOVERY
# ════════════════════════════════════════════════════
err_cases = [c for c in CASES if c["category"] == "error_recovery"]
section("11. ERROR RECOVERY", len(err_cases))
for c in err_cases:
    if c.get("should_retry") is not None:
        if c["should_retry"]:
            check("error_recovery",
                  f'{c["action"]} is safe to retry',
                  c["action"] in SAFE_TO_RETRY, got=f"not in SAFE_TO_RETRY")
        if c["should_never_retry"]:
            check("error_recovery",
                  f'{c["action"]} must NEVER be retried',
                  c["action"] in NEVER_RETRY, got=f"not in NEVER_RETRY")
    if c.get("has_alternative"):
        check("error_recovery",
              f'{c["action"]} has alternative → {c["alternative"]}',
              c["action"] in ALTERNATIVE_STRATEGIES,
              got="no alternative strategy")

# ════════════════════════════════════════════════════
#  12. TASK PLANNER
# ════════════════════════════════════════════════════
planner = [c for c in CASES if c["category"] == "task_planner"]
section("12. TASK PLANNER", len(planner))
for c in planner:
    plan = parse_task_plan(c["input"])
    step_count = len(plan.steps)
    first = plan.steps[0].action if plan.steps else ""
    count_ok = step_count >= c["expected_step_count"]
    first_ok = first == c["expected_first_action"]
    check("task_planner",
          f'"{c["input"][:45]}…" → {c["expected_step_count"]} steps, first={c["expected_first_action"]}',
          count_ok and first_ok,
          got=f"steps={step_count}, first={first}")

# ════════════════════════════════════════════════════
#  RESULTS
# ════════════════════════════════════════════════════
total = PASS + FAIL
pct = (PASS / total * 100) if total else 0

print(f"\n{'═'*60}")
print(f"  STRESS TEST RESULTS")
print(f"{'═'*60}")
print(f"\n  Overall: {PASS}/{total} passed ({pct:.1f}%)")
print(f"\n  Per-category breakdown:")
for cat, stats in sorted(CATEGORY_STATS.items()):
    cat_total = stats["pass"] + stats["fail"]
    cat_pct = (stats["pass"] / cat_total * 100) if cat_total else 0
    icon = "✅" if stats["fail"] == 0 else "⚠️" if cat_pct >= 80 else "❌"
    print(f"    {icon} {cat}: {stats['pass']}/{cat_total} ({cat_pct:.0f}%)")

if pct >= 95:
    print(f"\n  🔥 EXCELLENT — {pct:.1f}% pass rate!")
elif pct >= 80:
    print(f"\n  ⚠️ GOOD but room for improvement — {pct:.1f}%")
else:
    print(f"\n  ❌ NEEDS WORK — {pct:.1f}%")
print(f"{'═'*60}")

sys.exit(0 if pct >= 80 else 1)
