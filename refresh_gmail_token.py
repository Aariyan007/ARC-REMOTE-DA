"""
Quick script to re-authenticate Gmail API and refresh token.json.
Run this once, it will open a browser for Google OAuth consent.
"""
import os
import sys

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]
CREDENTIALS_FILE = os.path.join(os.path.dirname(__file__), 'credentials.json')
TOKEN_FILE = os.path.join(os.path.dirname(__file__), 'token.json')

def refresh_token():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    # Delete old token
    if os.path.exists(TOKEN_FILE):
        os.remove(TOKEN_FILE)
        print("🗑️  Deleted old token.json")

    # Re-authenticate
    print("🔐 Opening browser for Google OAuth consent...")
    flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
    creds = flow.run_local_server(port=0)
    
    with open(TOKEN_FILE, "w") as f:
        f.write(creds.to_json())
    print(f"✅ New token saved to {TOKEN_FILE}")
    
    # Quick test: try sending a test email
    from googleapiclient.discovery import build
    service = build("gmail", "v1", credentials=creds)
    profile = service.users().getProfile(userId="me").execute()
    print(f"✅ Authenticated as: {profile.get('emailAddress')}")
    print(f"✅ Total messages: {profile.get('messagesTotal')}")
    print("\n🎉 Gmail API is ready! You can now send emails from ARC.")

if __name__ == "__main__":
    refresh_token()
