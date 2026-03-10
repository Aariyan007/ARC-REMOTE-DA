import webbrowser
import urllib.parse
from core.voice_response import speak

def search_google(query: str):
    speak(f"Searching Google for {query}")
    """
    Opens Safari with a Google search for the given query.
    
    Example:
        search_google("python tutorial")
        → opens: https://google.com/search?q=python+tutorial
    """
    if not query or not query.strip():
        print("⚠️  No search query provided")
        return

    query = query.strip()
    encoded = urllib.parse.quote(query)   # handles spaces, special chars
    url = f"https://www.google.com/search?q={encoded}"

    print(f"🔍 Searching Google for: '{query}'")
    webbrowser.open(url)


# ─── Quick test ──────────────────────────────────────────────
# Run: python3 control/web_search.py
if __name__ == "__main__":
    test_queries = [
        "python tutorial",
        "how to build a jarvis assistant",
        "weather today",
    ]

    for query in test_queries:
        search_google(query)
        import time; time.sleep(2)