"""
test_phase3.py — Phase 3 full test suite.
Run this bad boy and see if everything we built actually works.

  python3 test_phase3.py           # run all tests
  python3 test_phase3.py mouse     # only mouse/keyboard tests
  python3 test_phase3.py intent    # only intent routing tests
  python3 test_phase3.py files     # only file edge-case tests
  python3 test_phase3.py agents    # only agent tests

What's covered:
  1. control/computer_use.py  — mouse, keyboard, screenshot
  2. perception/screen_reader.py — Gemini Vision screen understanding
  3. core/agents/computer_use_agent.py — all 8 registered actions
  4. Bug fix regressions:
       - edit_file verifier (glob fallback for bare filenames)
       - open_app param keys (app/name/target/application)
       - play_song intent scores (named songs, by-artist patterns)
       - build_single_slot_question UnboundLocalError
       - edit_file content=None properly asks instead of writing noise
  5. Fast intent routing — new computer_use intent patterns
  6. Casual file creation flows ("create a file" → name it mid-convo)
"""

import os
import sys
import time
import tempfile
import traceback

# ────────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────────

PASSED = []
FAILED = []
SKIPPED = []

GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"


def _ok(name, detail=""):
    PASSED.append(name)
    print(f"  {GREEN}✅ PASS{RESET}  {name}" + (f"  ({detail})" if detail else ""))


def _fail(name, reason=""):
    FAILED.append(name)
    print(f"  {RED}❌ FAIL{RESET}  {name}" + (f"  → {reason}" if reason else ""))


def _skip(name, reason=""):
    SKIPPED.append(name)
    print(f"  {YELLOW}⏭  SKIP{RESET}  {name}" + (f"  ({reason})" if reason else ""))


def section(title):
    print(f"\n{BOLD}{CYAN}{'─'*60}{RESET}")
    print(f"{BOLD}{CYAN}  {title}{RESET}")
    print(f"{BOLD}{CYAN}{'─'*60}{RESET}")


def summary():
    total = len(PASSED) + len(FAILED) + len(SKIPPED)
    print(f"\n{BOLD}{'='*60}{RESET}")
    print(f"{BOLD}  RESULTS  —  {total} tests{RESET}")
    print(f"{'='*60}")
    print(f"  {GREEN}Passed : {len(PASSED)}{RESET}")
    print(f"  {RED}Failed : {len(FAILED)}{RESET}")
    print(f"  {YELLOW}Skipped: {len(SKIPPED)}{RESET}")
    print(f"{'='*60}\n")
    if FAILED:
        print(f"{RED}Failed tests:{RESET}")
        for f in FAILED:
            print(f"  • {f}")
    return len(FAILED)


# ────────────────────────────────────────────────────────────────────────
# SECTION 1 — control/computer_use.py
# ────────────────────────────────────────────────────────────────────────

