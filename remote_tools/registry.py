"""
Tool registry. A tool is `fn(args: dict, ctx: ToolContext) -> ActionResult`.

Every tool declares a JSON parameter schema (used both to tell the chat model how to
call it and to validate the arguments it sends back) and a risk level:

  read    - observes only; runs without asking
  change  - alters the laptop or sends something out; always needs a human confirm
  danger  - like change, but destructive/hard to undo; confirm card is flagged

The confirm requirement is enforced in code (see remote_tools.agent), never left to
the model's good behaviour.
"""

from dataclasses import dataclass, field
from typing import Callable, Dict, Optional

from core.action_result import ActionResult

RISK_READ = "read"
RISK_CHANGE = "change"
RISK_DANGER = "danger"
RISKS = (RISK_READ, RISK_CHANGE, RISK_DANGER)


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
    label: str = ""                       # shown as the job's "command" / activity chip
    parameters: dict = field(default_factory=lambda: {"type": "object", "properties": {}})
    risk: str = RISK_READ
    # Human text for the confirm card, built from the *validated* arguments.
    confirm_summary: Optional[Callable[[dict], str]] = None
    # True when the tool returns content from outside our control (file text, web pages).
    untrusted_output: bool = False

    def describe_call(self, args: dict) -> str:
        if self.confirm_summary:
            try:
                return self.confirm_summary(args)
            except Exception:
                pass
        shown = ", ".join(f"{k}={str(v)[:80]!r}" for k, v in args.items())
        return f"{self.label or self.name}({shown})"


_TOOLS: Dict[str, Tool] = {}


def register(name: str, description: str = "", label: str = "", parameters: Optional[dict] = None,
             risk: str = RISK_READ, confirm_summary: Optional[Callable[[dict], str]] = None,
             untrusted_output: bool = False):
    if risk not in RISKS:
        raise ValueError(f"unknown risk {risk!r}")

    def deco(fn):
        _TOOLS[name] = Tool(
            name=name, fn=fn, description=description, label=label or name,
            parameters=parameters or {"type": "object", "properties": {}},
            risk=risk, confirm_summary=confirm_summary, untrusted_output=untrusted_output,
        )
        return fn
    return deco


def unregister(name: str) -> None:
    _TOOLS.pop(name, None)


def get_tool(name: str) -> Optional[Tool]:
    _load_builtin()
    return _TOOLS.get(name)


def all_tools() -> list:
    _load_builtin()
    return list(_TOOLS.values())


def list_tools() -> list:
    return [{"name": t.name, "description": t.description, "risk": t.risk} for t in all_tools()]


def _load_builtin():
    # imported lazily so registration happens once and import cycles can't occur
    from remote_tools import builtin  # noqa: F401


# ── Argument validation ──────────────────────────────────────

_TYPES = {
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
}


def validate_args(schema: dict, args) -> tuple:
    """
    Validate `args` against a flat JSON-schema object. Returns (clean_args, error).
    Unknown arguments are rejected (the model must not smuggle extras into a tool).
    Supports: type, required, enum, minLength/maxLength, minimum/maximum.
    """
    if args is None:
        args = {}
    if not isinstance(args, dict):
        return None, "arguments must be an object"
    props = schema.get("properties", {})
    required = schema.get("required", [])

    unknown = [k for k in args if k not in props]
    if unknown:
        return None, f"unknown argument(s): {', '.join(sorted(map(str, unknown)))}"
    missing = [k for k in required if k not in args or args[k] in (None, "")]
    if missing:
        return None, f"missing required argument(s): {', '.join(missing)}"

    clean = {}
    for key, value in args.items():
        spec = props[key]
        want = _TYPES.get(spec.get("type", "string"))
        if want is None:
            return None, f"argument '{key}' has unsupported schema type"
        # bool is an int subclass in Python; don't let True pass as an integer/number
        if isinstance(value, bool) and spec.get("type") != "boolean":
            return None, f"argument '{key}' must be {spec.get('type')}"
        if not isinstance(value, want):
            return None, f"argument '{key}' must be {spec.get('type')}"
        if "enum" in spec and value not in spec["enum"]:
            return None, f"argument '{key}' must be one of {spec['enum']}"
        if isinstance(value, str):
            if "\x00" in value:
                return None, f"argument '{key}' contains invalid characters"
            if len(value) > spec.get("maxLength", 4000):
                return None, f"argument '{key}' is too long"
            if len(value) < spec.get("minLength", 0):
                return None, f"argument '{key}' is too short"
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if "minimum" in spec and value < spec["minimum"]:
                return None, f"argument '{key}' must be >= {spec['minimum']}"
            if "maximum" in spec and value > spec["maximum"]:
                return None, f"argument '{key}' must be <= {spec['maximum']}"
        clean[key] = value
    return clean, None
