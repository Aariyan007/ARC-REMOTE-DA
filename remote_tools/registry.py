"""
Tool registry. A tool is `fn(args: dict, ctx: ToolContext) -> ActionResult`.
The server runs tools inside a normal job, so events, caps, timeouts, cancel and
audit behave exactly like natural-language commands.
"""

from dataclasses import dataclass
from typing import Callable, Dict, Optional

from core.action_result import ActionResult


@dataclass
class ToolContext:
    device_id: str
    job_id: str
    emit: Callable[..., None]            # emit(type, message, data=None)

    def progress(self, message: str, **data):
        self.emit("progress", message, data or None)


@dataclass
class Tool:
    name: str
    fn: Callable[[dict, ToolContext], ActionResult]
    description: str = ""
    label: str = ""                       # shown as the job's "command" in history


_TOOLS: Dict[str, Tool] = {}


def register(name: str, description: str = "", label: str = ""):
    def deco(fn):
        _TOOLS[name] = Tool(name, fn, description, label or name)
        return fn
    return deco


def get_tool(name: str) -> Optional[Tool]:
    _load_builtin()
    return _TOOLS.get(name)


def list_tools() -> list:
    _load_builtin()
    return [{"name": t.name, "description": t.description} for t in _TOOLS.values()]


def _load_builtin():
    # imported lazily so registration happens once and import cycles can't occur
    from remote_tools import builtin  # noqa: F401
