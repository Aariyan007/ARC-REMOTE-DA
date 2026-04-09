import requests
from core.voice_response import speak

# ─── Settings ────────────────────────────────────────────────
DEFAULT_LOCATION = "Kochi"
# ─────────────────────────────────────────────────────────────


def get_weather(location: str = DEFAULT_LOCATION) -> str:
    """Fetches real weather from wttr.in."""
    try:
        response = requests.get(
            f"https://wttr.in/{location}?format=3",
            timeout=5
        )
        return response.text.strip()
    except:
        return None


def tell_weather(location: str = DEFAULT_LOCATION) -> None:
    """Fetches and speaks real weather."""
    weather = get_weather(location)
    if weather:
        speak(f"Right now, {weather}")
        print(f"🌤️  {weather}")
    else:
        speak("Sorry, I couldn't fetch the weather right now.")