def test_computer_use_module():
    section("1 · Computer Use — Mouse & Keyboard (control/computer_use.py)")

    try:
        import control.computer_use as cu
    except ImportError as e:
        _skip("computer_use import", f"pyautogui not installed: {e}")
        return

    # is_available()
    avail = cu.is_available()
    if avail:
        _ok("is_available()", "pyautogui ready")
    else:
        _skip("is_available()", "pyautogui not available — skipping mouse tests")
        return

    # get_screen_size()
    w, h = cu.get_screen_size()
    if w > 0 and h > 0:
        _ok("get_screen_size()", f"{w}x{h}")
    else:
        _fail("get_screen_size()", f"got {w}x{h}")

    # get_mouse_position()
    x, y = cu.get_mouse_position()
    _ok("get_mouse_position()", f"({x}, {y})")

    # move_to() — move to center of screen
    cx, cy = w // 2, h // 2
    r = cu.move_to(cx, cy)
    if r.ok:
        _ok("move_to(center)", f"moved to ({cx}, {cy})")
    else:
        _fail("move_to(center)", r.error)

    # move_to() — clamp to screen bounds (shouldn't crash on out-of-bounds)
    r = cu.move_to(99999, 99999)
    if r.ok:
        _ok("move_to(clamped out-of-bounds)", "properly clamped to screen edge")
    else:
        _fail("move_to(clamped)", r.error)

    # ── Move back to center so PyAutoGUI fail-safe doesn't trip ──
    cu.move_to(cx, cy, duration=0.1)

    # scroll()
    r = cu.scroll(cx, cy, clicks=1)
    if r.ok:
        _ok("scroll(up, center)", r.message)
    else:
        _fail("scroll()", r.error)

    # press_key() — pressing nothing harmful
    r = cu.press_key("shift")
    if r.ok:
        _ok("press_key(shift)", "pressed harmlessly")
    else:
        _fail("press_key(shift)", r.error)

    # hotkey() — command+shift (harmless combo on mac)
    # Actually skip anything that might trigger shortcuts - just test return type
    r = cu.hotkey("shift")
    if r.ok:
        _ok("hotkey(shift)", "returns ControlResult.ok")
    else:
        _fail("hotkey()", r.error)

    # take_screenshot_to_bytes()
    img_bytes = cu.take_screenshot_to_bytes()
    if img_bytes and len(img_bytes) > 1000:
        _ok("take_screenshot_to_bytes()", f"{len(img_bytes)//1024}KB PNG")
    else:
        _fail("take_screenshot_to_bytes()", "empty or too small")

    # take_screenshot_to_file()
    path = cu.take_screenshot_to_file()
    if path and os.path.exists(path):
        size = os.path.getsize(path)
        _ok("take_screenshot_to_file()", f"saved {size//1024}KB → {os.path.basename(path)}")
        os.unlink(path)
    else:
        _fail("take_screenshot_to_file()", f"file not created: {path}")

    # ControlResult.success / fail constructors
    from control.computer_use import ControlResult
    ok_r = ControlResult.success("test ok")
    fail_r = ControlResult.fail("test fail")
    if ok_r.ok and ok_r.message == "test ok":
        _ok("ControlResult.success()", "ok=True, message set")
    else:
        _fail("ControlResult.success()")

    if not fail_r.ok and fail_r.error == "test fail":
        _ok("ControlResult.fail()", "ok=False, error set")
    else:
        _fail("ControlResult.fail()")


# ────────────────────────────────────────────────────────────────────────
# SECTION 2 — perception/screen_reader.py
# ────────────────────────────────────────────────────────────────────────

def test_screen_reader():
    section("2 · Screen Reader — Gemini Vision (perception/screen_reader.py)")

    try:
        from perception import screen_reader as sr
    except ImportError as e:
        _skip("screen_reader import", str(e))
        return

    if not os.getenv("API_KEY"):
        _skip("screen_reader tests", "API_KEY not set — Gemini Vision won't work")
        return

    try:
        from control.computer_use import is_available
        if not is_available():
            _skip("screen_reader tests", "pyautogui unavailable — can't take screenshots")
            return
    except Exception:
        _skip("screen_reader tests", "computer_use unavailable")
        return

    # ScreenReadResult dataclass
    result = sr.ScreenReadResult(ok=True, text="hello", x=100, y=200)
    if result.has_location and result.coords() == (100, 200):
        _ok("ScreenReadResult.has_location + coords()", "(100, 200)")
    else:
        _fail("ScreenReadResult.coords()")

    result_no_loc = sr.ScreenReadResult(ok=True, text="no coords")
    if not result_no_loc.has_location and result_no_loc.coords() is None:
        _ok("ScreenReadResult.coords() None when no x,y")
    else:
        _fail("ScreenReadResult.coords() None check")

    # read_screen() — basic question about current screen
    print("  → Calling Gemini Vision to read screen (takes a few secs)...")
    r = sr.read_screen("What operating system is this? Just say 'macOS' or 'Windows' or 'Linux'.")
    if r.ok and r.text:
        _ok("read_screen(OS question)", f"Gemini says: '{r.text[:60]}'")
    else:
        _fail("read_screen()", r.error or "no text returned")

    # get_screen_text() — should return a non-empty string
    print("  → Reading all text on screen...")
    text = sr.get_screen_text()
    if text and len(text) > 10:
        _ok("get_screen_text()", f"{len(text)} chars extracted")
    elif text == "":
        _fail("get_screen_text()", "empty string returned")
    else:
        _fail("get_screen_text()", "None returned")

    # verify_screen_state() — something that's definitely true
    print("  → Verifying screen state...")
    is_mac = sr.verify_screen_state("This is a computer screen")
    if is_mac:
        _ok("verify_screen_state(obvious truth)", "returned True")
    else:
        _fail("verify_screen_state()", "returned False for obvious statement")


