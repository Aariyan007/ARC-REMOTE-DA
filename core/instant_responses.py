"""
Instant Response Engine — picks natural, varied responses instantly.

Instead of "Opening VS Code." every single time, randomly picks
from a pool of mood-aware variations. Tracks recent responses
to avoid repetition. Runs in <1ms.
"""

import random
from collections import deque


# ─── Response Pools ──────────────────────────────────────────
# Per-action pools with mood variants.
# Format: { action: { mood: [responses] } }
RESPONSE_POOL = {
    # ── App actions ──────────────────────────────────────────
    "open_app": {
        "casual":    ["Got it.", "Opening it up.", "Here you go.", "On it.", "Firing it up.", "Right away."],
        "focused":   ["Opening.", "Done.", "Launching.", "Ready."],
        "sarcastic": ["Your wish is my command.", "Opening, again.", "Oh, this one. Sure.", "Let me guess, work? Opening."],
        "night":     ["Opening.", "Here.", "Got it."],
    },
    "close_app": {
        "casual":    ["Closing it.", "Done.", "Gone.", "Shut it down."],
        "focused":   ["Closed.", "Done."],
        "sarcastic": ["Finally closing that, huh?", "Bye bye.", "Good riddance."],
        "night":     ["Closed.", "Done."],
    },
    "switch_to_app": {
        "casual":    ["Switching now.", "There you go.", "Switching over."],
        "focused":   ["Switched.", "Done."],
        "sarcastic": ["Jumping to it.", "Switching, as always."],
        "night":     ["Switched.", "Here."],
    },

    # ── Volume / Brightness ──────────────────────────────────
    "volume_up": {
        "casual":    ["Louder it is.", "Turning up.", "Volume bumped.", "Cranking it up."],
        "focused":   ["Volume up.", "Louder."],
        "sarcastic": ["Hope the neighbors don't mind.", "Louder, got it.", "Turning it up, DJ."],
        "night":     ["Turning up a bit.", "Louder."],
    },
    "volume_down": {
        "casual":    ["Turning down.", "Quieter now.", "Lowering volume."],
        "focused":   ["Volume down.", "Lower."],
        "sarcastic": ["Peace and quiet, finally.", "Toning it down."],
        "night":     ["Quieter.", "Down."],
    },
    "mute": {
        "casual":    ["Muted.", "Shhh.", "Silence.", "All quiet now."],
        "focused":   ["Muted.", "Silent."],
        "sarcastic": ["Finally, silence.", "Muted, you're welcome.", "Ah, peace."],
        "night":     ["Muted.", "Quiet."],
    },
    "unmute": {
        "casual":    ["Unmuted.", "Sound's back.", "Audio on."],
        "focused":   ["Unmuted.", "Sound on."],
        "sarcastic": ["Back to noise.", "Unmuted, brace yourself."],
        "night":     ["Unmuted.", "Sound on."],
    },
    "brightness_up": {
        "casual":    ["Brighter.", "Brightening up.", "More light."],
        "focused":   ["Brighter.", "Up."],
        "sarcastic": ["Let there be light.", "Brighter, alright."],
        "night":     ["A bit brighter.", "Brighter."],
    },
    "brightness_down": {
        "casual":    ["Dimming.", "Darker now.", "Easing up on the brightness."],
        "focused":   ["Dimmer.", "Down."],
        "sarcastic": ["Going dark mode? Dimming.", "Easy on the eyes."],
        "night":     ["Dimmed.", "Darker."],
    },

    # ── System ───────────────────────────────────────────────
    "lock_screen": {
        "casual":    ["Locking up.", "Screen locked.", "Locked."],
        "focused":   ["Locked.", "Screen locked."],
        "sarcastic": ["Locking it. Don't forget your password.", "Locked. See you."],
        "night":     ["Locked.", "Night."],
    },
    "take_screenshot": {
        "casual":    ["Screenshot taken.", "Captured.", "Got it on screen."],
        "focused":   ["Screenshot saved.", "Captured."],
        "sarcastic": ["Cheese! Screenshot taken.", "Snapped."],
        "night":     ["Screenshot taken.", "Saved."],
    },
    "get_battery": {
        "casual":    ["Checking battery.", "Let me check.", "One sec."],
        "focused":   ["Checking.", "Battery check."],
        "sarcastic": ["Running on fumes? Let me check.", "Battery check incoming."],
        "night":     ["Checking.", "One sec."],
    },

    # ── Navigation ───────────────────────────────────────────
    "search_google": {
        "casual":    ["Searching now.", "Let me look that up.", "On it."],
        "focused":   ["Searching.", "Looking up."],
        "sarcastic": ["To Google we go.", "Googling, as one does."],
        "night":     ["Searching.", "Looking."],
    },
    "open_folder": {
        "casual":    ["Opening it.", "There you go.", "Here's your folder."],
        "focused":   ["Opening.", "Done."],
        "sarcastic": ["Your folder, sir.", "Opening, of course."],
        "night":     ["Opened.", "Here."],
    },
    "tell_time": {
        "casual":    ["Here's the time.", "Let me check.", "The time is"],
        "focused":   ["The time is"],
        "sarcastic": ["You don't have a clock? The time is", "Time check—"],
        "night":     ["It's"],
    },
    "tell_date": {
        "casual":    ["Today is", "The date is", "Here's today's date."],
        "focused":   ["Today is"],
        "sarcastic": ["Lost track of the days? Today is", "Date check—"],
        "night":     ["Today is"],
    },
    "tell_weather": {
        "casual":    ["Checking the weather.", "Let me see.", "Weather check."],
        "focused":   ["Checking.", "Weather coming up."],
        "sarcastic": ["Just look outside. Kidding, checking now.", "Weather, coming up."],
        "night":     ["Checking weather.", "One sec."],
    },

    # ── Email ────────────────────────────────────────────────
    "read_emails": {
        "casual":    ["Checking your inbox.", "Let me see what's new.", "Pulling up emails."],
        "focused":   ["Checking inbox.", "Emails."],
        "sarcastic": ["Let's see what the world wants from you.", "Inbox time."],
        "night":     ["Checking.", "Inbox."],
    },
    "send_email": {
        "casual":    ["Composing email.", "Setting that up.", "Email ready."],
        "focused":   ["Composing.", "Email."],
        "sarcastic": ["Email duty. Composing.", "Another email? Composing."],
        "night":     ["Composing.", "Setting up."],
    },
    "open_gmail": {
        "casual":    ["Opening Gmail.", "Here's your mail.", "Gmail coming up."],
        "focused":   ["Opening Gmail.", "Gmail."],
        "sarcastic": ["Gmail, your second home. Opening.", "Mail time."],
        "night":     ["Opening Gmail.", "Here."],
    },

    # ── Window Management ────────────────────────────────────
    "minimize_all":    {"casual": ["All minimized.", "Desktop clear."], "focused": ["Done."], "sarcastic": ["Everything hidden.", "Clean slate."], "night": ["Done."]},
    "minimise_all":    {"casual": ["All minimized.", "Desktop clear."], "focused": ["Done."], "sarcastic": ["Everything hidden.", "Clean slate."], "night": ["Done."]},
    "show_desktop":    {"casual": ["Showing desktop.", "Here it is."], "focused": ["Desktop."], "sarcastic": ["The beautiful empty desktop."], "night": ["Desktop."]},
    "close_window":    {"casual": ["Window closed.", "Gone."], "focused": ["Closed."], "sarcastic": ["Window gone.", "Bye bye window."], "night": ["Closed."]},
    "close_tab":       {"casual": ["Tab closed.", "Done."], "focused": ["Closed."], "sarcastic": ["One less tab. Progress."], "night": ["Closed."]},
    "new_tab":         {"casual": ["New tab.", "Fresh tab."], "focused": ["New tab."], "sarcastic": ["Another tab? Sure."], "night": ["New tab."]},
    "fullscreen":      {"casual": ["Fullscreen.", "Going full."], "focused": ["Fullscreen."], "sarcastic": ["Maximum screen real estate."], "night": ["Fullscreen."]},
    "mission_control": {"casual": ["Mission control.", "All windows."], "focused": ["Mission control."], "sarcastic": ["Houston, we have windows."], "night": ["Here."]},

    # ── Routines ─────────────────────────────────────────────
    "start_work_day": {
        "casual":    ["Starting your work day.", "Work mode activated.", "Let's get to it."],
        "focused":   ["Work mode on.", "Starting."],
        "sarcastic": ["Time to pretend to be productive. Starting work day.", "Let's grind."],
        "night":     ["Starting work day.", "Here we go."],
    },
    "end_work_day": {
        "casual":    ["Wrapping up.", "Day's done.", "Ending work day."],
        "focused":   ["Ending.", "Done for the day."],
        "sarcastic": ["Freedom at last. Ending work day.", "Quitting time!"],
        "night":     ["Wrapping up.", "Done."],
    },
    "morning_briefing": {
        "casual":    ["Here's your briefing.", "Morning update coming up.", "Let me brief you."],
        "focused":   ["Briefing.", "Here's today."],
        "sarcastic": ["Rise and shine. Here's your briefing.", "The daily news."],
        "night":     ["Briefing.", "Here."],
    },

    # ── File Operations ──────────────────────────────────────
    "read_file":       {"casual": ["Reading it.", "Let me read that."], "focused": ["Reading."], "sarcastic": ["Reading, one sec."], "night": ["Reading."]},
    "create_file":     {"casual": ["Creating it.", "File coming up."], "focused": ["Creating."], "sarcastic": ["Another file? Creating."], "night": ["Creating."]},
    "delete_file":     {"casual": ["Deleting.", "Moving to trash."], "focused": ["Deleting."], "sarcastic": ["Gone forever. Just kidding, it's in trash."], "night": ["Deleted."]},
    "rename_file":     {"casual": ["Renaming.", "Done."], "focused": ["Renamed."], "sarcastic": ["New name, who dis?"], "night": ["Renamed."]},
    "copy_file":       {"casual": ["Copying.", "Done."], "focused": ["Copied."], "sarcastic": ["Copy that. Literally."], "night": ["Copied."]},
    "get_recent_files": {"casual": ["Checking recent files.", "Let me see."], "focused": ["Checking."], "sarcastic": ["What have you been up to? Checking."], "night": ["Checking."]},

    # ── PDF ───────────────────────────────────────────────────
    "summarise_pdf":   {"casual": ["Reading the PDF.", "Summarizing."], "focused": ["Reading PDF."], "sarcastic": ["PDF time. Summarizing."], "night": ["Reading."]},

    # ── Shutdown/Restart (after confirmation) ────────────────
    "shutdown_pc":     {"casual": ["Shutting down.", "Goodbye."], "focused": ["Shutting down."], "sarcastic": ["Shutting down. See you on the other side."], "night": ["Shutting down. Night."]},
    "restart_pc":      {"casual": ["Restarting.", "Be right back."], "focused": ["Restarting."], "sarcastic": ["Restarting. Don't go anywhere."], "night": ["Restarting."]},
    "sleep_mac":       {"casual": ["Going to sleep.", "Nap time."], "focused": ["Sleeping."], "sarcastic": ["Sleepy time.", "Napping."], "night": ["Sleeping. Night."]},

    # ── Generic fallback ─────────────────────────────────────
    "_fallback": {
        "casual":    ["Got it.", "On it.", "Done.", "Sure thing.", "Right away."],
        "focused":   ["Done.", "Got it.", "Ready."],
        "sarcastic": ["As you wish.", "Your command, executed.", "Done, obviously."],
        "night":     ["Done.", "Got it."],
    },

    # ── Confirmation prompts ─────────────────────────────────
    "_confirm": {
        "casual":    ["Are you sure?", "Should I go ahead?", "Confirm?"],
        "focused":   ["Confirm?", "Proceed?"],
        "sarcastic": ["You sure about that?", "Really? Confirm?"],
        "night":     ["Sure?", "Confirm?"],
    },
}


