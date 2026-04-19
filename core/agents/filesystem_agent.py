"""
FileSystemAgent — handles all file and folder operations.

Capabilities:
- search_file, open_file, read_file, create_file, edit_file
- delete_file, rename_file, copy_file, recent_files
- open_folder, create_folder

This agent ONLY has access to filesystem tools.
It cannot send emails, control volume, or browse the web.
"""

import os
import subprocess
from core.agents.base_agent import BaseAgent, AgentResult
from core.memory import update_file_context, update_context


class FileSystemAgent(BaseAgent):

    @property
    def name(self) -> str:
        return "filesystem"

    @property
    def description(self) -> str:
        return (
            "Handles all file and folder operations: searching, reading, "
            "creating, editing, deleting, renaming, and copying files. "
            "Also handles opening and creating folders."
        )

    def __init__(self, actions_map: dict = None):
        """
        Args:
            actions_map: The global ACTIONS dict from main.py so this agent
                         can call the existing control functions.
        """
        super().__init__()
        self._actions = actions_map or {}

        # Register all file capabilities with parameter schemas
        self.register_action("search_file", self._search_file,
            parameters={"name": "REQUIRED string — filename or partial name to search for"},
            help_text="Search for files on this computer by name.")
        self.register_action("open_file", self._open_file,
            parameters={"path": "REQUIRED string — full absolute file path"},
            help_text="Open a file in its default application.")
        self.register_action("read_file", self._read_file,
            parameters={"name": "REQUIRED string — filename with extension (e.g. 'notes.txt')", "location": "optional string — folder name"},
            help_text="Read text content from a file.")
        self.register_action("create_file", self._create_file,
            parameters={"name": "REQUIRED string — filename WITH extension (e.g. 'superman.txt', 'report.md')", "location": "optional string — folder, defaults to desktop"},
            help_text="Create a new empty file. MUST include the file extension in the name.")
        self.register_action("edit_file", self._edit_file,
            parameters={"name": "REQUIRED string — filename with extension", "content": "REQUIRED string — text to write into the file"},
            help_text="Write or append text content to an existing file.")
        self.register_action("delete_file", self._delete_file,
            parameters={"name": "REQUIRED string — filename with extension"},
            help_text="Move a file to the trash.")
        self.register_action("rename_file", self._rename_file,
            parameters={"name": "REQUIRED string — current filename", "new_name": "REQUIRED string — new filename"},
            help_text="Rename a file.")
        self.register_action("copy_file", self._copy_file,
            parameters={"name": "REQUIRED string — filename to copy", "location": "REQUIRED string — destination folder"},
            help_text="Copy a file to another location.")
        self.register_action("recent_files", self._recent_files,
            help_text="List recently modified files from the last 24 hours.")
        self.register_action("open_folder", self._open_folder,
            parameters={"name": "REQUIRED string — folder name (e.g. 'Downloads', 'Desktop')"},
            help_text="Open a folder in Finder.")
        self.register_action("create_folder", self._create_folder,
            parameters={"name": "REQUIRED string — new folder name", "location": "optional string — parent folder"},
            help_text="Create a new folder.")

    # ── File: Search ─────────────────────────────────────────
    def _search_file(self, params: dict) -> AgentResult:
        """Searches for files using macOS Spotlight (mdfind)."""
        name = params.get("name", params.get("query", ""))
        if not name:
            return AgentResult(
                success=False, action="search_file",
                error="No file name or query provided",
            )

        try:
            result = subprocess.run(
                ["mdfind", "-name", name],
                capture_output=True, text=True, timeout=10,
            )
            files = [
                f for f in result.stdout.strip().split("\n")
                if f and not any(skip in f for skip in [
                    "venv", ".git", "Library/Caches", ".pyc",
                    "node_modules", "/System/", "/private/", "/usr/",
                    "PrivateFrameworks", ".framework", ".app/Contents",
                ])
            ]

            if files:
                display = "\n".join([
                    f"{i+1}. {os.path.basename(f)} → {f}"
                    for i, f in enumerate(files[:8])
                ])
                return AgentResult(
                    success=True, action="search_file",
                    result=f"Found {len(files)} files:\n{display}",
                    data={"files": files[:8], "count": len(files)},
                )
            return AgentResult(
                success=True, action="search_file",
                result=f"No files found matching '{name}'",
                data={"files": [], "count": 0},
            )
        except Exception as e:
            return AgentResult(
                success=False, action="search_file", error=str(e),
            )

    # ── File: Open ───────────────────────────────────────────
    def _open_file(self, params: dict) -> AgentResult:
        """Opens a file in its default application."""
        path = params.get("path", "")
        if not path:
            return AgentResult(
                success=False, action="open_file",
                error="No file path provided",
            )

        if os.path.exists(path):
            subprocess.Popen(["open", path])
            return AgentResult(
                success=True, action="open_file",
                result=f"Opened {os.path.basename(path)}",
                data={"path": path},
            )
        return AgentResult(
            success=False, action="open_file",
            error=f"File not found: {path}",
        )

    # ── File: Read ───────────────────────────────────────────
    def _read_file(self, params: dict) -> AgentResult:
        """Reads file contents (text files). Returns first 2000 chars."""
        path = params.get("path", "")
        name = params.get("name", params.get("filename", ""))

        # Direct path read
        if path and os.path.exists(path):
            try:
                with open(path, "r", errors="ignore") as f:
                    content = f.read()[:2000]
                return AgentResult(
                    success=True, action="read_file",
                    result=f"File contents:\n{content}",
                    data={"content": content, "path": path},
                )
            except Exception as e:
                return AgentResult(
                    success=False, action="read_file", error=str(e),
                )

        # Fallback: use the existing read_file from ACTIONS
        if name and "read_file" in self._actions:
            location = params.get("location")
            self._actions["read_file"](name, location)
            return AgentResult(
                success=True, action="read_file",
                result=f"Read {name} aloud",
                data={"filename": name},
            )

        return AgentResult(
            success=False, action="read_file",
            error=f"File not found: {path or name}",
        )

    # ── File: Create ─────────────────────────────────────────
    def _create_file(self, params: dict) -> AgentResult:
        """Creates a new file at the specified location."""
        name = params.get("name", params.get("filename", ""))
        location = params.get("location", "desktop")

        if not name:
            return AgentResult(
                success=False, action="create_file",
                error="No filename provided",
            )

        if "create_file" in self._actions:
            self._actions["create_file"](name, location)
            # ✅ Update file context so follow-up commands can reference "that file"
            update_file_context(name, action="create_file")
            update_context(action="create_file", target=name, result=f"Created {name}")
            return AgentResult(
                success=True, action="create_file",
                result=f"Created {name} on {location}",
                data={"filename": name, "location": location},
            )
        return AgentResult(
            success=False, action="create_file",
            error="create_file action not available",
        )

    # ── File: Edit ───────────────────────────────────────────
    def _edit_file(self, params: dict) -> AgentResult:
        """Appends content to an existing file."""
        name = params.get("name", params.get("filename", ""))
        content = params.get("content", "")
        location = params.get("location")

        if not name:
            return AgentResult(
                success=False, action="edit_file",
                error="No filename provided",
            )
        if not content:
            return AgentResult(
                success=False, action="edit_file",
                error="No content provided — ask the user what to write",
            )

        if "edit_file" in self._actions:
            self._actions["edit_file"](name, content, location)
            update_file_context(name, action="edit_file")
            update_context(action="edit_file", target=name, result=f"Edited {name}")
            return AgentResult(
                success=True, action="edit_file",
                result=f"Appended text to {name}",
                data={"filename": name, "content_preview": content[:100]},
            )
        return AgentResult(
            success=False, action="edit_file",
            error="edit_file action not available",
        )

    # ── File: Delete ─────────────────────────────────────────
    def _delete_file(self, params: dict) -> AgentResult:
        """Moves a file to trash."""
        name = params.get("name", params.get("filename", ""))
        location = params.get("location")

        if not name:
            return AgentResult(
                success=False, action="delete_file",
                error="No filename provided",
            )

        if "delete_file" in self._actions:
            self._actions["delete_file"](name, location)
            update_context(action="delete_file", target=name, result=f"Deleted {name}")
            return AgentResult(
                success=True, action="delete_file",
                result=f"Moved {name} to trash",
                data={"filename": name},
            )
        return AgentResult(
            success=False, action="delete_file",
            error="delete_file action not available",
        )

    # ── File: Rename ─────────────────────────────────────────
    def _rename_file(self, params: dict) -> AgentResult:
        """Renames a file."""
        old = params.get("name", params.get("filename", params.get("old_name", "")))
        new = params.get("new_name", "")
        location = params.get("location")

        if not old or not new:
            return AgentResult(
                success=False, action="rename_file",
                error="Need both old and new file names",
            )

        if "rename_file" in self._actions:
            rename_result = self._actions["rename_file"](old, new, location)
            if rename_result is False:
                return AgentResult(
                    success=False, action="rename_file",
                    error=f"Couldn't rename {old} to {new}",
                )
            if isinstance(rename_result, dict) and not rename_result.get("success"):
                return AgentResult(
                    success=False, action="rename_file",
                    error=rename_result.get("error", f"Couldn't rename {old} to {new}"),
                )

            final_name = rename_result.get("new_name", new) if isinstance(rename_result, dict) else new
            final_path = rename_result.get("path") if isinstance(rename_result, dict) else None
            # Track the new name as the current active file
            update_file_context(final_name, path=final_path, action="rename_file")
            update_context(action="rename_file", target=final_name, result=f"Renamed {old} to {final_name}")
            return AgentResult(
                success=True, action="rename_file",
                result=f"Renamed {old} to {final_name}",
                data={"old_name": old, "new_name": final_name, "path": final_path},
            )
        return AgentResult(
            success=False, action="rename_file",
            error="rename_file action not available",
        )

    # ── File: Copy ───────────────────────────────────────────
    def _copy_file(self, params: dict) -> AgentResult:
        """Copies a file to a destination."""
        name = params.get("name", params.get("filename", ""))
        dest = params.get("location", params.get("destination", "desktop"))

        if not name:
            return AgentResult(
                success=False, action="copy_file",
                error="No filename provided",
            )

        if "copy_file" in self._actions:
            self._actions["copy_file"](name, dest)
            return AgentResult(
                success=True, action="copy_file",
                result=f"Copied {name} to {dest}",
                data={"filename": name, "destination": dest},
            )
        return AgentResult(
            success=False, action="copy_file",
            error="copy_file action not available",
        )

    # ── File: Recent ─────────────────────────────────────────
    def _recent_files(self, params: dict) -> AgentResult:
        """Shows recently modified files."""
        if "get_recent_files" in self._actions:
            self._actions["get_recent_files"]()
            return AgentResult(
                success=True, action="recent_files",
                result="Showed recent files",
            )

        # Fallback: inline Spotlight search
        try:
            result = subprocess.run(
                ["mdfind", "-onlyin", os.path.expanduser("~"),
                 "kMDItemContentModificationDate >= $time.today(-1)"],
                capture_output=True, text=True, timeout=10,
            )
            files = [
                f for f in result.stdout.strip().split("\n")
                if f and not any(s in f for s in ["venv", ".git", "Library", "cache"])
            ][:10]
            names = [os.path.basename(f) for f in files]
            return AgentResult(
                success=True, action="recent_files",
                result=f"Recent files: {', '.join(names)}",
                data={"files": files},
            )
        except Exception as e:
            return AgentResult(
                success=False, action="recent_files", error=str(e),
            )

    # ── Folder: Open ─────────────────────────────────────────
    def _open_folder(self, params: dict) -> AgentResult:
        """Opens a folder in Finder."""
        target = params.get("target", params.get("name", params.get("folder_name", "")))

        if not target:
            return AgentResult(
                success=False, action="open_folder",
                error="No folder name provided",
            )

        if "open_folder" in self._actions:
            self._actions["open_folder"](target)
            return AgentResult(
                success=True, action="open_folder",
                result=f"Opened {target}",
                data={"folder": target},
            )
        return AgentResult(
            success=False, action="open_folder",
            error="open_folder action not available",
        )

    # ── Folder: Create ───────────────────────────────────────
    def _create_folder(self, params: dict) -> AgentResult:
        """Creates a new folder."""
        target = params.get("target", params.get("name", params.get("folder_name", "")))
        location = params.get("location", "desktop")

        if not target:
            return AgentResult(
                success=False, action="create_folder",
                error="No folder name provided",
            )

        if "create_folder" in self._actions:
            self._actions["create_folder"](target, location=location)
            return AgentResult(
                success=True, action="create_folder",
                result=f"Created folder {target}",
                data={"folder": target},
            )
        return AgentResult(
            success=False, action="create_folder",
            error="create_folder action not available",
        )