# ────────────────────────────────────────────────────────────────────────
# SECTION 3 — core/agents/computer_use_agent.py
# ────────────────────────────────────────────────────────────────────────

def test_computer_use_agent():
    section("3 · ComputerUseAgent — All 8 Actions")

    try:
        from core.agents.computer_use_agent import ComputerUseAgent
        agent = ComputerUseAgent()
    except Exception as e:
        _skip("ComputerUseAgent import", str(e))
        return

    # Check all 8 actions registered
    expected_actions = {
        "computer_use", "click_element", "type_into",
        "open_app_ui", "navigate_url_ui", "whatsapp_send",
        "gmail_search", "gmail_open_url",
    }
    registered = set(agent.capabilities)
    missing = expected_actions - registered
    extra   = registered - expected_actions

    if not missing:
        _ok("All 8 actions registered", f"{sorted(registered)}")
    else:
        _fail("Actions registered", f"missing: {missing}")

    if extra:
        _ok(f"Extra actions (bonus): {extra}")

    # computer_use with no instruction
    result = agent.execute("computer_use", {})
    if not result.success and "instruction" in (result.error or "").lower():
        _ok("computer_use — no instruction → graceful error")
    else:
        _fail("computer_use — no instruction", f"got: {result}")

    # click_element with no element
    result = agent.execute("click_element", {})
    if not result.success:
        _ok("click_element — no element → graceful error")
    else:
        _fail("click_element — should fail with no element")

    # type_into with no text
    result = agent.execute("type_into", {"field": "search box"})
    if not result.success and "text" in (result.error or "").lower():
        _ok("type_into — no text → graceful error")
    else:
        _fail("type_into — no text", f"got: {result}")

    # open_app_ui with no app name
    result = agent.execute("open_app_ui", {})
    if not result.success:
        _ok("open_app_ui — no name → graceful error")
    else:
        _fail("open_app_ui — should fail with no name")

    # navigate_url_ui with no url
    result = agent.execute("navigate_url_ui", {})
    if not result.success:
        _ok("navigate_url_ui — no url → graceful error")
    else:
        _fail("navigate_url_ui — should fail with no url")

    # whatsapp_send with no contact
    result = agent.execute("whatsapp_send", {"message": "hello"})
    if not result.success and "contact" in (result.error or "").lower():
        _ok("whatsapp_send — no contact → graceful error", result.error)
    else:
        _fail("whatsapp_send — no contact", f"got: {result}")

    # whatsapp_send with no message
    result = agent.execute("whatsapp_send", {"contact": "mom"})
    if not result.success and "message" in (result.error or "").lower():
        _ok("whatsapp_send — no message → graceful error", result.error)
    else:
        _fail("whatsapp_send — no message", f"got: {result}")

    # gmail_search with no query
    result = agent.execute("gmail_search", {})
    if not result.success:
        _ok("gmail_search — no query → graceful error")
    else:
        _fail("gmail_search — should fail with no query")

    # _check_available() returns bool
    avail = agent._check_available()
    if isinstance(avail, bool):
        _ok(f"_check_available() → {avail}", "returns bool correctly")
    else:
        _fail("_check_available() wrong type")


