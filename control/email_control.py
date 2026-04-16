import os
import json
import base64
import subprocess
import urllib.parse
import webbrowser
import re
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from core.voice_response import speak
from core.speech_to_text import listen, listen_long

# ─── Settings ────────────────────────────────────────────────
SCOPES           = ["https://www.googleapis.com/auth/gmail.modify"]
CREDENTIALS_FILE = os.path.join(os.path.dirname(__file__), '..', 'credentials.json')
TOKEN_FILE       = os.path.join(os.path.dirname(__file__), '..', 'token.json')
# ─────────────────────────────────────────────────────────────


# ─── Helpers ─────────────────────────────────────────────────

def _safe(value) -> str:
    """Sanitise a value for use in email fields. Never returns None."""
    if value is None:
        return ""
    return str(value).strip()


def _resolve_contact(name: str) -> str:
    """
    Resolves a contact name to an email address from data/contacts.json.
    Falls back to returning the original name if no match found.
    """
    contacts_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'contacts.json')
    if os.path.exists(contacts_path):
        try:
            with open(contacts_path) as f:
                contacts = json.load(f)
            name_lower = name.lower().strip()
            # Exact match
            if name_lower in contacts:
                email = contacts[name_lower]
                print(f"📞 Contact resolved: '{name}' → {email}")
                return email
            # Fuzzy substring match
            for contact_name, email in contacts.items():
                if contact_name in name_lower or name_lower in contact_name:
                    print(f"📞 Contact resolved (fuzzy): '{name}' → {email}")
                    return email
        except Exception as e:
            print(f"⚠️  Contact lookup error: {e}")
    return name


def _extract_meaning_with_gemini(raw_text: str, field_type: str) -> str:
    """
    Use Gemini to extract the actual meaning from a voice transcription.
    field_type: 'subject', 'recipient', 'body', etc.
    """
    try:
        from google import genai
        client = genai.Client(api_key=os.getenv("API_KEY"))
        prompt = f"""Extract the actual email {field_type} from this voice input.
The user was asked "What is the {field_type}?" and they said: "{raw_text}"

Return ONLY the extracted {field_type}, nothing else. No quotes, no explanation.
Examples:
- "my college is the subject" → my college
- "write subject as my college" → my college
- "the subject is meeting tomorrow" → meeting tomorrow
- "right subject as my college" → my college
- "i said my college" → my college
- "no i said my college" → my college
- "say hi to Aariyan" → Aariyan
- "send it to my friend aryan" → aryan
- "just write hello world" → hello world
"""
        response = client.models.generate_content(model="gemini-3.1-flash-lite-preview", contents=prompt)
        extracted = response.text.strip()
        if extracted:
            print(f"🧠 Gemini extracted {field_type}: '{raw_text}' → '{extracted}'")
            return extracted
        return raw_text
    except Exception as e:
        print(f"⚠️  Gemini extraction failed: {e}")
        return raw_text


def _voice_input_with_retry(
    prompt: str,
    confirm_label: str = "",
    max_retries: int = 2,
    use_long_listen: bool = False,
    long_max_seconds: int = 30,
    long_silence_seconds: float = 2.5,
    gemini_field: str = "",
) -> str:
    """
    Ask a voice question, listen for the answer, optionally confirm,
    and retry up to `max_retries` times if the input is empty or rejected.

    Args:
        gemini_field: If set (e.g. 'subject', 'recipient'), uses Gemini
                      to extract the actual meaning from natural speech.

    Returns the confirmed text, or "" if all retries exhausted.
    """
    for attempt in range(max_retries + 1):
        speak(prompt if attempt == 0 else f"Let me try again. {prompt}")

        if use_long_listen:
            raw = listen_long(max_seconds=long_max_seconds,
                              silence_seconds=long_silence_seconds)
        else:
            raw = listen()

        text = _safe(raw)
        if not text:
            if attempt < max_retries:
                speak("I didn't catch that.")
                continue
            else:
                speak("Still couldn't hear you. Skipping this.")
                return ""

        # ── Gemini-assisted extraction ─────────────────────
        if gemini_field:
            text = _extract_meaning_with_gemini(text, gemini_field)

        # ── Confirmation step ────────────────────────────────
        if confirm_label:
            speak(f"Did you say {confirm_label}: {text}?")
            confirmation = listen()
            if confirmation and any(
                w in confirmation.lower()
                for w in ["yes", "yeah", "yep", "correct", "right", "sure", "that's right"]
            ):
                return text
            elif confirmation and any(
                w in confirmation.lower()
                for w in ["no", "nope", "wrong", "change", "not right"]
            ):
                # ── Smart correction: extract what they actually said ──
                if gemini_field and confirmation:
                    corrected = _extract_meaning_with_gemini(confirmation, gemini_field)
                    if corrected and corrected.lower() != confirmation.lower():
                        speak(f"Got it. {confirm_label}: {corrected}. Correct?")
                        second_confirm = listen()
                        if second_confirm and any(
                            w in second_confirm.lower()
                            for w in ["yes", "yeah", "yep", "correct", "right", "sure"]
                        ):
                            return corrected
                if attempt < max_retries:
                    continue
                else:
                    speak("Alright, going with what I heard.")
                    return text
            else:
                # Ambiguous response — accept what we heard
                return text
        else:
            return text

    return ""


