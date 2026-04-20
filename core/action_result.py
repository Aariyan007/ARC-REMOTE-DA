"""
ActionResult — Structured return type for every executor.

Every action in the system returns this instead of a loose string.
The response_policy module uses it to generate grounded spoken text.
"""

from dataclasses import dataclass, field


@dataclass
class ActionResult:
    """Standardized result from any action execution."""
    success: bool                           # Did the action succeed?
    action: str                             # What action was performed
    summary: str = ""                       # e.g. "Renamed notes.txt to ideas.txt"
    error: str = ""                         # e.g. "File not found: notes.txt"
    data: dict = field(default_factory=dict) # Structured payload for chaining
    user_message: str = ""                  # Optional override for what to speak
    verified: bool = False                  # Was outcome verified post-execution

    @staticmethod
    def ok(action: str, summary: str, **kwargs) -> "ActionResult":
        """Shorthand for a successful result."""
        return ActionResult(success=True, action=action, summary=summary, **kwargs)

    @staticmethod
    def fail(action: str, error: str, **kwargs) -> "ActionResult":
        """Shorthand for a failed result."""
        return ActionResult(success=False, action=action, error=error, **kwargs)

    @staticmethod
    def from_agent_result(agent_result) -> "ActionResult":
        """Convert an AgentResult (from base_agent.py) to ActionResult."""
        return ActionResult(
            success=agent_result.success,
            action=agent_result.action,
            summary=agent_result.result if agent_result.success else "",
            error=agent_result.error if not agent_result.success else "",
            data=agent_result.data if hasattr(agent_result, 'data') else {},
        )


# ─── Quick test ──────────────────────────────────────────────
if __name__ == "__main__":
    r1 = ActionResult.ok("open_app", "Opened Chrome", data={"app": "chrome"})
    print(f"OK:   {r1}")

    r2 = ActionResult.fail("rename_file", "File not found: notes.txt")
    print(f"FAIL: {r2}")

    print("\n✅ ActionResult test passed!")