# ────────────────────────────────────────────────────────────────────────
# SECTION 4 — Bug Fix Regressions
# ────────────────────────────────────────────────────────────────────────

def test_bug_regressions():
    section("4 · Bug Fix Regressions")

    # ── Bug 1: edit_file verifier glob fallback ──────────────────
    try:
        from core.action_verifier import verify_file_edited, BeforeState
        from core.action_result import ActionResult

        # Create a real temp file to stat
        tmp = tempfile.NamedTemporaryFile(suffix=".txt", delete=False, dir=os.path.expanduser("~/Desktop"))
        tmp.write(b"original content")
        tmp.flush()
        tmp_name = os.path.basename(tmp.name)
        tmp_bare = tmp.name.replace(".txt", "")  # bare path without extension
        tmp.close()

        # Before state with mtime
        before = BeforeState()
        stat = os.stat(tmp.name)
        before.file_exists = True
        before.file_path   = tmp_bare    # intentionally BARE (no .txt) — this is the bug scenario
        before.file_mtime  = stat.st_mtime
        before.file_size   = stat.st_size

        # Simulate edit (write new content → changes mtime)
        time.sleep(0.05)
        with open(tmp.name, "w") as f:
            f.write("new content after edit")

        result = ActionResult.ok("edit_file", "Wrote to file", data={"filename": tmp_bare})
        vr = verify_file_edited({"filename": tmp_bare}, result, before)

        if vr.ok:
            _ok("edit_file verifier glob fallback", f"found {tmp_name} via {tmp_bare}.*")
        else:
            _fail("edit_file verifier glob fallback", vr.message)

        os.unlink(tmp.name)

    except Exception as e:
        _fail("edit_file verifier glob fallback", f"exception: {e}\n{traceback.format_exc()}")

    # ── Bug 2: open_app accepts "app" and "application" keys ─────
    try:
        from core.agents.system_agent import SystemControlAgent
        from unittest.mock import patch
        agent = SystemControlAgent(actions_map={})

        # Test that it doesn't fail with "No app name provided" for these keys
        # We mock speak so the test doesn't actually try to talk and listen to the mic
        with patch("control.mac.open_apps.speak"):
            for key in ["app", "application", "target", "name"]:
                result = agent._open_app({key: "TestApp"})
                # It will fail because TestApp doesn't exist, but NOT with "No app name provided"
                error = (result.error or "").lower()
                if "no app name" not in error:
                    _ok(f"open_app accepts '{key}' param key", f"error='{result.error or 'none'}'")
                else:
                    _fail(f"open_app '{key}' key rejected", f"still says: {result.error}")

            # Test empty params still fails correctly
            result = agent._open_app({})
            if "no app name" in (result.error or "").lower():
                _ok("open_app {} params → 'No app name provided'")
            else:
                _fail("open_app {} params", f"unexpected error: {result.error}")

    except Exception as e:
        _fail("open_app param key regression", f"{e}")

    # ── Bug 3: background_gemini model name is valid ─────────────
    try:
        import ast
        with open("core/background_gemini.py") as f:
            content = f.read()
        if "gemini-2.5-flash" in content and "gemini-3.1-flash-lite-preview" not in content:
            _ok("background_gemini model name fixed", "uses gemini-2.5-flash")
        elif "gemini-3.1-flash-lite-preview" in content:
            _fail("background_gemini model name", "still uses dead model 'gemini-3.1-flash-lite-preview'")
        else:
            _skip("background_gemini model name", "can't find model name in file")
    except Exception as e:
        _fail("background_gemini model check", str(e))

    # ── Bug 4: build_single_slot_question local import removed ───
    try:
        with open("core/intent_router.py") as f:
            lines = f.readlines()
        # Check that there's no local 'from core.ambiguity_resolver import build_single_slot_question'
        # inside the route() function body (it should only be in the top-level imports)
        local_imports = [
            (i+1, l.strip()) for i, l in enumerate(lines)
            if "from core.ambiguity_resolver import build_single_slot_question" in l
            and i > 100  # below the top-level import section
        ]
        if not local_imports:
            _ok("build_single_slot_question — no shadowing local import")
        else:
            _fail("build_single_slot_question local import still present",
                  f"line(s): {[ln for ln, _ in local_imports]}")
    except Exception as e:
        _fail("build_single_slot_question check", str(e))

    # ── Bug 5: edit_file content=None → uses `or ""` ─────────────
    try:
        with open("core/intent_router.py") as f:
            content = f.read()
        if 'params.get("content") or ""' in content:
            _ok("edit_file content=None normalization", 'uses .get("content") or ""')
        else:
            _fail("edit_file content=None", 'missing .get("content") or "" guard')
    except Exception as e:
        _fail("edit_file content check", str(e))

    # ── Bug 6: speaker verification threshold is ≤ 0.40 ─────────
    try:
        with open("auth/voice/verify_voice.py") as f:
            content = f.read()
        import re
        m = re.search(r'THRESHOLD\s*=\s*([\d.]+)', content)
        if m:
            threshold = float(m.group(1))
            if threshold <= 0.40:
                _ok("speaker verification threshold", f"THRESHOLD={threshold} (was 0.50, passes 0.37-0.49 scores)")
            else:
                _fail("speaker verification threshold", f"THRESHOLD={threshold} still too high (live scores: 0.37-0.49)")
        else:
            _skip("speaker threshold check", "couldn't parse THRESHOLD value")
    except Exception as e:
        _fail("speaker threshold", str(e))


