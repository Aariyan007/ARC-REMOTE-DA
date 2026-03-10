from datetime import datetime
from core.voice_response import speak

def tell_time():
    now = datetime.now()
    formatted = now.strftime("%I:%M %p").lstrip("0")
    speak(f"It's {formatted}")
    print(f"🕐 It's {formatted}")

def tell_date():
    now = datetime.now()
    formatted = now.strftime("%A, %B %d").replace(" 0", " ")
    speak(f"Today is {formatted}")
    print(f"📅 Today is {formatted}")


# ─── Quick test ──────────────────────────────────────────────
# Run: python3 control/time_utils.py
if __name__ == "__main__":
    tell_time()
    tell_date()