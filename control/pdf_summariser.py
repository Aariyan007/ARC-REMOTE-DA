import os
import json
import time
from google import genai

from dotenv import load_dotenv
# ─── Settings ────────────────────────────────────────────────
load_dotenv()
GEMINI_API_KEY = os.getenv("API_KEY")
MODEL          = "gemini-2.5-flash"
# ─────────────────────────────────────────────────────────────

client = genai.Client(api_key=GEMINI_API_KEY)


def extract_text_from_pdf(pdf_path: str) -> str:
    """Extracts text from PDF using PyPDF2."""
    try:
        import PyPDF2
        text = ""
        with open(pdf_path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                text += page.extract_text() + "\n"
        return text.strip()
    except ImportError:
        print("❌ PyPDF2 not installed. Run: pip install PyPDF2")
        return None
    except Exception as e:
        print(f"❌ Error reading PDF: {e}")
        return None


def summarise_pdf(pdf_path: str) -> str:
    """
    Reads a PDF and returns a spoken summary via Gemini.
    Usage: summarise_pdf("/path/to/file.pdf")
    """
    from core.voice_response import speak

    if not os.path.exists(pdf_path):
        speak("I couldn't find that PDF file.")
        return None

    filename = os.path.basename(pdf_path)
    speak(f"Reading {filename}. Give me a moment.")
    print(f"📄 Reading: {pdf_path}")

    text = extract_text_from_pdf(pdf_path)
    if not text:
        speak("I couldn't read that PDF.")
        return None

    # Truncate if too long for Gemini
    if len(text) > 10000:
        text = text[:10000] + "..."
        print("⚠️  PDF truncated to 10,000 chars for Gemini")

    print(f"📊 Extracted {len(text)} characters")

    try:
        speak("Summarising now.")
        response = client.models.generate_content(
            model=MODEL,
            contents=f"""
Summarise this document in 3-5 sentences.
Speak naturally like you're explaining it to a friend.
Focus on the main points only.
Document:
{text}
"""
        )

        summary = response.text.strip()
        speak(summary)
        print(f"\n📝 Summary:\n{summary}")
        return summary

    except Exception as e:
        if "429" in str(e):
            speak("Rate limited. Try again in a moment.")
        else:
            speak("Had trouble summarising that.")
        print(f"❌ Error: {e}")
        return None


def find_latest_pdf() -> str:
    """Finds the most recently downloaded PDF."""
    downloads = os.path.expanduser("~/Downloads")
    pdfs = [
        os.path.join(downloads, f)
        for f in os.listdir(downloads)
        if f.endswith(".pdf")
    ]
    if not pdfs:
        return None
    return max(pdfs, key=os.path.getmtime)


def summarise_latest_pdf() -> None:
    """Summarises the most recent PDF in Downloads."""
    from core.voice_response import speak
    pdf = find_latest_pdf()
    if pdf:
        print(f"📄 Found latest PDF: {pdf}")
        summarise_pdf(pdf)
    else:
        speak("No PDF files found in Downloads.")


# ─── Quick test ──────────────────────────────────────────────
if __name__ == "__main__":
    # Test with latest PDF in downloads
    pdf = find_latest_pdf()
    if pdf:
        print(f"Found: {pdf}")
        summarise_pdf(pdf)
    else:
        print("No PDFs in Downloads folder")