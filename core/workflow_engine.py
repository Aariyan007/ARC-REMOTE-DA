"""
Workflow Engine — deterministic multi-step command execution.

Matches free-text commands to pre-built workflow templates.
Templates run step-by-step without LLM planning for common use cases.
LLM (agent/task_planner) is the fallback for unknown workflows.

Supported workflows:
  - find_and_email_file:  "find X and email it to Y"
  - find_and_open_file:   "find X and open it"
  - search_and_summarize: "search X and summarize"
"""

from __future__ import annotations

import re
import time
from typing import Optional

from core.command_models import (
    CommandResponse, ExecutionStatus, StepResult
)


# ─── Workflow matching patterns ────────────────────────────────

_WORKFLOW_PATTERNS: list[tuple[str, list[str]]] = [
    # ("find_and_email_file", [
    #     r"(?:find|search|locate)\s+.+\s+(?:and\s+)?(?:email|send|mail)\s+(?:it\s+)?(?:to\s+)",
    #     r"(?:email|send|mail)\s+.+(?:\.txt|\.pdf|\.docx|\.csv|\.xlsx|\.py|\.json)\s+to\s+",
    #     r"(?:find|search)\s+file\s+.+\s+(?:and\s+)?(?:email|send)\s+",
    # ]),
    ("find_and_open_file", [
        r"(?:find|search|locate)\s+.+\s+(?:and\s+)?(?:open|show|read)\s+(?:it\b|the\s+file\b)",
    ]),
]


# ─── Parameter extractors for workflows ───────────────────────

def _extract_find_email_params(text: str) -> dict:
    """
    Extract filename + recipient from a 'find X and email to Y' command.
    Returns: { filename, recipient } — both may be empty strings if not found.
    """
    params: dict = {"filename": "", "recipient": ""}
    text_lower = text.lower()

    # ── Extract recipient (email address or name after "to") ──
    email_match = re.search(
        r'\bto\s+([\w._%+\-]+@[\w.\-]+\.[a-zA-Z]{2,})', text, re.IGNORECASE
    )
    if email_match:
        params["recipient"] = email_match.group(1).strip()
    else:
        # "to aariyan" / "to my friend john" → name
        to_match = re.search(
            r'\b(?:email|send|mail)\s+(?:it\s+)?to\s+([\w]+)', text_lower
        )
        if to_match:
            params["recipient"] = to_match.group(1).strip()

    # ── Extract filename ------------------------------------------
    # Pattern 1: explicit filename with extension — match the shortest
    # word-sequence immediately before the extension, not the whole phrase.
    file_match = re.search(
        r'\b([\w][\w\-.]*\.(?:txt|pdf|docx|xlsx|csv|py|json|md|pptx|jpg|png|mp4|zip))\b',
        text, re.IGNORECASE
    )
    if file_match:
        params["filename"] = file_match.group(1).strip()
    else:
        # Pattern 2: "find/search [the file] X and email ..."
        # Use \S+ (no spaces) so we get exactly one token (the filename stem)
        name_match = re.search(
            r'(?:find|search|locate)\s+(?:the\s+)?(?:file\s+)?(\S+?)\s+'
            r'(?:and\s+)?(?:email|send|mail)',
            text_lower
        )
        if name_match:
            candidate = name_match.group(1).strip()
            if candidate not in {"the", "a", "an", "my", "its", "that", "this", "file"}:
                params["filename"] = candidate

    return params


def _extract_find_open_params(text: str) -> dict:
    params: dict = {"filename": ""}
    file_match = re.search(
        r'\b([\w\-. ]+\.(?:txt|pdf|docx|xlsx|csv|py|json|md|pptx))\b',
        text, re.IGNORECASE
    )
    if file_match:
        params["filename"] = file_match.group(1).strip()
    return params


# ─── Workflow implementations ──────────────────────────────────