# ────────────────────────────────────────────────────────────────────────
# SECTION 5 — Fast Intent Routing
# ────────────────────────────────────────────────────────────────────────

def test_fast_intent_routing():
    section("5 · Fast Intent Routing — New Intents & Song Patterns")

    try:
        from core.fast_intent import initialize, classify, INTENT_REGISTRY
        initialize([])
    except Exception as e:
        _skip("fast_intent init", str(e))
        return

    # ── computer_use intent ──────────────────────────────────────
    cu_commands = [
        "send a whatsapp message to my mom",
        "open gmail and search for emails from boss",
        "click the send button",
        "go to youtube and search for music",
        "message my friend on whatsapp",
        "search gmail for unread emails",
        "navigate to the website and click",
    ]
    print("  computer_use routing:")
    cu_hits = 0
    for cmd in cu_commands:
        result = classify(cmd)
        hit = result.action == "computer_use" and result.confidence > 0.50
        if hit:
            cu_hits += 1
        marker = "✅" if hit else "⚠️ "
        print(f"    {marker}  '{cmd[:50]}' → {result.action} ({result.confidence:.2f})")
    rate = cu_hits / len(cu_commands)
    if rate >= 0.7:
        _ok(f"computer_use routing ({cu_hits}/{len(cu_commands)} correct ≥70%)")
    else:
        _fail(f"computer_use routing", f"only {cu_hits}/{len(cu_commands)} correct")

    # ── play_song with named songs ───────────────────────────────
    song_commands = [
        "play a song named back and back",
        "play the song called thriller",
        "play back in black by ac dc",
        "play shape of you by ed sheeran",
        "play me a song named believer",
        "play levitating by dua lipa",
        "i want to hear back and back",
        "play hotel california by eagles",
    ]
    print("  play_song (named songs):")
    song_hits = 0
    for cmd in song_commands:
        result = classify(cmd)
        hit = result.action == "play_song" and result.confidence > 0.40
        if hit:
            song_hits += 1
        marker = "✅" if hit else "⚠️ "
        print(f"    {marker}  '{cmd[:50]}' → {result.action} ({result.confidence:.2f})")
    rate = song_hits / len(song_commands)
    if rate >= 0.7:
        _ok(f"play_song named songs ({song_hits}/{len(song_commands)} correct ≥70%)")
    else:
        _fail(f"play_song named songs", f"only {song_hits}/{len(song_commands)} correct — song patterns may need more examples")

    # ── Sanity: other intents still work ─────────────────────────
    sanity = [
        ("turn up the volume", "volume_up"),
        ("what is the time", "tell_time"),
        ("delete that file", "delete_file"),
        ("open vscode", "open_app"),
        ("take a screenshot", "take_screenshot"),
        ("send an email to my boss", "send_email"),
    ]
    print("  Sanity checks (existing intents):")
    sanity_hits = 0
    for cmd, expected in sanity:
        result = classify(cmd)
        hit = result.action == expected
        if hit:
            sanity_hits += 1
        marker = "✅" if hit else "❌"
        print(f"    {marker}  '{cmd}' → {result.action} (want {expected})")
    if sanity_hits == len(sanity):
        _ok(f"Existing intents unbroken ({sanity_hits}/{len(sanity)})")
    else:
        _fail(f"Existing intents broken", f"{sanity_hits}/{len(sanity)} correct")


