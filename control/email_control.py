import subprocess
import urllib.parse
from core.voice_response import speak


def read_emails() -> None:
    """Opens Gmail inbox in Safari."""
    speak("Opening your Gmail inbox.")
    subprocess.Popen(["open", "https://mail.google.com"])


def search_emails(query: str) -> None:
    """Opens Gmail with search query."""
    speak(f"Searching Gmail for {query}.")
    encoded = urllib.parse.quote(query)
    url = f"https://mail.google.com/mail/u/0/#search/{encoded}"
    subprocess.Popen(["open", url])


def send_email(to: str = "", subject: str = "", body: str = "") -> None:
    """Opens Gmail compose window."""
    speak("Opening Gmail to compose an email.")
    params = urllib.parse.urlencode({
        "to":      to,
        "subject": subject,
        "body":    body
    })
    url = f"https://mail.google.com/mail/?view=cm&{params}"
    subprocess.Popen(["open", url])


def open_gmail() -> None:
    """Opens Gmail."""
    speak("Opening Gmail.")
    subprocess.Popen(["open", "https://mail.google.com"])


# ─── Quick test ──────────────────────────────────────────────
if __name__ == "__main__":
    print("Testing email — opening Gmail...")
    read_emails()