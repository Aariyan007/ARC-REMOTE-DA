from rapidfuzz import process, fuzz

# ─── Command Registry ────────────────────────────────────────
# This is the single place where all commands live.
# To add a new command later — just add it here. Nothing else changes.
COMMAND_REGISTRY = {
    # App commands
    "open vscode":        "open_vscode",
    "open vs code":       "open_vscode",
    "open chrome":        "open_chrome",
    "open browser":       "open_chrome",
    "open terminal":      "open_terminal",

    # Search commands
    "search":             "search_google",
    "google":             "search_google",
    "look up":            "search_google",
    "find":               "search_google",

    # Time commands
    "what time is it":    "tell_time",
    "what's the time":    "tell_time",
    "current time":       "tell_time",
    "time please":        "tell_time",

    # System commands
    "lock screen":        "lock_screen",
    "lock my screen":     "lock_screen",
    "shutdown":           "shutdown_pc",
    "shut down":          "shutdown_pc",
    "restart":            "restart_pc",
}

# How confident the match needs to be (0-100)
# 70 = fairly loose, handles typos and Whisper mishears well
MATCH_THRESHOLD = 70
# ─────────────────────────────────────────────────────────────


def extract_search_query(command: str) -> str:
    """
    Pulls the actual search term out of the command.
    Example: "search python loops" → "python loops"
    """
    for trigger in ["search", "google", "look up", "find"]:
        if trigger in command:
            return command.split(trigger, 1)[-1].strip()
    return command


def route(command: str, actions: dict) -> None:
    """
    Takes a text command, finds the best matching action, executes it.

    Args:
        command: What the user said. Example: "open vscode"
        actions: Dict of action_name → function. Passed in from main.py
    """
    if not command:
        print("⚠️  Empty command received")
        return

    command = command.strip().lower()
    print(f"\n🔍 Routing: '{command}'")

    # ── Step 1: Check for search command first (special case)
    # Because "search python loops" won't match "search" exactly
    for trigger in ["search", "google", "look up", "find"]:
        if command.startswith(trigger):
            query = extract_search_query(command)
            if query:
                print(f"🌐 Search intent detected → query: '{query}'")
                if "search_google" in actions:
                    actions["search_google"](query)
                else:
                    print("❌ search_google function not connected yet")
                return

    # ── Step 2: Fuzzy match against all known commands
    result = process.extractOne(
        command,
        COMMAND_REGISTRY.keys(),
        scorer=fuzz.WRatio
    )

    if result is None:
        _unknown_command(command)
        return

    matched_phrase, score, _ = result
    action_name = COMMAND_REGISTRY[matched_phrase]

    print(f"✅ Matched: '{matched_phrase}' (confidence: {score}%) → {action_name}")

    # ── Step 3: Check confidence is high enough
    if score < MATCH_THRESHOLD:
        print(f"⚠️  Confidence too low ({score}% < {MATCH_THRESHOLD}%) — treating as unknown")
        _unknown_command(command)
        return

    # ── Step 4: Execute the action
    if action_name in actions:
        actions[action_name]()
    else:
        print(f"❌ Action '{action_name}' not connected yet")


def _unknown_command(command: str) -> None:
    """Called when no command matches. Gemini fallback will go here later."""
    print(f"❓ Unknown command: '{command}'")
    print("   → [Gemini fallback will handle this in Phase 2]")


# ─── Quick test ──────────────────────────────────────────────
# Run: python3 core/intent_router.py
if __name__ == "__main__":

    # Fake actions for testing — real ones come from control/ folder later
    def fake_open_vscode():    print("🖥️  [ACTION] Opening VS Code")
    def fake_open_chrome():    print("🌐  [ACTION] Opening Chrome")
    def fake_open_terminal():  print("💻  [ACTION] Opening Terminal")
    def fake_tell_time():      print("🕐  [ACTION] Telling time")
    def fake_lock_screen():    print("🔒  [ACTION] Locking screen")
    def fake_search(query):    print(f"🔍  [ACTION] Searching for: '{query}'")

    test_actions = {
        "open_vscode":    fake_open_vscode,
        "open_chrome":    fake_open_chrome,
        "open_terminal":  fake_open_terminal,
        "tell_time":      fake_tell_time,
        "lock_screen":    fake_lock_screen,
        "search_google":  fake_search,
    }

    # Test commands — including messy ones Whisper might produce
    test_commands = [
        "open vscode",
        "open vs code",
        "open crome",              # typo — should still match chrome
        "search python tutorial",
        "what time is it",
        "hey lock my screen",
        "i want to open the browser",
        "blah blah random words",  # should be unknown
    ]

    print("=" * 50)
    print("  INTENT ROUTER TEST")
    print("=" * 50)

    for cmd in test_commands:
        route(cmd, test_actions)
        print("-" * 40)