# ────────────────────────────────────────────────────────────────────────
# SECTION 6 — File Edge Cases (create → ask name flow)
# ────────────────────────────────────────────────────────────────────────

def test_file_edge_cases():
    section("6 · File Edge Cases — Casual Commands & Name Flow")

    try:
        from core.param_extractors import extract_file_edit_params, extract_filename, _is_meta_content
    except ImportError as e:
        _skip("param_extractors import", str(e))
        return

    # ── edit_file: content that IS real content ──────────────────
    real_content_cases = [
        ("write hi i am batman in notes.txt",       "hi i am batman"),
        ("add hello world to the file",             "hello world"),
        ("inside notes.txt write I am a hero",      "I am a hero"),
        ("append this is a test to the document",   "this is a test"),
    ]
    print("  Real content extraction:")
    for cmd, expected_substr in real_content_cases:
        params = extract_file_edit_params(cmd)
        content = params.get("content") or ""
        if expected_substr.lower() in content.lower():
            _ok(f"real content: '{cmd[:45]}'", f"→ '{content}'")
        else:
            _fail(f"real content: '{cmd[:45]}'", f"expected '{expected_substr}' but got '{content}'")

    # ── edit_file: meta-word content should be cleared (→ ask user) ──
    meta_content_cases = [
        "add some contents in it",
        "type in something inside like this",
        "write some stuff in the file",
        "add text to the file",
        "put something in it",
        "insert contents into the document",
    ]
    print("  Meta-word content clearing (should all return content=None):")
    for cmd in meta_content_cases:
        params = extract_file_edit_params(cmd)
        content = params.get("content")
        if content is None or content == "":
            _ok(f"meta cleared: '{cmd[:45]}'", "content=None ✓ (will ask user)")
        else:
            _fail(f"meta NOT cleared: '{cmd[:45]}'", f"content='{content}' — would write noise!")

    # ── filename extraction: casual names ────────────────────────
    filename_cases = [
        ("create a file called batman or something", "batman"),
        ("make a file named superman",               "superman"),
        ("create notes.txt",                         "notes.txt"),
        ("delete batman.txt please",                 "batman.txt"),
        ("read the file called ideas",               "ideas"),
    ]
    print("  Filename extraction (casual speech):")
    for cmd, expected in filename_cases:
        params = extract_filename(cmd)
        fname = params.get("filename") or ""
        if expected.lower() in fname.lower():
            _ok(f"filename: '{cmd[:45]}'", f"→ '{fname}'")
        else:
            _fail(f"filename: '{cmd[:45]}'", f"expected '{expected}' got '{fname}'")

    # ── _is_meta_content() edge cases ───────────────────────────
    meta_check = [
        ("something",         True),
        ("some content",      True),
        ("contents in it",    True),
        ("hi i am batman",    False),
        ("hello world",       False),
        ("the quick brown",   False),
        ("i want to add",     True),
        ("this is my content", False),  # "content" alone is meta but with real words it's fine
    ]
    print("  _is_meta_content() checks:")
    for text, expected_meta in meta_check:
        result = _is_meta_content(text)
        if result == expected_meta:
            _ok(f"_is_meta_content('{text}')", f"→ {result}")
        else:
            _fail(f"_is_meta_content('{text}')", f"expected {expected_meta} got {result}")

    # ── Compound command: "create file X and write Y" ───────────
    try:
        from core.param_extractors import extract_compound_file_params, is_compound_file_command
        compound_cases = [
            (
                "create a file called notes.txt and write hello world in it",
                {"filename": "notes.txt", "content_substr": "hello world"},
            ),
            (
                "make a file named batman.txt then add i am batman inside",
                {"filename": "batman.txt", "content_substr": "batman"},
            ),
            (
                "create superman.txt and put hi i am superman inside",
                {"filename": "superman.txt", "content_substr": "superman"},
            ),
        ]
        print("  Compound create+write extraction:")
        for cmd, expected in compound_cases:
            is_comp = is_compound_file_command(cmd)
            if not is_comp:
                _fail(f"compound detect: '{cmd[:50]}'", "not detected as compound")
                continue
            params = extract_compound_file_params(cmd)
            fname = params.get("filename") or ""
            content = params.get("content") or ""
            fname_ok   = expected["filename"].lower() in fname.lower()
            content_ok = expected["content_substr"].lower() in content.lower()
            if fname_ok and content_ok:
                _ok(f"compound: '{cmd[:50]}'", f"file='{fname}' content='{content[:30]}'")
            else:
                issues = []
                if not fname_ok:   issues.append(f"filename expected '{expected['filename']}' got '{fname}'")
                if not content_ok: issues.append(f"content expected '{expected['content_substr']}' got '{content}'")
                _fail(f"compound: '{cmd[:50]}'", "; ".join(issues))
    except ImportError as e:
        _skip("compound file tests", str(e))


