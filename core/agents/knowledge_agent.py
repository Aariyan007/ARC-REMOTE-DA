"""
KnowledgeAgent — Interacts with the Obsidian Second Brain.

This agent acts as Jarvis's long-term memory. It reads and writes Markdown files
into the Obsidian vault located at ~/Desktop/Jarvis_Second_Brain.
Capabilities:
- save_note: Create a new note in the vault
- append_note: Append text to an existing note
- read_note: Read the contents of a note
- search_vault: Search across all notes for a specific topic
"""

import os
import datetime
from core.agents.base_agent import BaseAgent, AgentResult

class KnowledgeAgent(BaseAgent):
    
    def __init__(self, vault_path: str = "~/Desktop/Jarvis_Second_Brain"):
        super().__init__()
        self.vault_path = os.path.expanduser(vault_path)
        
        # Ensure base structure exists
        os.makedirs(self.vault_path, exist_ok=True)
        for folder in ["1_Projects", "2_Areas", "3_Resources", "4_Archives", "Daily_Notes", "Workflows"]:
            os.makedirs(os.path.join(self.vault_path, folder), exist_ok=True)
            
        self.register_action(
            name="save_note",
            method=self._save_note,
            parameters={
                "title": "REQUIRED string — The title of the note (to be used as the filename)",
                "content": "REQUIRED string — The markdown content to save inside the note",
                "folder": "OPTIONAL string — The subfolder ('1_Projects', '2_Areas', '3_Resources', 'Daily_Notes', 'Workflows'). Defaults to '3_Resources'"
            },
            help_text="Creates a new knowledge note or long-term memory entry in the Second Brain."
        )
        
        self.register_action(
            name="append_note",
            method=self._append_note,
            parameters={
                "title": "REQUIRED string — The name of the existing note to append to",
                "content": "REQUIRED string — The text to add at the bottom of the note"
            },
            help_text="Adds new information to an existing note in the Second Brain."
        )
        
        self.register_action(
            name="read_note",
            method=self._read_note,
            parameters={
                "title": "REQUIRED string — The exact title or filename of the note"
            },
            help_text="Reads all the text from a specific note in the Second Brain."
        )
        
        self.register_action(
            name="search_vault",
            method=self._search_vault,
            parameters={
                "query": "REQUIRED string — The search term or topic to look for"
            },
            help_text="Searches all notes in the Second Brain for the query and returns matching filenames and snippets."
        )

    @property
    def name(self) -> str:
        return "knowledge"

    @property
    def description(self) -> str:
        return (
            "Interacts with the local Obsidian Second Brain. "
            "Use this agent to permanently save user preferences, project workflows, or long-term memories. "
            "It can create new notes, append to daily logs, and retrieve past knowledge by searching the vault."
        )

    def _find_file(self, title: str) -> str:
        """Helper to find the full path of a file by title in the vault."""
        filename = title if title.endswith(".md") else f"{title}.md"
        for root, dirs, files in os.walk(self.vault_path):
            if filename in files:
                return os.path.join(root, filename)
        return ""

    def _save_note(self, params: dict) -> AgentResult:
        title = params.get("title", params.get("name", ""))
        content = params.get("content", "")
        folder = params.get("folder", "3_Resources")

        if not title or not content:
            return AgentResult(success=False, action="save_note", error="Title and content are required.")

        # Ensure safe filename
        safe_title = title.replace("/", "_")
        if not safe_title.endswith(".md"):
            safe_title += ".md"

        target_dir = os.path.join(self.vault_path, folder)
        if not os.path.exists(target_dir):
            target_dir = os.path.join(self.vault_path, "3_Resources")

        file_path = os.path.join(target_dir, safe_title)
        
        # Add basic obsidian frontmatter/headers if it's completely new
        formatted_content = f"# {title}\n\n{content}\n"

        try:
            with open(file_path, "w") as f:
                f.write(formatted_content)
            return AgentResult(
                success=True, 
                action="save_note",
                result=f"Saved note '{title}' to {os.path.basename(target_dir)}.",
                data={"path": file_path}
            )
        except Exception as e:
            return AgentResult(success=False, action="save_note", error=str(e))

    def _append_note(self, params: dict) -> AgentResult:
        title = params.get("title", params.get("name", ""))
        content = params.get("content", "")

        if not title or not content:
            return AgentResult(success=False, action="append_note", error="Title and content are required.")

        file_path = self._find_file(title)
        if not file_path:
            # If it doesn't exist, create it in Daily Notes if not specified, else Resources
            return self._save_note(params)

        try:
            with open(file_path, "a") as f:
                f.write(f"\n{content}\n")
            return AgentResult(
                success=True,
                action="append_note",
                result=f"Added info to '{title}'.",
                data={"path": file_path}
            )
        except Exception as e:
            return AgentResult(success=False, action="append_note", error=str(e))

    def _read_note(self, params: dict) -> AgentResult:
        title = params.get("title", params.get("name", ""))
        if not title:
            return AgentResult(success=False, action="read_note", error="Note title is required.")

        file_path = self._find_file(title)
        if not file_path:
            return AgentResult(success=False, action="read_note", error=f"Could not find note '{title}' in the vault.")

        try:
            with open(file_path, "r") as f:
                content = f.read()
            return AgentResult(
                success=True,
                action="read_note",
                result=f"Read {len(content)} characters from '{title}'.",
                data={"content": content, "path": file_path}
            )
        except Exception as e:
            return AgentResult(success=False, action="read_note", error=str(e))

    def _search_vault(self, params: dict) -> AgentResult:
        query = params.get("query", "")
        if not query:
            return AgentResult(success=False, action="search_vault", error="Search query is required.")

        results = []
        try:
            for root, dirs, files in os.walk(self.vault_path):
                # Optionally skip hidden folders like .obsidian
                if ".obsidian" in root:
                    continue
                for file in files:
                    if file.endswith(".md"):
                        path = os.path.join(root, file)
                        with open(path, "r", errors="ignore") as f:
                            content = f.read()
                            if query.lower() in content.lower():
                                snippet_idx = content.lower().find(query.lower())
                                start = max(0, snippet_idx - 30)
                                end = min(len(content), snippet_idx + len(query) + 30)
                                snippet = content[start:end].replace('\n', ' ')
                                results.append({
                                    "title": file.replace(".md", ""),
                                    "folder": os.path.basename(root),
                                    "snippet": f"...{snippet}..."
                                })

            if not results:
                return AgentResult(
                    success=True, 
                    action="search_vault", 
                    result=f"No notes found mentioning '{query}'.",
                    data={"matches": []}
                )

            return AgentResult(
                success=True,
                action="search_vault",
                result=f"Found {len(results)} note(s) mentioning '{query}'.",
                data={"matches": results}
            )
        except Exception as e:
            return AgentResult(success=False, action="search_vault", error=str(e))

if __name__ == "__main__":
    agent = KnowledgeAgent()
    print("Testing KnowledgeAgent...")
    res = agent.execute("save_note", {"title": "Jarvis Architecture", "content": "Jarvis uses Gemini for planning.", "folder": "1_Projects"})
    print(res)
    res = agent.execute("search_vault", {"query": "Gemini"})
    print(res)