# ─── Anti-Repetition Tracker ────────────────────────────────
# Keeps last N responses to avoid saying the same thing twice.
_recent_responses: deque = deque(maxlen=8)


def get_instant_response(action: str, mood: str = "casual") -> str:
    """
    Returns a varied, mood-aware instant response for the given action.
    Tracks recent responses to avoid repetition.
    """
    # Get pool for this action, fallback to generic
    pool = RESPONSE_POOL.get(action, RESPONSE_POOL["_fallback"])

    # Get mood-specific responses, fallback to casual
    if isinstance(pool, dict):
        responses = pool.get(mood, pool.get("casual", ["Got it."]))
    else:
        responses = pool

    # Filter out recently used responses
    available = [r for r in responses if r not in _recent_responses]
    if not available:
        available = responses  # Reset if all were used

    # Pick and track
    chosen = random.choice(available)
    _recent_responses.append(chosen)
    return chosen


def get_confirmation_prompt(action: str, mood: str = "casual") -> str:
    """
    Returns a confirmation prompt for destructive actions.
    E.g., "I'm about to shut down your Mac. Should I?"
    """
    action_descriptions = {
        "shutdown_pc": "shut down your Mac",
        "restart_pc":  "restart your Mac",
        "delete_file": "delete that file",
        "send_email":  "send that email",
    }

    desc = action_descriptions.get(action, f"perform {action}")
    prefix = get_instant_response("_confirm", mood)

    return f"I'm about to {desc}. {prefix}"


# ─── Quick test ──────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("  INSTANT RESPONSE ENGINE TEST")
    print("=" * 60)

    for mood in ["casual", "sarcastic", "focused", "night"]:
        print(f"\n── Mood: {mood} ──")
        for action in ["open_app", "volume_up", "search_google", "shutdown_pc"]:
            responses = [get_instant_response(action, mood) for _ in range(3)]
            print(f"  {action}: {responses}")

    print("\n── Confirmation Prompts ──")
    for action in ["shutdown_pc", "delete_file", "send_email"]:
        print(f"  {action}: {get_confirmation_prompt(action, 'casual')}")
