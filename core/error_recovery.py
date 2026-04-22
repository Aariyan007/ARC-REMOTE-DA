"""
Error Recovery — retry-once loop with grounded failure reporting.

When verify_action() returns ok=False, the recovery loop:
  1. Checks if the action is safe to retry (SAFE_TO_RETRY set)
  2. Retries ONCE with same params
  3. Re-verifies
  4. If still fails → generates a grounded failure message explaining what
     ARC tried and what actually happened

Contract:
  - recover() never crashes — worst case it returns a RecoveryResult(success=False)
  - Callers get an actionable message, not just "it failed"
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from core.command_schema import VerificationResult


# ─── Recovery result ─────────────────────────────────────────

@dataclass
class RecoveryResult:
    """Outcome of a recovery attempt."""

    success: bool
    message: str                         # human-readable explanation
    action: str = ""
    params: dict = field(default_factory=dict)
    attempts: int = 0                    # how many times we tried
    verification: Optional[VerificationResult] = None
    alternative_tried: str = ""          # if we tried an alternate approach
    details: dict = field(default_factory=dict)


# ─── Retry policy ────────────────────────────────────────────

# Actions safe to retry (idempotent or harmless)
SAFE_TO_RETRY = {
    "create_file", "create_and_edit_file", "copy_file", "create_folder",
    "open_app", "open_url", "search_google", "new_tab",
    "open_folder", "switch_to_app", "edit_file",
}

# Actions that must NEVER be retried
NEVER_RETRY = {
    "delete_file", "delete_folder", "shutdown_pc", "restart_pc",
    "empty_trash", "format_disk", "send_email",
}

# Maximum retry count per recovery attempt
MAX_RETRIES = 1

# Delay between retries (seconds)
RETRY_DELAY = 1.0


# ─── Alternative strategies ─────────────────────────────────

# Mapping: when action X fails, try action Y with these param transforms
ALTERNATIVE_STRATEGIES: Dict[str, Dict[str, Any]] = {
    "open_app": {
        "alternative_action": "search_google",
        "param_transform": lambda p: {"query": f"download {p.get('target', '')}"},
        "reason": "App not found — searching for it instead",
    },
    "open_url": {
        "alternative_action": "search_google",
        "param_transform": lambda p: {"query": p.get("url", p.get("target", ""))},
        "reason": "URL failed — searching for it instead",
    },
    "open_folder": {
        "alternative_action": "create_folder",
        "param_transform": lambda p: {"target": p.get("target", ""), "location": p.get("location", "desktop")},
        "reason": "Folder not found — creating it",
        "condition": lambda vr: "not found" in (vr.message or "").lower(),
    },
}


# ─── Grounded failure message builder ─────────────────────────

_ACTION_VERBS = {
    "create_file": "create the file",
    "delete_file": "delete the file",
    "rename_file": "rename the file",
    "copy_file": "copy the file",
    "edit_file": "edit the file",
    "create_folder": "create the folder",
    "open_folder": "open the folder",
    "open_app": "open the app",
    "close_app": "close the app",
    "switch_to_app": "switch to the app",
    "minimise_app": "minimize the app",
    "open_url": "open the URL",
    "search_google": "run the search",
    "new_tab": "open a new tab",
    "close_tab": "close the tab",
    "send_email": "send the email",
    "shutdown_pc": "shut down",
    "restart_pc": "restart",
}


def _build_grounded_failure(action: str, params: dict,
                            verification: VerificationResult,
                            attempts: int,
                            alternative_tried: str = "") -> str:
    """
    Build a human-readable failure message grounded in what actually happened.

    Instead of: "Action failed."
    We say:     "I tried to create the file 'notes.txt' on Desktop but it wasn't
                 found after creation. I tried once more but it still didn't appear."
    """
    verb = _ACTION_VERBS.get(action, f"do '{action}'")
    target = params.get("target", params.get("filename", params.get("name", "")))

    parts = [f"I tried to {verb}"]
    if target:
        parts[0] += f" '{target}'"

    # Location context
    loc = params.get("location", "")
    if loc:
        parts[0] += f" in {loc}"

    # What went wrong
    parts.append(f"but {verification.message.lower().rstrip('.')}")

    # Retry info
    if attempts > 1:
        parts.append(f"I tried {attempts} times but it still didn't work.")

    # Alternative attempt
    if alternative_tried:
        parts.append(f"I also tried: {alternative_tried}.")

    # AX/permission issue
    details = verification.details or {}
    if details.get("reason") == "ax_unavailable":
        parts.append("Note: Accessibility permissions may not be granted.")
    if details.get("reason") == "ax_exception":
        parts.append("There was a system error checking the result.")

    return " ".join(parts)


# ─── Core recovery function ──────────────────────────────────

def recover(
    action: str,
    params: dict,
    failed_verification: VerificationResult,
    execute_fn: Callable[[str, dict], Any],
    verify_fn: Callable[[str, dict, Any, Any], VerificationResult],
    before_state: Any = None,
) -> RecoveryResult:
    """
    Attempt to recover from a failed action.

    Args:
        action:             The action that failed (e.g., "create_file")
        params:             The params used
        failed_verification: The VerificationResult that triggered recovery
        execute_fn:         Callable(action, params) → result
        verify_fn:          Callable(action, params, result, before) → VerificationResult
        before_state:       BeforeState snapshot (for re-verification)

    Returns:
        RecoveryResult with success=True/False and a grounded message
    """
    attempts = 1  # first attempt already happened

    # ── Step 1: Should we retry? ─────────────────────────────
    if action in NEVER_RETRY:
        return RecoveryResult(
            success=False,
            message=_build_grounded_failure(action, params, failed_verification, attempts),
            action=action,
            params=params,
            attempts=attempts,
            verification=failed_verification,
        )

    # ── Step 2: Retry once if safe ───────────────────────────
    if action in SAFE_TO_RETRY and attempts <= MAX_RETRIES:
        time.sleep(RETRY_DELAY)
        attempts += 1

        try:
            retry_result = execute_fn(action, params)
            retry_verification = verify_fn(action, params, retry_result, before_state)

            if retry_verification.ok:
                return RecoveryResult(
                    success=True,
                    message=f"Succeeded on retry (attempt {attempts}).",
                    action=action,
                    params=params,
                    attempts=attempts,
                    verification=retry_verification,
                )
            # Retry also failed — fall through to alternative
            failed_verification = retry_verification
        except Exception:
            pass  # retry itself failed — fall through

    # ── Step 3: Try alternative strategy ─────────────────────
    alt_tried = ""
    strategy = ALTERNATIVE_STRATEGIES.get(action)
    if strategy:
        # Check condition if present
        condition = strategy.get("condition")
        if condition is None or condition(failed_verification):
            alt_action = strategy["alternative_action"]
            alt_params = strategy["param_transform"](params)
            alt_tried = strategy["reason"]

            try:
                alt_result = execute_fn(alt_action, alt_params)
                alt_verify = verify_fn(alt_action, alt_params, alt_result, None)

                if alt_verify.ok:
                    return RecoveryResult(
                        success=True,
                        message=f"Original failed, but {alt_tried.lower()}.",
                        action=alt_action,
                        params=alt_params,
                        attempts=attempts,
                        verification=alt_verify,
                        alternative_tried=alt_tried,
                    )
            except Exception:
                pass  # alternative also failed

    # ── Step 4: Give up with grounded failure message ────────
    return RecoveryResult(
        success=False,
        message=_build_grounded_failure(
            action, params, failed_verification, attempts, alt_tried
        ),
        action=action,
        params=params,
        attempts=attempts,
        verification=failed_verification,
        alternative_tried=alt_tried,
    )


# ─── Convenience: check if recovery is worth attempting ──────

def should_attempt_recovery(action: str, verification: VerificationResult) -> bool:
    """Quick gate: should we even try recovery for this action?"""
    if verification.ok:
        return False
    if action in NEVER_RETRY:
        return False
    # Check if the failure is a permission issue (can't fix by retrying)
    details = verification.details or {}
    if details.get("reason") in ("ax_unavailable", "no_path"):
        return False
    return True