# ─── Gmail Service ───────────────────────────────────────────

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


# ─── Email Body Extraction ──────────────────────────────────

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


# ─── Read / Search / Open ────────────────────────────────────

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


# ─── Send Email (Voice-Driven Multi-Step) ────────────────────

def send_email(to: str = "", subject: str = "", body: str = "") -> None:
    """Opens Gmail compose window pre-filled via a multi-step voice conversation."""

    # Step 1: Who to send to
    to = _safe(to)
    if not to:
        to = _voice_input_with_retry(
            prompt="Who do you want to send the email to?",
            confirm_label="recipient",
            max_retries=2,
            gemini_field="recipient",
        )
        if not to:
            speak("Cancelled. No recipient provided.")
            return "Cancelled — missing recipient"

    # ── Resolve contact name to email address ────────────────
    to = _resolve_contact(to)

    # Step 2: Subject
    subject = _safe(subject)
    if not subject:
        subject = _voice_input_with_retry(
            prompt="What is the subject?",
            confirm_label="subject",
            max_retries=2,
            gemini_field="subject",
        )
        if not subject:
            speak("Cancelled. No subject provided.")
            return "Cancelled — missing subject"

    # Step 3: Body (use long listen for extended speech)
    body = _safe(body)
    if not body:
        body = _voice_input_with_retry(
            prompt="What should the email say?",
            confirm_label="",  # skip confirmation for body — too long
            max_retries=2,
            use_long_listen=True,
            long_max_seconds=30,
            long_silence_seconds=2.5,
        )
        if not body:
            speak("Cancelled. No message provided.")
            return "Cancelled — missing body"

    # Step 4: Final confirmation
    speak(f"Ready to compose email to {to}, subject: {subject}. Should I open it?")
    confirmation = listen()

    if confirmation and any(
        word in confirmation.lower()
        for word in ["yes", "yeah", "yep", "sure", "do it", "send", "open", "go"]
    ):
        speak("Opening Gmail to compose.")

        # ── Proper URL construction — fixes Issue 1 ──────────
        params = urllib.parse.urlencode(
            {
                "to":      _safe(to),
                "su":      _safe(subject),
                "body":    _safe(body),
            },
            quote_via=urllib.parse.quote,
        )

        url = f"https://mail.google.com/mail/?view=cm&fs=1&{params}"
        print(f"📧 Gmail URL: {url[:120]}...")
        webbrowser.open(url)
        speak("Review and send when you're ready.")
        return "Draft opened in Gmail"
    else:
        speak("Alright, email cancelled.")
        return "Email cancelled by user"


def open_gmail() -> None:
    """Opens Gmail in the default browser."""
    speak("Opening Gmail.")
    webbrowser.open("https://mail.google.com")


# ─── Quick test ──────────────────────────────────────────────
if __name__ == "__main__":
    print("Testing Gmail — reading emails...\n")
    read_emails(3)
    print("\nTesting search...\n")
    search_emails("MLH")