from rapidfuzz import process, fuzz

# ─── Command Registry ────────────────────────────────────────
COMMAND_REGISTRY = {
    # App commands
    "open vscode":        "open_vscode",
    "open vs code":       "open_vscode",
    "open safari":        "open_safari",
    "open browser":       "open_safari",
    "open terminal":      "open_terminal",

    # Search commands
    "search":             "search_google",
    "google":             "search_google",
    "look up":            "search_google",
    "find":               "search_google",

    # Time commands
    "what time is it":    "tell_time",
    "what's the time":    "tell_time",
    "what is the time":   "tell_time",
    "current time":       "tell_time",
    "time please":        "tell_time",

    # Date commands
    "what is the date":   "tell_date",
    "what's the date":    "tell_date",
    "today's date":       "tell_date",

    # System commands
    "lock screen":        "lock_screen",
    "lock my screen":     "lock_screen",
    "lock the screen":    "lock_screen",
    "shutdown":           "shutdown_pc",
    "shut down":          "shutdown_pc",
    "restart":            "restart_pc",
}

MATCH_THRESHOLD = 70
# ─────────────────────────────────────────────────────────────


def extract_search_query(command: str) -> str:
    """Pulls the actual search term out of the command."""
    for trigger in ["search", "google", "look up", "find"]:
        if trigger in command:
            return command.split(trigger, 1)[-1].strip()
    return command


def route(command: str, actions: dict) -> None:
    """
    Takes a text command, finds the best matching action, executes it.
    Order:
        1. Search trigger check
        2. Explicit app keyword check
        3. Fuzzy match
        4. Unknown → Gemini fallback later
    """
    if not command:
        print("⚠️  Empty command received")
        return

    command = command.strip().lower()
    print(f"\n🔍 Routing: '{command}'")

    # ── Step 1: Search commands ──────────────────────────────
    for trigger in ["search", "google", "look up", "find"]:
        if trigger in command:
            query = extract_search_query(command)
            if query:
                print(f"🌐 Search intent detected → query: '{query}'")
                if "search_google" in actions:
                    actions["search_google"](query)
                else:
                    print("❌ search_google not connected yet")
                return

    # ── Step 2: Explicit app keyword check ──────────────────
    if "safari" in command or "browser" in command:
        print("✅ App intent detected → open_safari")
        if "open_safari" in actions:
            actions["open_safari"]()
        return

    if "vscode" in command or "vs code" in command or "code editor" in command:
        print("✅ App intent detected → open_vscode")
        if "open_vscode" in actions:
            actions["open_vscode"]()
        return

    if "terminal" in command:
        print("✅ App intent detected → open_terminal")
        if "open_terminal" in actions:
            actions["open_terminal"]()
        return

    # ── Step 3: Fuzzy match ──────────────────────────────────
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

    if score < MATCH_THRESHOLD:
        print(f"⚠️  Confidence too low ({score}% < {MATCH_THRESHOLD}%) — treating as unknown")
        _unknown_command(command)
        return

    # ── Step 4: Execute ──────────────────────────────────────
    if action_name in actions:
        actions[action_name]()
    else:
        print(f"❌ Action '{action_name}' not connected yet")


def _unknown_command(command: str) -> None:
    """Called when no command matches. Gemini fallback will go here later."""
    print(f"❓ Unknown command: '{command}'")
    print("   → [Gemini fallback will handle this in Phase 2]")


# ─── Quick test ──────────────────────────────────────────────
if __name__ == "__main__":

    def fake_open_vscode():    print("🖥️  [ACTION] Opening VS Code")
    def fake_open_safari():    print("🌐  [ACTION] Opening Safari")
    def fake_open_terminal():  print("💻  [ACTION] Opening Terminal")
    def fake_tell_time():      print("🕐  [ACTION] Telling time")
    def fake_tell_date():      print("📅  [ACTION] Telling date")
    def fake_lock_screen():    print("🔒  [ACTION] Locking screen")
    def fake_search(query):    print(f"🔍  [ACTION] Searching for: '{query}'")

    test_actions = {
        "open_vscode":    fake_open_vscode,
        "open_safari":    fake_open_safari,
        "open_terminal":  fake_open_terminal,
        "tell_time":      fake_tell_time,
        "tell_date":      fake_tell_date,
        "lock_screen":    fake_lock_screen,
        "search_google":  fake_search,
    }

    test_commands = [
        "open vscode",
        "open safari",
        "open crome",
        "open the browser please",
        "search python tutorial",
        "jarvis search for machine learning",
        "what time is it",
        "what is the time",
        "hey lock my screen",
        "i want to open the browser",
        "blah blah random words",
    ]

    print("=" * 50)
    print("  INTENT ROUTER TEST")
    print("=" * 50)

    for cmd in test_commands:
        route(cmd, test_actions)
        print("-" * 40)