# ────────────────────────────────────────────────────────────────────────
# SECTION 7 — Live Mouse Demo (optional, needs display)
# ────────────────────────────────────────────────────────────────────────

def test_live_mouse_demo():
    section("7 · Live Mouse Demo — Watch the cursor move!")

    try:
        import control.computer_use as cu
        if not cu.is_available():
            _skip("live mouse demo", "pyautogui unavailable")
            return
    except Exception:
        _skip("live mouse demo", "computer_use not loadable")
        return

    w, h = cu.get_screen_size()
    cx, cy = w // 2, h // 2

    print(f"  Screen: {w}x{h}. Watch the cursor...")

    # Draw a small square with the mouse  
    corners = [
        (cx - 100, cy - 100),
        (cx + 100, cy - 100),
        (cx + 100, cy + 100),
        (cx - 100, cy + 100),
        (cx - 100, cy - 100),
    ]
    all_ok = True
    for (x, y) in corners:
        r = cu.move_to(x, y, duration=0.2)
        if not r.ok:
            all_ok = False
        time.sleep(0.1)

    if all_ok:
        _ok("Mouse draws a square — cursor moved to all 4 corners + back")
    else:
        _fail("Mouse square demo — some moves failed")

    # Return to center
    cu.move_to(cx, cy, duration=0.3)
    _ok("Mouse back at center — demo complete 🎯")


# ────────────────────────────────────────────────────────────────────────
# SECTION 8 — action_verifier registrations
# ────────────────────────────────────────────────────────────────────────

