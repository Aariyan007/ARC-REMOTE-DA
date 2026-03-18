from datetime import datetime
from core.responder import generate_response
from core.voice_response import speak


def tell_time(user_said: str = "what time is it"):
    now       = datetime.now()
    formatted = now.strftime("%I:%M %p").lstrip("0")
    response  = generate_response("tell_time", user_said, extra_info=formatted)
    speak(f"{response} {formatted}")
    print(f"🕐 It's {formatted}")


def tell_date(user_said: str = "what's the date"):
    now       = datetime.now()
    formatted = now.strftime("%A, %B %d").replace(" 0", " ")
    response  = generate_response("tell_date", user_said, extra_info=formatted)
    speak(f"{response} {formatted}")
    print(f"📅 Today is {formatted}")