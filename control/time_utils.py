from datetime import datetime
from core.voice_response import speak

def tell_time():
    now = datetime.now()
    formatted = now.strftime("%I:%M %p").lstrip("0")
    message = f"It's {formatted}"
    speak(message)
    print(f"🕐 {message}")
    return message

def tell_date():
    now = datetime.now()
    formatted = now.strftime("%A, %B %d").replace(" 0", " ")
    message = f"Today is {formatted}"
    speak(message)
    print(f"📅 {formatted}")
    return message
