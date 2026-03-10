from datetime import datetime


def tell_time():
    """
    Prints the current time in natural language.
    Example output: "🕐 It's 3:45 PM"
    """
    now = datetime.now()
    formatted = now.strftime("%I:%M %p")   # 03:45 PM format
    formatted = formatted.lstrip("0")      # removes leading zero → 3:45 PM

    print(f"🕐 It's {formatted}")
    return formatted


def tell_date():
    """
    Prints today's date in natural language.
    Example output: "📅 Today is Wednesday, March 11"
    """
    now = datetime.now()
    formatted = now.strftime("%A, %B %d").replace(" 0", " ")  # removes leading zero in day
    print(f"📅 Today is {formatted}")
    return formatted


# ─── Quick test ──────────────────────────────────────────────
# Run: python3 control/time_utils.py
if __name__ == "__main__":
    tell_time()
    tell_date()