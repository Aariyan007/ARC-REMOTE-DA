import urllib.parse
import webbrowser


def search_google(query: str):
    if not query or not query.strip():
        return
    q = query.strip()
    try:
        from control.playwright_browser import search_google_in_browser

        search_google_in_browser(q)
        return
    except Exception as e:
        print(f"[search_google] Playwright unavailable ({e}); using system browser.")

    encoded = urllib.parse.quote(q)
    webbrowser.open(f"https://www.google.com/search?q={encoded}")