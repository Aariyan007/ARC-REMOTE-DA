import webbrowser
import urllib.parse

def search_google(query: str):
    if not query or not query.strip():
        return
    encoded = urllib.parse.quote(query.strip())
    webbrowser.open(f"https://www.google.com/search?q={encoded}")