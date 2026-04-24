import os
import json
import base64
import subprocess
import urllib.parse
import webbrowser
import re

# ─── Gmail API imports are LAZY (deferred to function scope) ──
# google_auth_oauthlib may not be installed; deferring prevents
# ImportError from blocking the entire control layer boot.
# voice imports are also lazy to avoid circular import issues.

def _get_speak():
    from core.voice_response import speak
    return speak

def _get_listen():
    from core.speech_to_text import listen
    return listen

def _get_listen_long():
    from core.speech_to_text import listen_long
    return listen_long

def speak(msg):
    """Proxy to voice_response.speak — lazy loaded."""
    _get_speak()(msg)

def _is_headless_source(source: str) -> bool:
    return (source or "").lower() != "voice"

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
    _source: str = "voice",
    _request_id: str = "",
) -> str:
    """
    Ask a voice question, listen for the answer, optionally confirm,
    and retry up to `max_retries` times if the input is empty or rejected.
    If _source is non-voice, it uses the headless job stream for input instead.

    Args:
        gemini_field: If set (e.g. 'subject', 'recipient'), uses Gemini
                      to extract the actual meaning from natural speech.

    Returns the confirmed text, or "" if all retries exhausted.
    """
    if _is_headless_source(_source) and _request_id:
        from remote.job_store import ask_user
        # Headless mode: ask the client via job stream
        reply = ask_user(_request_id, prompt, event_type="clarify")
        # For text UI, we assume what they typed is what they meant; skip confirmation.
        return reply or ""

    for attempt in range(max_retries + 1):
        speak(prompt if attempt == 0 else f"Let me try again. {prompt}")

        if use_long_listen:
            raw = _get_listen_long()(max_seconds=long_max_seconds,
                                     silence_seconds=long_silence_seconds)
        else:
            raw = _get_listen()()

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
            confirmation = _get_listen()()
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
                        second_confirm = _get_listen()()
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
    """Authenticates and returns Gmail API service. Imports are lazy."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

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

def send_email(to: str = "", subject: str = "", body: str = "", _source: str = "voice", _request_id: str = "") -> str:
    """Opens Gmail compose window pre-filled via a multi-step voice conversation or API."""

    # Step 1: Who to send to
    to = _safe(to)
    if not to:
        to = _voice_input_with_retry(
            prompt="Who do you want to send the email to?",
            confirm_label="recipient",
            max_retries=2,
            gemini_field="recipient",
            _source=_source,
            _request_id=_request_id,
        )
        if not to:
            if not _is_headless_source(_source):
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
            _source=_source,
            _request_id=_request_id,
        )
        if not subject:
            if not _is_headless_source(_source):
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
            _source=_source,
            _request_id=_request_id,
        )
        if not body:
            if not _is_headless_source(_source):
                speak("Cancelled. No message provided.")
            return "Cancelled — missing body"

    # Step 4: Final confirmation
    if _is_headless_source(_source):
        from remote.job_store import ask_user
        reply = ask_user(_request_id, f"Ready to compose email to {to}, subject: '{subject}'. Should I open it?", event_type="confirm")
        confirmation = reply
    else:
        speak(f"Ready to compose email to {to}, subject: {subject}. Should I open it?")
        confirmation = _get_listen()()

    if confirmation and any(
        word in confirmation.lower()
        for word in ["yes", "yeah", "yep", "sure", "do it", "send", "open", "go"]
    ):
        if not _is_headless_source(_source):
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
        if not _is_headless_source(_source):
            speak("Review and send when you're ready.")
        return "Draft opened in Gmail"

    return "Cancelled — email draft not opened"

from control.file_search import search_files_advanced_multiple
from remote.job_store import ask_user, get_job_store, JobEvent

def find_and_send_file(filename: str = "", to: str = "", _source: str = "voice", _request_id: str = "") -> str:
    """Finds a file, asks for disambiguation if multiple match, confirms, and sends via email attachment."""

    if not filename:
        return "Failed — no filename provided to search for."

    matches = search_files_advanced_multiple(filename, top_k=5)
    
    if not matches:
        if not _is_headless_source(_source):
            speak(f"I couldn't find any file matching {filename}.")
        return f"Failed — could not find file matching '{filename}'"

    selected_file = matches[0]

    if len(matches) > 1:
        if _is_headless_source(_source):
            prompt = f"Found multiple matches for '{filename}'. Which one do you want to send?\n"
            for i, match in enumerate(matches):
                prompt += f"{i+1}. {os.path.basename(match)}\n"
            
            reply = ask_user(_request_id, prompt, event_type="clarify")
            # Parse numeric reply (e.g. "1" or "number 2")
            match_idx = re.search(r'\b([1-5])\b', str(reply))
            if match_idx:
                idx = int(match_idx.group(1)) - 1
                if 0 <= idx < len(matches):
                    selected_file = matches[idx]
        else:
            # For voice, just take the first match or ask to clarify (simplified here)
            speak(f"Found {len(matches)} files matching {filename}. I'll use {os.path.basename(matches[0])}.")

    # Step 2: Recipient
    to = _safe(to)
    if not to:
        to = _voice_input_with_retry(
            prompt="Who do you want to send the file to?",
            confirm_label="recipient",
            max_retries=2,
            gemini_field="recipient",
            _source=_source,
            _request_id=_request_id,
        )
        if not to:
            if not _is_headless_source(_source):
                speak("Cancelled. No recipient provided.")
            return "Cancelled — missing recipient"

    to = _resolve_contact(to)

    # Step 3: Confirmation
    file_basename = os.path.basename(selected_file)
    confirm_msg = f"Ready to open Gmail draft to send '{file_basename}' to {to}. Proceed?"
    
    if not _is_headless_source(_source):
        speak(confirm_msg)
        
    # Always ask UI (Remote) but also allow local voice reply if applicable
    # We use a helper to wait for either
    confirmation = ask_user(
        _request_id, 
        confirm_msg, 
        event_type="confirm",
        data={
            "filename": file_basename,
            "recipient": to,
            "path": selected_file,
            "action": "email_send"
        }
    )

    if confirmation and any(word in str(confirmation).lower() for word in ["yes", "yeah", "yep", "sure", "do it", "send", "open", "go"]):
        if not _is_headless_source(_source):
            speak("Opening Gmail with attachment.")
        else:
            # If confirmed via UI, have Jarvis acknowledge it on the PC too if desired
            speak(f"Confirmed. Sending {file_basename} to {to}.")
        
        # Add a progress event so the UI shows activity
        get_job_store().get(_request_id).add_event(
            JobEvent("executing", f"Attaching {file_basename} and drafting email...")
        )
        
        # Use playwright to open draft and attach
        res = draft_email_with_attachment(
            to=to,
            subject=f"Sending: {file_basename}",
            body="",
            attachment_path=selected_file,
            announce=(not _is_headless_source(_source)),
        )
        if res.get("success"):
            if res.get("sent"):
                return f"Sent! {file_basename} has been emailed to {to}. You can check your sent mail for confirmation."
            else:
                return f"Draft opened with {file_basename} attached."
        else:
            return f"Failed to send email: {res.get('error')}"
    else:
        if not _is_headless_source(_source):
            speak("Alright, cancelled.")
        return "Cancelled by user"

# ─── Attachment-capable email draft ──────────────────────────────

def draft_email_with_attachment(
    to: str,
    subject: str = "",
    body: str = "",
    attachment_path: str = None,
    announce: bool = True,
) -> dict:
    """
    Opens Gmail compose with the given fields pre-filled, then attaches
    a file via Playwright browser automation.

    Args:
        to:              Recipient email address
        subject:         Email subject line
        body:            Email body text
        attachment_path: Absolute path to the file to attach (optional)
        announce:        If True, speak status updates (voice mode)

    Returns:
        {
            "success": bool,
            "draft_opened": bool,
            "attachment_verified": bool,
            "error": str
        }
    """
    result = {
        "success": False,
        "draft_opened": False,
        "attachment_verified": False,
        "error": "",
    }

    to = _safe(to)
    subject = _safe(subject)
    body = _safe(body)

    if not to:
        result["error"] = "No recipient provided."
        return result

    # Resolve contact name → email
    to = _resolve_contact(to)

    # Build the Gmail compose URL
    params = urllib.parse.urlencode(
        {"to": to, "su": subject, "body": body},
        quote_via=urllib.parse.quote,
    )
    compose_url = f"https://mail.google.com/mail/?view=cm&fs=1&{params}"
    print(f"📧 Gmail compose URL: {compose_url[:100]}...")

    # ── Attempt Playwright attach ——————————————————————
    if attachment_path:
        try:
            from control.playwright_browser import open_gmail_compose_with_attachment
            attach_result = open_gmail_compose_with_attachment(
                to=to,
                subject=subject,
                body=body,
                file_path=attachment_path,
                auto_send=True,
            )
            result["draft_opened"] = True
            result["attachment_verified"] = attach_result.get("attachment_verified", False)
            result["sent"] = attach_result.get("sent", False)
            result["success"] = True
            if announce:
                if result.get("sent"):
                    speak(f"Done. Email sent to {to} with {os.path.basename(attachment_path)} attached.")
                elif result["attachment_verified"]:
                    speak(f"Draft opened with attachment. Please click send manually.")
                else:
                    speak("Gmail opened. Please verify the attachment and send manually.")
            print(f"  ✔ Draft opened. Attachment: {result['attachment_verified']}, Sent: {result.get('sent', False)}")
            return result
        except Exception as e:
            print(f"  ⚠️  Playwright attach failed ({e}), falling back to URL open.")
            result["error"] = str(e)

    # ── Fallback: open compose URL in default browser (no attachment) ———
    try:
        webbrowser.open(compose_url)
        result["draft_opened"] = True
        result["success"] = True
        if attachment_path:
            result["error"] = "Playwright unavailable; file not attached automatically."
            if announce:
                speak(f"Gmail opened. Please attach {os.path.basename(attachment_path)} manually.")
        else:
            if announce:
                speak("Gmail compose opened. Review and send when ready.")
    except Exception as e:
        result["error"] = str(e)
        if announce:
            speak("Couldn't open Gmail.")

    return result


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
