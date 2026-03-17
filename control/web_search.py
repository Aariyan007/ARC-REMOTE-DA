import webbrowser
import urllib.parse
from core.responder import generate_response
from core.voice_response import speak


def search_google(query: str, user_said: str = "search"):
    if not query or not query.strip():
        speak("What would you like me to search for?")
        return

    response = generate_response("search_google", user_said, extra_info=query)
    speak(response)

    encoded = urllib.parse.quote(query.strip())
    webbrowser.open(f"https://www.google.com/search?q={encoded}")