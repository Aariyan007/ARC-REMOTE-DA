import os
import base64
import subprocess
import urllib.parse
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from core.voice_response import speak
import re

# ─── Settings ────────────────────────────────────────────────
SCOPES           = ["https://www.googleapis.com/auth/gmail.modify"]
CREDENTIALS_FILE = os.path.join(os.path.dirname(__file__), '..', 'credentials.json')
TOKEN_FILE       = os.path.join(os.path.dirname(__file__), '..', 'token.json')
# ─────────────────────────────────────────────────────────────


def get_gmail_service():
    """Authenticates and returns Gmail API service."""
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow  = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
    return build("gmail", "v1", credentials=creds)


def _extract_body(payload: dict) -> str:
    """Extracts plain text body from email payload."""
    body = ""

    # Single part email
    if "body" in payload and payload["body"].get("data"):
        body = base64.urlsafe_b64decode(
            payload["body"]["data"]
        ).decode("utf-8", errors="ignore")

    # Multipart email
    elif "parts" in payload:
        for part in payload["parts"]:
            if part["mimeType"] == "text/plain" and part["body"].get("data"):
                body = base64.urlsafe_b64decode(
                    part["body"]["data"]
                ).decode("utf-8", errors="ignore")
                break
            # Nested parts
            elif "parts" in part:
                for subpart in part["parts"]:
                    if subpart["mimeType"] == "text/plain" and subpart["body"].get("data"):
                        body = base64.urlsafe_b64decode(
                            subpart["body"]["data"]
                        ).decode("utf-8", errors="ignore")
                        break

    # Clean up — remove extra whitespace
    body = re.sub(r'http\S+', '', body)
    body = " ".join(body.split())
    return body


def _speak_email(service, msg_id: str, read_body: bool = False) -> None:
    """Fetches and speaks a single email."""
    data    = service.users().messages().get(
        userId="me", id=msg_id,
        format="full" if read_body else "metadata",
        metadataHeaders=["Subject", "From"]
    ).execute()

    headers     = {h["name"]: h["value"] for h in data["payload"]["headers"]}
    subject     = headers.get("Subject", "No subject")
    sender      = headers.get("From", "Unknown")
    sender_name = sender.split("<")[0].strip().strip('"')

    speak(f"From {sender_name}: {subject}.")
    print(f"📧 From: {sender_name} | Subject: {subject}")

    if read_body:
        body = _extract_body(data["payload"])
        if body:
            # Read first 300 chars — enough to get the gist
            preview = body[:300]
            if len(body) > 300:
                preview += "..."
            speak(f"It says: {preview}")
            print(f"📄 Body preview: {preview[:100]}...")
        else:
            speak("Couldn't read the email body.")


def read_emails(count: int = 5) -> None:
    """Reads latest unread email subjects aloud."""
    speak("Checking your inbox.")
    try:
        service  = get_gmail_service()
        results  = service.users().messages().list(
            userId="me",
            labelIds=["INBOX", "UNREAD"],
            maxResults=count
        ).execute()

        messages = results.get("messages", [])
        if not messages:
            speak("You have no unread emails.")
            return

        speak(f"You have {len(messages)} unread emails.")
        for msg in messages[:count]:
            _speak_email(service, msg["id"], read_body=False)

    except Exception as e:
        print(f"❌ Email error: {e}")
        speak("Couldn't read emails right now.")


def search_emails(query: str) -> None:
    """
    Searches Gmail and reads matching emails aloud.
    Reads subject + body preview for each result.
    """
    speak(f"Searching emails for {query}.")
    try:
        service  = get_gmail_service()
        results  = service.users().messages().list(
            userId="me",
            q=query,
            maxResults=3
        ).execute()

        messages = results.get("messages", [])
        if not messages:
            speak(f"No emails found about {query}.")
            return

        speak(f"Found {len(messages)} emails. Reading them.")
        for msg in messages[:3]:
            _speak_email(service, msg["id"], read_body=True)  # ← reads body too

    except Exception as e:
        print(f"❌ Search error: {e}")
        speak("Couldn't search emails right now.")


def send_email(to: str = "", subject: str = "", body: str = "") -> None:
    """Opens Gmail compose window pre-filled."""
    speak("Opening Gmail to compose an email.")
    params = urllib.parse.urlencode({
        "to":      to,
        "subject": subject,
        "body":    body
    })
    url = f"https://mail.google.com/mail/?view=cm&{params}"
    subprocess.Popen(["open", url])
    speak("Review and send when ready.")


def open_gmail() -> None:
    """Opens Gmail in Safari."""
    speak("Opening Gmail.")
    subprocess.Popen(["open", "https://mail.google.com"])


# ─── Quick test ──────────────────────────────────────────────
if __name__ == "__main__":
    print("Testing Gmail — reading emails...\n")
    read_emails(3)
    print("\nTesting search...\n")
    search_emails("MLH")