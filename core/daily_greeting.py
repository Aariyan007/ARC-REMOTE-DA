"""
Daily Greeting — runs once per day on first Jarvis startup.

Features:
  - Time-aware greeting (Good morning / afternoon / evening / night)
  - Current temperature + weather
  - Top world news headlines
  - Tracks last greeting date to avoid repeating

Storage: data/last_greeting.json
"""

import json
import os
import re
import requests
from datetime import datetime

from core.voice_response import speak

# ─── Settings ────────────────────────────────────────────────
BASE_DIR         = os.path.dirname(os.path.dirname(__file__))
GREETING_PATH    = os.path.join(BASE_DIR, "data", "last_greeting.json")
DEFAULT_LOCATION = "Thrissur"
NEWS_COUNT       = 3        # how many headlines to read
# ─────────────────────────────────────────────────────────────


def _get_today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _already_greeted_today() -> bool:
    """Check if we've already done the daily greeting today."""
    if not os.path.exists(GREETING_PATH):
        return False
    try:
        with open(GREETING_PATH, "r") as f:
            data = json.load(f)
        return data.get("last_date") == _get_today()
    except (json.JSONDecodeError, IOError):
        return False


def _mark_greeted() -> None:
    """Mark today as greeted."""
    os.makedirs(os.path.dirname(GREETING_PATH), exist_ok=True)
    with open(GREETING_PATH, "w") as f:
        json.dump({"last_date": _get_today()}, f)


def _get_time_greeting() -> str:
    """Returns greeting based on current hour."""
    hour = datetime.now().hour
    if 5 <= hour < 12:
        return "Good morning"
    elif 12 <= hour < 17:
        return "Good afternoon"
    elif 17 <= hour < 21:
        return "Good evening"
    else:
        return "Hey night owl"


def _sanitize_for_speech(text: str) -> str:
    """Cleans text for TTS — removes symbols that cause garbage audio."""
    text = text.replace("°C", " degrees Celsius")
    text = text.replace("°F", " degrees Fahrenheit")
    text = text.replace("°", " degrees ")
    text = text.replace("℃", " degrees Celsius")
    text = text.replace("℉", " degrees Fahrenheit")
    text = re.sub(r'[^\x00-\x7F]+', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _get_weather(location: str = DEFAULT_LOCATION) -> str:
    """Fetches current weather."""
    try:
        response = requests.get(
            f"https://wttr.in/{location}?format=3",
            timeout=5
        )
        raw = response.text.strip()
        return _sanitize_for_speech(raw)
    except Exception:
        return None


def _get_news_headlines(count: int = NEWS_COUNT) -> list:
    """
    Fetches top world news headlines using Google News RSS feed.
    No API key needed.
    """
    try:
        response = requests.get(
            "https://news.google.com/rss?hl=en-IN&gl=IN&ceid=IN:en",
            timeout=8,
            headers={"User-Agent": "Mozilla/5.0"}
        )
        # Parse RSS XML manually (no extra dependencies)
        import xml.etree.ElementTree as ET
        root = ET.fromstring(response.content)
        
        headlines = []
        for item in root.findall(".//item"):
            title = item.find("title")
            if title is not None and title.text:
                # Clean up the headline
                headline = title.text.strip()
                # Remove source suffix like " - BBC News"
                headline = re.sub(r'\s*-\s*[A-Za-z\s]+$', '', headline)
                # Remove HTML entities
                headline = headline.replace("&amp;", "and")
                headline = headline.replace("&quot;", "")
                headline = headline.replace("&#39;", "'")
                if headline and len(headline) > 10:
                    headlines.append(headline)
                    if len(headlines) >= count:
                        break

        return headlines
    except Exception as e:
        print(f"⚠️ News fetch error: {e}")
        return []


def should_greet() -> bool:
    """Returns True if daily greeting hasn't been done today."""
    return not _already_greeted_today()


def daily_greeting(name: str = "Aariyan") -> None:
    """
    Speaks the daily greeting with time, weather, and news.
    Only runs once per day.
    """
    if _already_greeted_today():
        return

    print("\n🌅 Daily greeting starting...")

    greeting = _get_time_greeting()
    now = datetime.now()
    time_str = now.strftime("%I:%M %p").lstrip("0")
    date_str = now.strftime("%A, %B %d")

    # ── Greeting + Time ──────────────────────────────────────
    speak(f"{greeting}, {name}!")
    speak(f"It's {time_str}, {date_str}.")

    # ── Weather ──────────────────────────────────────────────
    weather = _get_weather()
    if weather:
        speak(f"Weather right now: {weather}.")
        print(f"🌤️  {weather}")
    else:
        speak("Couldn't check the weather right now.")

    # ── News Headlines ───────────────────────────────────────
    headlines = _get_news_headlines()
    if headlines:
        speak(f"Here are today's top {len(headlines)} headlines.")
        for i, headline in enumerate(headlines, 1):
            speak(f"{i}. {headline}")
            print(f"📰 {i}. {headline}")
    else:
        speak("Couldn't fetch the news today.")

    # ── Wrap up ──────────────────────────────────────────────
    hour = now.hour
    if 5 <= hour < 12:
        speak("Have a great day ahead. What can I do for you?")
    elif 12 <= hour < 17:
        speak("Hope your day's going well. What do you need?")
    elif 17 <= hour < 21:
        speak("Evening time. What's on your mind?")
    else:
        speak("Late night session. What are we working on?")

    _mark_greeted()
    print("✅ Daily greeting done\n")


# ─── Quick test ──────────────────────────────────────────────
if __name__ == "__main__":
    # Force re-greet for testing
    if os.path.exists(GREETING_PATH):
        os.remove(GREETING_PATH)
    daily_greeting()
"""
Description: New module for daily auto-greeting with time, weather, and world news headlines.
"""
