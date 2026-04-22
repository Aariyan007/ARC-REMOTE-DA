"""
Task Planner — multi-step DAG-based task execution.

Upgrades ARC from linear 2-step chaining to a proper task graph:
  - Parse complex commands into a TaskPlan (ordered list of TaskSteps)
  - Execute steps in dependency order
  - Pass results from parent steps into child steps (context injection)
  - Handle failure mid-chain: stop, report what succeeded and what didn't

Design:
  - Deterministic parsing (regex), no LLM calls
  - Steps are connected by result-forwarding rules
  - Each step knows its dependencies (which prior steps must succeed first)

Example:
  "create a folder called projects, make a file inside it, and write hello"
  → Step 1: create_folder(target="projects")
  → Step 2: create_file(location="projects")     [depends on step 1]
  → Step 3: edit_file(location="projects")        [depends on step 2]
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


# ─── Data structures ─────────────────────────────────────────

@dataclass
class TaskStep:
    """Single step in a task plan."""

    step_id: int
    action: str
    params: dict = field(default_factory=dict)
    depends_on: List[int] = field(default_factory=list)  # step_ids this depends on
    inject_from: str = ""         # which result key to inject from parent
    inject_as: str = ""           # param key to receive the injected value

    # Filled during execution
    status: str = "pending"       # pending | running | done | failed | skipped
    result: Any = None
    error: str = ""
    verification_ok: Optional[bool] = None


@dataclass
class TaskPlan:
    """Ordered plan of task steps with dependency tracking."""

    steps: List[TaskStep] = field(default_factory=list)
    original_command: str = ""
    is_multi_step: bool = False

    def add_step(self, action: str, params: dict = None,
                 depends_on: List[int] = None,
                 inject_from: str = "", inject_as: str = "") -> TaskStep:
        step = TaskStep(
            step_id=len(self.steps),
            action=action,
            params=params or {},
            depends_on=depends_on or [],
            inject_from=inject_from,
            inject_as=inject_as,
        )
        self.steps.append(step)
        if len(self.steps) > 1:
            self.is_multi_step = True
        return step

    def get_step(self, step_id: int) -> Optional[TaskStep]:
        if 0 <= step_id < len(self.steps):
            return self.steps[step_id]
        return None

    def all_done(self) -> bool:
        return all(s.status in ("done", "failed", "skipped") for s in self.steps)

    def any_failed(self) -> bool:
        return any(s.status == "failed" for s in self.steps)

    def summary(self) -> str:
        lines = []
        for s in self.steps:
            icon = {"done": "✅", "failed": "❌", "skipped": "⏭️",
                    "running": "🔄", "pending": "⏳"}.get(s.status, "?")
            lines.append(f"  {icon} Step {s.step_id}: {s.action}({s.params}) → {s.status}")
            if s.error:
                lines.append(f"      └─ {s.error}")
        return "\n".join(lines)


# ─── Result injection rules ──────────────────────────────────

# When step N produces a result, what key should be forwarded to step N+1?
RESULT_FORWARD_RULES: Dict[str, Dict[str, str]] = {
    # parent_action → {inject_from: what result key, inject_as: what param key}
    "create_folder": {"inject_from": "target",   "inject_as": "location"},
    "create_file":   {"inject_from": "filename",  "inject_as": "filename"},
    "open_folder":   {"inject_from": "target",   "inject_as": "location"},
    "rename_file":   {"inject_from": "new_name",  "inject_as": "filename"},
    # file → email: pass resolved path as attachment_path
    "search_file":   {"inject_from": "path",      "inject_as": "attachment_path"},
    "read_file":     {"inject_from": "path",      "inject_as": "attachment_path"},
}


# ─── Command parsing ─────────────────────────────────────────

# Conjunction patterns that split multi-step commands
_SPLIT_PATTERNS = [
    r',\s*(?:and\s+)?then\s+',       # ", then" / ", and then"
    r'\s+and\s+then\s+',             # "and then"
    r'\s+then\s+',                    # "then"
    r';\s*',                          # semicolon
    r',\s+(?:i\s+(?:want|need)\s+to\s+)',  # ", I want to"
    r'\s+after\s+that\s+',           # "after that"
    r',\s*(?:also|next)\s+',         # ", also" / ", next"
    # Comma before a new action verb (the big one)
    r',\s+(?=(?:make|create|open|close|delete|rename|copy|search|send|write|edit|go)\b)',
    # "and" before a new action verb
    r'\s+and\s+(?=(?:search|open|close|delete|create|make|write|edit|go|send)\b)',
]

_SPLIT_REGEX = re.compile('|'.join(f'({p})' for p in _SPLIT_PATTERNS), re.IGNORECASE)

# Action keyword mapping for each fragment
_FRAGMENT_ACTION_MAP = [
    (r'\b(?:make|create)\b.*\bfolder\b', "create_folder"),
    (r'\b(?:make|create)\b.*\b(?:file|\w+\.\w{1,5})\b', "create_file"),
    (r'\b(?:write|put|type|add|edit)\b',  "edit_file"),
    (r'\bdelete\b',                       "delete_file"),
    (r'\brename\b',                       "rename_file"),
    (r'\bcopy\b',                         "copy_file"),
    (r'\b(?:go\s+to|open)\b.*\bfolder\b', "open_folder"),
    (r'\b(?:go\s+to|open)\b.*\b(?:downloads|documents|desktop|photos)\b', "open_folder"),
    (r'\b(?:open|launch|run)\b.*(?:chrome|firefox|safari|vscode|spotify|terminal|finder|slack|discord)', "open_app"),
    (r'\b(?:open|launch|run)\b',          "open_app"),
    (r'\bclose\b.*\btab\b',             "close_tab"),
    (r'\bclose\b',                        "close_app"),
    (r'\bsearch\b',                       "search_google"),
    (r'\bsend\b.*\bemail\b',            "send_email"),
    (r'\bshutdown\b|\bshut\s+down\b',   "shutdown_pc"),
]

# Param extraction patterns
_PARAM_PATTERNS = {
    "target": [
        r'(?:called|named)\s+["\']?([^"\',.;]+)',
        r'(?:folder|app|file)\s+["\']?([^"\',.;]+)',
    ],
    "filename": [
        r'(?:file\s+)?(?:called|named)\s+["\']?([^"\',.;]+)',
    ],
    "content": [
        r'(?:write|put|type|add)\s+["\']?(.+?)(?:["\']?\s*(?:in|into|to|inside)|\s*$)',
    ],
    "query": [
        r'(?:search\s+(?:for\s+)?|google\s+)["\']?(.+?)(?:["\']|$)',
    ],
    "new_name": [
        r'(?:rename\s+(?:it\s+)?to\s+|to\s+)["\']?([^"\',.;]+)',
    ],
    "location": [
        r'(?:in|inside|into)\s+["\']?([^"\',.;]+?)(?:\s*$|\s*,)',
    ],
}


def _extract_action(fragment: str) -> str:
    """Determine the action from a command fragment."""
    frag_lower = fragment.lower().strip()
    for pattern, action in _FRAGMENT_ACTION_MAP:
        if re.search(pattern, frag_lower):
            return action
    return ""


def _extract_params(fragment: str, action: str) -> dict:
    """Extract parameters from a command fragment based on the action."""
    params = {}
    frag = fragment.strip()

    for param_key, patterns in _PARAM_PATTERNS.items():
        for pattern in patterns:
            m = re.search(pattern, frag, re.IGNORECASE)
            if m:
                val = m.group(1).strip().rstrip('.,;!?')
                if val and val.lower() not in ('it', 'that', 'this', 'them'):
                    params[param_key] = val
                break

    # Infer target from the fragment if not extracted
    if "target" not in params and "filename" not in params:
        # Try to get the object noun after the verb
        m = re.search(
            r'\b(?:open|close|delete|create|make|rename)\s+(?:a\s+|the\s+|my\s+)?'
            r'(?:file|folder|app|tab)?\s*(?:called\s+|named\s+)?["\']?([a-zA-Z0-9_.\- ]+)',
            frag, re.IGNORECASE
        )
        if m:
            candidate = m.group(1).strip().rstrip('.,;!?')
            # Don't capture action verbs as targets
            if candidate.lower() not in ('a', 'the', 'my', 'and', 'then', 'it', 'that'):
                if action in ("create_file", "edit_file", "rename_file", "delete_file", "copy_file"):
                    params["filename"] = candidate
                else:
                    params["target"] = candidate

    return params


def parse_task_plan(command: str) -> TaskPlan:
    """
    Parse a potentially multi-step command into a TaskPlan.

    Examples:
      "open chrome"
      → 1-step plan: [open_app(target=chrome)]

      "create a folder called projects, make a file inside it, write hello"
      → 3-step plan with dependencies

      "make a file and then delete it"
      → 2-step plan: [create_file, delete_file] with dependency

    Returns a TaskPlan with steps in execution order.
    """
    plan = TaskPlan(original_command=command)

    # Split on conjunctions
    fragments = _SPLIT_REGEX.split(command)
    # Filter out None and separator captures
    fragments = [f.strip() for f in fragments if f and f.strip()
                 and not re.match(r'^(?:,?\s*(?:and\s+)?then|;\s*|,?\s*(?:also|next)|after\s+that)',
                                  f.strip(), re.IGNORECASE)]

    if not fragments:
        fragments = [command]

    prev_step_id = None
    for frag in fragments:
        action = _extract_action(frag)
        if not action:
            continue

        params = _extract_params(frag, action)
        depends = [prev_step_id] if prev_step_id is not None else []

        # Set up result injection from parent step
        inject_from = ""
        inject_as = ""
        if prev_step_id is not None:
            prev_step = plan.get_step(prev_step_id)
            if prev_step:
                rule = RESULT_FORWARD_RULES.get(prev_step.action, {})
                inject_from = rule.get("inject_from", "")
                inject_as = rule.get("inject_as", "")

        step = plan.add_step(
            action=action,
            params=params,
            depends_on=depends,
            inject_from=inject_from,
            inject_as=inject_as,
        )
        prev_step_id = step.step_id

    return plan


# ─── Plan execution ──────────────────────────────────────────

def _inject_parent_result(step: TaskStep, plan: TaskPlan) -> None:
    """Inject result from parent step into this step's params."""
    if not step.depends_on or not step.inject_as:
        return

    for dep_id in step.depends_on:
        parent = plan.get_step(dep_id)
        if parent and parent.status == "done" and parent.result is not None:
            # Get the value to inject
            if step.inject_from:
                # Try to get from result data
                if hasattr(parent.result, 'data'):
                    val = parent.result.data.get(step.inject_from, "")
                elif isinstance(parent.result, dict):
                    val = parent.result.get(step.inject_from, "")
                else:
                    val = ""

                # Fall back to parent params if result doesn't have it
                if not val:
                    val = parent.params.get(step.inject_from,
                          parent.params.get("target", ""))
            else:
                val = parent.params.get("target",
                      parent.params.get("filename", ""))

            if val:
                step.params[step.inject_as] = val
                # Also set as target fallback
                if "target" not in step.params:
                    step.params["target"] = val


