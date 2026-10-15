"""Built-in tools. Importing this module registers them."""

from core.action_result import ActionResult
from remote_tools import files
from remote_tools.registry import register, ToolContext, RISK_READ
from remote_tools.tools import fs, system  # noqa: F401  (register on import)


@register(
    "search_files",
    description="Find files by name in the allowed folders. If nothing matches exactly it suggests similar names "
                "(typos, partial names, different word order). Use this before reading or sending a file.",
    label="Search files",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "File name or part of it, e.g. 'resume' or 'budget.xlsx'.", "maxLength": 200},
            "limit": {"type": "integer", "description": "Max results (default 5).", "minimum": 1, "maximum": 20},
        },
        "required": ["query"],
    },
    risk=RISK_READ,
)
def search_files(args: dict, ctx: ToolContext) -> ActionResult:
    query = str(args.get("query", "")).strip()
    if not query:
        return ActionResult.fail("search_files", "Missing 'query'", user_message="What file are you looking for?")
    if len(query) > 200:
        return ActionResult.fail("search_files", "Query too long")

    ctx.progress(f"Searching for '{query}'...")
    result = files.attach_download_urls(files.find_files(query, limit=int(args.get("limit", 5) or 5)),
                                        ctx.device_id)
    matches = result["matches"]
    if not matches:
        return ActionResult.fail(
            "search_files", f"No file found like '{query}'", data=result,
            user_message=f"I couldn't find anything like '{query}'.",
        )
    if result["exact"]:
        summary = f"Found {matches[0]['name']}" + (f" (+{len(matches) - 1} more)" if len(matches) > 1 else "")
    else:
        summary = f"No file named '{query}'. Did you mean: " + ", ".join(m["name"] for m in matches[:3]) + "?"
    return ActionResult.ok("search_files", summary, data=result)
