import os
import base64
import subprocess
import urllib.parse
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from core.voice_response import speak

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
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)


def read_emails(count: int = 5) -> None:
    """Reads latest unread emails aloud."""
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
            data    = service.users().messages().get(
                userId="me", id=msg["id"], format="metadata",
                metadataHeaders=["Subject", "From"]
            ).execute()

            headers = {h["name"]: h["value"] for h in data["payload"]["headers"]}
            subject = headers.get("Subject", "No subject")
            sender  = headers.get("From", "Unknown")

            # Clean sender name
            sender_name = sender.split("<")[0].strip().strip('"')

            speak(f"From {sender_name}: {subject}.")
            print(f"📧 From: {sender_name} | Subject: {subject}")

    except Exception as e:
        print(f"❌ Email error: {e}")
        speak("Couldn't read emails. Check your connection.")


def search_emails(query: str) -> None:
    """Searches Gmail and reads matching email subjects aloud."""
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

        speak(f"Found {len(messages)} emails about {query}.")

        for msg in messages[:3]:
            data    = service.users().messages().get(
                userId="me", id=msg["id"], format="metadata",
                metadataHeaders=["Subject", "From"]
            ).execute()

            headers     = {h["name"]: h["value"] for h in data["payload"]["headers"]}
            subject     = headers.get("Subject", "No subject")
            sender      = headers.get("From", "Unknown")
            sender_name = sender.split("<")[0].strip().strip('"')

            speak(f"From {sender_name}: {subject}.")
            print(f"📧 From: {sender_name} | Subject: {subject}")

    except Exception as e:
        print(f"❌ Search error: {e}")
        speak("Couldn't search emails right now.")


def read_email_body(msg_id: str) -> None:
    """Reads the full body of a specific email."""
    try:
        service = get_gmail_service()
        data    = service.users().messages().get(
            userId="me", id=msg_id, format="full"
        ).execute()

        # Extract body
        parts = data.get("payload", {}).get("parts", [])
        body  = ""

        for part in parts:
            if part["mimeType"] == "text/plain":
                body = base64.urlsafe_b64decode(
                    part["body"]["data"]
                ).decode("utf-8")
                break

        if body:
            # Truncate if too long
            if len(body) > 500:
                body = body[:500] + "..."
            speak(body)
        else:
            speak("Couldn't read the email body.")

    except Exception as e:
        print(f"❌ Error reading body: {e}")


def send_email(to: str = "", subject: str = "", body: str = "") -> None:
    """Opens Gmail compose in Safari — pre-filled."""
    speak(f"Opening Gmail to send email.")
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
    print("Testing Gmail API...")
    print("First run will open browser for authorization.\n")
    read_emails(3)