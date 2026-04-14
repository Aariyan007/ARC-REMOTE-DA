"""
Agent Base Class — the contract every specialized agent implements.

Every agent in the system is a self-contained unit that:
1. Knows its own capabilities (tools)
2. Can execute actions within its domain
3. Reports results in a standardized format
4. Has NO access to tools outside its domain (isolation)

This ensures the ManagerAgent can route confidently — the FileSystemAgent
can never accidentally send an email, and the EmailAgent can never delete files.
"""

import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AgentResult:
    """Standardized result from any agent execution."""
    success:    bool                    # Did the action succeed?
    action:     str                     # What action was performed
    result:     str         = ""        # Human-readable result string
    data:       dict        = field(default_factory=dict)  # Structured data (for chaining)
    error:      str         = ""        # Error message if failed
    duration_ms: float      = 0.0       # How long the action took


class BaseAgent(ABC):
    """
    Abstract base class for all Jarvis agents.

    Every agent must implement:
    - name:         Unique agent identifier (e.g., "filesystem", "email")
    - description:  What this agent handles
    - capabilities: List of action names this agent can perform
    - execute():    Runs a specific action with given params
    """

    def __init__(self):
        self._action_map = {}   # action_name → method

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique agent identifier (e.g., 'filesystem', 'email')."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """What this agent handles — used by ManagerAgent for routing."""
        pass

    @property
    def capabilities(self) -> list:
        """List of action names this agent can perform."""
        return list(self._action_map.keys())

    @property
    def tools_description(self) -> str:
        """
        Human-readable description of this agent's tools.
        Used when ManagerAgent needs to describe available actions to Gemini.
        """
        lines = [f"Agent: {self.name} — {self.description}", "Actions:"]
        for action_name, method in self._action_map.items():
            doc = method.__doc__ or "No description"
            # Take first line of docstring
            first_line = doc.strip().split("\n")[0]
            lines.append(f"  - {action_name}: {first_line}")
        return "\n".join(lines)

    def can_handle(self, action: str) -> bool:
        """Returns True if this agent has the given action."""
        return action in self._action_map

    def execute(self, action: str, params: dict) -> AgentResult:
        """
        Executes the given action with params.
        Wraps the internal method with timing and error handling.
        """
        if action not in self._action_map:
            return AgentResult(
                success=False,
                action=action,
                error=f"Agent '{self.name}' does not support action '{action}'. "
                      f"Available: {', '.join(self.capabilities)}",
            )

        start = time.time()
        try:
            method = self._action_map[action]
            result = method(params)
            duration = (time.time() - start) * 1000

            if isinstance(result, AgentResult):
                result.duration_ms = duration
                return result

            # If the method returned a plain string, wrap it
            return AgentResult(
                success=True,
                action=action,
                result=str(result) if result else f"Executed {action}",
                duration_ms=duration,
            )

        except Exception as e:
            duration = (time.time() - start) * 1000
            return AgentResult(
                success=False,
                action=action,
                error=str(e),
                duration_ms=duration,
            )

    def register_action(self, name: str, method):
        """Registers a callable as an action for this agent."""
        self._action_map[name] = method

    def __repr__(self):
        return (
            f"<{self.__class__.__name__} name='{self.name}' "
            f"actions={self.capabilities}>"
        )