def _run_find_and_email(
    text: str, request_id: str, source: str
) -> CommandResponse:
    """
    Step 1: resolve_best_file(filename)
    Step 2: draft_email_with_attachment(to, attachment_path)
    """
    steps: list[StepResult] = []
    params = _extract_find_email_params(text)
    filename = params.get("filename", "")
    recipient = params.get("recipient", "")

    print(f"📧 FindAndEmail: file='{filename}' recipient='{recipient}'")

    if not filename:
        return CommandResponse.fail(
            request_id, "find_and_email_file",
            "I couldn't find a filename in your command. Try: find uber.txt and email it to someone@email.com",
            source=source,
        )

    # ── Step 1: Find the file ────────────────────────────────
    step1 = StepResult(step_id=0, action="resolve_best_file", status="running")
    steps.append(step1)

    try:
        from control.windows.folder_control import resolve_best_file
        resolution = resolve_best_file(filename)
        step1.data = {
            "resolved": resolution.resolved,
            "path": resolution.path,
            "matches": [
                {"path": m.path, "name": m.name, "score": m.score}
                for m in resolution.matches
            ],
            "reason": resolution.reason,
        }

        if not resolution.resolved:
            if resolution.reason == "ambiguous":
                step1.status = "done"
                candidates = [m.path for m in resolution.matches[:5]]
                return CommandResponse.needs_confirmation(
                    request_id, "find_and_email_file",
                    f"Found {len(resolution.matches)} files matching '{filename}'. "
                    f"Which one? {', '.join(m.name for m in resolution.matches[:5])}",
                    data={"candidates": candidates, "filename": filename, "recipient": recipient},
                    source=source,
                )
            step1.status = "failed"
            step1.error = f"File '{filename}' not found in Desktop, Documents, or Downloads."
            return CommandResponse.fail(
                request_id, "find_and_email_file",
                f"Couldn't find '{filename}' anywhere on your PC.",
                steps=steps, source=source,
            )

        step1.status = "done"
        step1.summary = f"Found: {resolution.path}"
        file_path = resolution.path
        file_name = resolution.matches[0].name if resolution.matches else filename
        print(f"  ✔ Found: {file_path}")
    except Exception as e:
        step1.status = "failed"
        step1.error = str(e)
        return CommandResponse.fail(
            request_id, "find_and_email_file",
            f"File search error: {e}", steps=steps, source=source,
        )

    # ── Step 2: Email with attachment ────────────────────────
    if not recipient:
        # Can't proceed without a recipient — return partial result
        return CommandResponse.needs_confirmation(
            request_id, "find_and_email_file",
            f"Found '{file_name}' at {file_path}. Who should I email it to?",
            data={"file_path": file_path, "file_name": file_name},
            source=source,
        )

    step2 = StepResult(step_id=1, action="draft_email_with_attachment", status="running")
    steps.append(step2)

    try:
        from control.email_control import draft_email_with_attachment
        result = draft_email_with_attachment(
            to=recipient,
            subject=f"Here is {file_name}",
            body="",
            attachment_path=file_path,
            announce=(source == "voice"),
        )
        if result.get("success"):
            step2.status = "done"
            step2.summary = f"Draft opened for {recipient}"
            step2.verified = result.get("attachment_verified", False)
            step2.data = result

            verified_msg = " Attachment confirmed." if step2.verified else " Please verify the attachment manually."
            return CommandResponse.ok(
                request_id, "find_and_email_file",
                f"Done. Gmail compose opened with '{file_name}' attached, addressed to {recipient}.{verified_msg}",
                steps=steps,
                data={"file_path": file_path, "recipient": recipient, "attachment_verified": step2.verified},
                source=source,
            )
        else:
            step2.status = "failed"
            step2.error = result.get("error", "Unknown error opening Gmail")
            return CommandResponse.fail(
                request_id, "find_and_email_file",
                f"Found the file but couldn't open Gmail: {step2.error}",
                steps=steps, source=source,
            )
    except Exception as e:
        step2.status = "failed"
        step2.error = str(e)
        return CommandResponse.fail(
            request_id, "find_and_email_file",
            f"Email error: {e}", steps=steps, source=source,
        )


def _run_find_and_open(
    text: str, request_id: str, source: str
) -> CommandResponse:
    """Step 1: resolve_best_file → Step 2: open file."""
    steps: list[StepResult] = []
    params = _extract_find_open_params(text)
    filename = params.get("filename", "")

    if not filename:
        return CommandResponse.fail(
            request_id, "find_and_open_file",
            "I couldn't find a filename in your command.",
            source=source,
        )

    step1 = StepResult(step_id=0, action="resolve_best_file", status="running")
    steps.append(step1)

    try:
        from control.windows.folder_control import resolve_best_file
        resolution = resolve_best_file(filename)

        if not resolution.resolved:
            step1.status = "failed"
            step1.error = f"File '{filename}' not found."
            return CommandResponse.fail(
                request_id, "find_and_open_file",
                f"Couldn't find '{filename}'.", steps=steps, source=source,
            )

        step1.status = "done"
        step1.summary = f"Found: {resolution.path}"
        file_path = resolution.path

        import os
        os.startfile(file_path)

        if source == "voice":
            from core.voice_response import speak
            speak(f"Opening {os.path.basename(file_path)}.")

        return CommandResponse.ok(
            request_id, "find_and_open_file",
            f"Opened '{os.path.basename(file_path)}'.",
            steps=steps,
            data={"file_path": file_path},
            source=source,
        )
    except Exception as e:
        step1.status = "failed"
        step1.error = str(e)
        return CommandResponse.fail(
            request_id, "find_and_open_file",
            str(e), steps=steps, source=source,
        )


# ─── WorkflowEngine ───────────────────────────────────────────

class WorkflowEngine:
    """Matches commands to deterministic workflows and executes them."""

    def match(self, text: str) -> Optional[str]:
        """
        Returns the workflow name if the command matches a known template.
        Returns None if no match — caller should fall back to LLM/intent router.
        """
        text_lower = text.lower().strip()
        for workflow_name, patterns in _WORKFLOW_PATTERNS:
            for pattern in patterns:
                if re.search(pattern, text_lower, re.IGNORECASE):
                    return workflow_name
        return None

    def run(
        self,
        workflow_name: str,
        text: str,
        request_id: str,
        *,
        source: str = "voice",
    ) -> CommandResponse:
        """Execute a named workflow and return a CommandResponse."""
        start = time.time()

        if workflow_name == "find_and_email_file":
            response = _run_find_and_email(text, request_id, source)
        elif workflow_name == "find_and_open_file":
            response = _run_find_and_open(text, request_id, source)
        else:
            response = CommandResponse.fail(
                request_id, workflow_name,
                f"Unknown workflow: {workflow_name}", source=source,
            )

        response.elapsed_ms = (time.time() - start) * 1000

        # Speak result for voice source
        if source == "voice":
            try:
                from core.voice_response import speak
                speak(response.final_result)
            except Exception:
                pass

        return response


# ─── Singleton ────────────────────────────────────────────────

_engine: Optional[WorkflowEngine] = None


def get_workflow_engine() -> WorkflowEngine:
    global _engine
    if _engine is None:
        _engine = WorkflowEngine()
    return _engine
