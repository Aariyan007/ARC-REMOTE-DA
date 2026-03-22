import subprocess
import requests
from datetime import datetime
from core.voice_response import speak
from core.memory import load_profile

# ─── Settings ────────────────────────────────────────────────
DEFAULT_LOCATION = "Malappuram"
# ─────────────────────────────────────────────────────────────


def get_weather(location: str = DEFAULT_LOCATION) -> str:
    """Gets current weather for location."""
    try:
        response = requests.get(
            f"https://wttr.in/{location}?format=3",
            timeout=5
        )
        return response.text.strip()
    except:
        return "Weather unavailable"


def get_mac_temperature() -> str:
    """Gets Mac CPU temperature."""
    try:
        result = subprocess.run(
            ["osx-cpu-temp"],
            capture_output=True, text=True, timeout=3
        )
        temp = result.stdout.strip()
        return f"Mac running at {temp}"
    except:
        # Fallback — read from system_profiler
        try:
            result = subprocess.run(
                ["sudo", "powermetrics", "--samplers", "smc", "-n", "1"],
                capture_output=True, text=True, timeout=5
            )
            for line in result.stdout.split("\n"):
                if "CPU die temperature" in line:
                    return f"Mac CPU at {line.split(':')[1].strip()}"
        except:
            pass
        return None


def get_time_greeting() -> str:
    """Returns appropriate greeting based on time."""
    hour = datetime.now().hour
    if 5 <= hour < 12:
        return "Good morning"
    elif 12 <= hour < 17:
        return "Good afternoon"
    elif 17 <= hour < 21:
        return "Good evening"
    else:
        return "Hey, still up"


def morning_briefing() -> None:
    """
    Speaks a full personalised morning briefing.
    Call with: "Jarvis morning briefing"
    """
    profile  = load_profile()
    name     = profile.get("name", "Aariyan")
    facts    = profile.get("learned_facts", [])
    now      = datetime.now()

    # ── Build briefing parts ─────────────────────────────────
    greeting    = get_time_greeting()
    time_str    = now.strftime("%I:%M %p").lstrip("0")
    date_str    = now.strftime("%A, %B %d")
    weather     = get_weather()
    mac_temp    = get_mac_temperature()

    # Find relevant facts for today
    routine_hints = []
    hour = now.hour

    # Morning routine reminders from learned facts
    if 7 <= hour < 10:
        routine_hints.append("Don't skip breakfast today.")
    if 18 <= hour < 19:
        routine_hints.append("LeetCode time — 6:30 to 7:30.")
    if 16 <= hour < 17:
        routine_hints.append("Gym time — don't skip it.")

    # Find current project from facts
    project_hint = None
    for fact in facts:
        if "jarvis" in fact.lower() or "working on" in fact.lower():
            project_hint = "You were working on Jarvis last session."
            break

    # ── Speak briefing ───────────────────────────────────────
    speak(f"{greeting} {name}.")
    speak(f"It's {time_str} on {date_str}.")
    speak(f"Weather: {weather}.")

    if mac_temp:
        speak(mac_temp)

    if project_hint:
        speak(project_hint)

    for hint in routine_hints:
        speak(hint)

    speak("That's your briefing. Let's get it.")


# ─── Quick test ──────────────────────────────────────────────
if __name__ == "__main__":
    morning_briefing()