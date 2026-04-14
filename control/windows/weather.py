import re
import requests
from core.voice_response import speak

# ─── Settings ────────────────────────────────────────────────
DEFAULT_LOCATION = "Thrissur"
# ─────────────────────────────────────────────────────────────


def _sanitize_for_speech(text: str) -> str:
    """
    Cleans weather output for TTS — replaces symbols that cause
    garbage audio (°, ℃, ℉, emoji, etc.) with spoken equivalents.
    """
    # Degree symbols → "degrees"
    text = text.replace("°C", " degrees Celsius")
    text = text.replace("°F", " degrees Fahrenheit")
    text = text.replace("°", " degrees ")
    text = text.replace("℃", " degrees Celsius")
    text = text.replace("℉", " degrees Fahrenheit")

    # Weather emoji → words
    emoji_map = {
        "☀️": "sunny", "🌤": "partly sunny", "⛅": "partly cloudy",
        "🌥": "mostly cloudy", "☁️": "cloudy", "🌦": "rain showers",
        "🌧": "rainy", "⛈": "thunderstorm", "🌩": "lightning",
        "🌨": "snowy", "❄️": "snow", "🌫": "foggy", "💨": "windy",
        "🌈": "rainbow", "🌙": "clear night", "⭐": "clear",
    }
    for emoji, word in emoji_map.items():
        text = text.replace(emoji, word)

    # Strip any remaining non-ASCII symbols that TTS can't handle
    text = re.sub(r'[^\x00-\x7F]+', ' ', text)

    # Clean extra whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text


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
        clean = _sanitize_for_speech(weather)
        speak(f"Right now, {clean}")
        print(f"🌤️  {weather}")
    else:
        speak("Sorry, I couldn't fetch the weather right now.")