def execute_plan(
    plan: TaskPlan,
    execute_fn,        # Callable(action, params) → result
    verify_fn=None,    # Callable(action, params, result, before) → VerificationResult
    recover_fn=None,   # Callable(action, params, verification) → RecoveryResult
    before_fn=None,    # Callable(action, params) → BeforeState
) -> TaskPlan:
    """
    Execute a TaskPlan step by step.

    Args:
        plan:       The plan to execute
        execute_fn: Actually runs the action → returns result
        verify_fn:  Verifies the result (optional)
        recover_fn: Attempts recovery on failure (optional)
        before_fn:  Captures before-state for verification (optional)

    Returns:
        The same TaskPlan with step statuses updated.
    """
    for step in plan.steps:
        # Check dependencies
        deps_ok = True
        for dep_id in step.depends_on:
            parent = plan.get_step(dep_id)
            if parent and parent.status != "done":
                deps_ok = False
                break

        if not deps_ok:
            step.status = "skipped"
            step.error = "Skipped because a prior step failed."
            continue

        # Inject parent results into params
        _inject_parent_result(step, plan)

        # Capture before state
        before = None
        if before_fn:
            try:
                before = before_fn(step.action, step.params)
            except Exception:
                pass

        # Execute
        step.status = "running"
        try:
            step.result = execute_fn(step.action, step.params)
        except Exception as e:
            step.status = "failed"
            step.error = f"Execution error: {e}"
            continue

        # Verify
        if verify_fn:
            try:
                vr = verify_fn(step.action, step.params, step.result, before)
                step.verification_ok = vr.ok

                if not vr.ok and recover_fn:
                    # Try recovery
                    recovery = recover_fn(step.action, step.params, vr)
                    if recovery.success:
                        step.status = "done"
                        step.result = recovery.verification
                        step.verification_ok = True
                        continue
                    else:
                        step.status = "failed"
                        step.error = recovery.message
                        continue

                if not vr.ok:
                    step.status = "failed"
                    step.error = vr.message
                    continue
            except Exception as e:
                # Verification crashed — still mark as done (best effort)
                step.verification_ok = None

        step.status = "done"

    return plan


# ─── Convenience ─────────────────────────────────────────────

def plan_summary_message(plan: TaskPlan) -> str:
    """Build a user-facing summary of the plan execution."""
    done = [s for s in plan.steps if s.status == "done"]
    failed = [s for s in plan.steps if s.status == "failed"]
    skipped = [s for s in plan.steps if s.status == "skipped"]

    parts = []
    if done:
        parts.append(f"✅ {len(done)} step(s) completed")
    if failed:
        parts.append(f"❌ {len(failed)} step(s) failed")
        for s in failed:
            parts.append(f"   └─ {s.action}: {s.error}")
    if skipped:
        parts.append(f"⏭️ {len(skipped)} step(s) skipped (dependency failed)")

    return "\n".join(parts) if parts else "No steps executed."