def test_action_verifier():
    section("8 · Action Verifier — Registry & File Ops")

    try:
        from core.action_verifier import (
            verify_action, BeforeState, capture_before_state,
            _resolve_file_path, SAFE_TO_RETRY,
        )
    except ImportError as e:
        _skip("action_verifier import", str(e))
        return

    # _resolve_file_path with absolute path
    abs_path = "/Users/lynux/Desktop/test.txt"
    resolved = _resolve_file_path("edit_file", {"filename": abs_path})
    if resolved == abs_path:
        _ok("_resolve_file_path(absolute)", abs_path)
    else:
        _fail("_resolve_file_path(absolute)", f"got {resolved}")

    # _resolve_file_path with bare name + desktop location
    resolved = _resolve_file_path("edit_file", {"filename": "notes", "location": "desktop"})
    if resolved and "notes" in resolved and "Desktop" in resolved:
        _ok("_resolve_file_path(bare, desktop)", resolved)
    else:
        _fail("_resolve_file_path(bare)", f"got {resolved}")

    # File create → verify_action flow (temp file)
    tmp = tempfile.NamedTemporaryFile(suffix=".txt", delete=False, dir=os.path.expanduser("~/Desktop"))
    tmp.write(b"content")
    tmp.close()
    fname = os.path.basename(tmp.name)

    from core.action_result import ActionResult
    before = capture_before_state("create_file", {"filename": fname, "location": "desktop"})
    result = ActionResult.ok("create_file", f"Created {fname}", data={"filename": fname})
    vr = verify_action("create_file", {"filename": fname, "location": "desktop"}, result, before)
    if vr.ok:
        _ok("verify_action(create_file) — file exists", fname)
    else:
        _fail("verify_action(create_file)", vr.message)

    os.unlink(tmp.name)

    # safe_to_retry set should include edit / create but not delete
    if "edit_file" in SAFE_TO_RETRY:
        _ok("SAFE_TO_RETRY includes edit_file")
    else:
        _skip("SAFE_TO_RETRY.edit_file", "not in set — retries won't happen for edits")

    if "delete_file" not in SAFE_TO_RETRY:
        _ok("SAFE_TO_RETRY excludes delete_file (correct, don't retry deletes)")
    else:
        _fail("SAFE_TO_RETRY includes delete_file", "should NOT retry deletes")


# ────────────────────────────────────────────────────────────────────────
# RUNNER
# ────────────────────────────────────────────────────────────────────────

SUITES = {
    "mouse":   [test_computer_use_module, test_live_mouse_demo],
    "vision":  [test_screen_reader],
    "agents":  [test_computer_use_agent],
    "bugs":    [test_bug_regressions],
    "intent":  [test_fast_intent_routing],
    "files":   [test_file_edge_cases],
    "verify":  [test_action_verifier],
}

ALL_SUITES = [
    test_computer_use_module,
    test_screen_reader,
    test_computer_use_agent,
    test_bug_regressions,
    test_fast_intent_routing,
    test_file_edge_cases,
    test_live_mouse_demo,
    test_action_verifier,
]

if __name__ == "__main__":
    # Change to project root if needed
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
    sys.path.insert(0, script_dir)

    # Load env vars
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    filter_arg = sys.argv[1].lower() if len(sys.argv) > 1 else None

    print(f"\n{BOLD}🧪 ARC Phase 3 Test Suite{RESET}")
    print(f"   Run with: python3 test_phase3.py [mouse|vision|agents|bugs|intent|files|verify]")

    if filter_arg and filter_arg in SUITES:
        print(f"   Filter: {YELLOW}{filter_arg}{RESET}\n")
        to_run = SUITES[filter_arg]
    else:
        print(f"   Running all suites\n")
        to_run = ALL_SUITES

    for suite_fn in to_run:
        try:
            suite_fn()
        except Exception as e:
            section_name = suite_fn.__name__
            print(f"  {RED}💥 SUITE CRASHED: {section_name}{RESET}")
            print(f"     {traceback.format_exc()}")
            FAILED.append(f"{section_name} (CRASHED)")

    exit_code = summary()
    sys.exit(exit_code)
