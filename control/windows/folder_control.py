import subprocess
import os
from core.voice_response import speak

def open_folder(folder_name: str) -> None:
    folder_map = {
        "downloads":  os.path.expanduser("~/Downloads"),
        "desktop":    os.path.expanduser("~/Desktop"),
        "documents":  os.path.expanduser("~/Documents"),
        "pictures":   os.path.expanduser("~/Pictures"),
        "music":      os.path.expanduser("~/Music"),
    }
    path = folder_map.get(folder_name.lower())
    if not path:
        for key, val in folder_map.items():
            if key in folder_name.lower():
                path = val
                break
    if path and os.path.exists(path):
        speak(f"Opening {folder_name}.")
        subprocess.Popen(["explorer", path])
    else:
        speak(f"Couldn't find {folder_name}.")

def create_folder(folder_name: str, location: str = "desktop") -> None:
    location_map = {
        "desktop":   os.path.expanduser("~/Desktop"),
        "downloads": os.path.expanduser("~/Downloads"),
        "documents": os.path.expanduser("~/Documents"),
    }
    base = location_map.get(location.lower(), os.path.expanduser("~/Desktop"))
    path = os.path.join(base, folder_name)
    if os.path.exists(path):
        speak(f"Folder {folder_name} already exists.")
        return
    os.makedirs(path)
    speak(f"Created folder {folder_name}.")
    subprocess.Popen(["explorer", path])
    print(f"📁 Created: {path}")

def search_file(filename: str) -> None:
    """Searches for files and lets user pick which one."""
    speak(f"Searching for {filename}.")

    result = subprocess.run(
        ["mdfind", "-name", filename],
        capture_output=True, text=True, timeout=10
    )

    files = [
        f for f in result.stdout.strip().split("\n")
        if f and not any(skip in f for skip in
                        ["venv", ".git", "Library/Caches", ".pyc", "node_modules"])
    ]

    if not files:
        speak(f"Couldn't find any file named {filename}.")
        return

    if len(files) == 1:
        # Only one result — ask what to do
        name = os.path.basename(files[0])
        location = os.path.dirname(files[0])
        speak(f"Found one file: {name} in {location}. Opening it.")
        subprocess.Popen(["open", files[0]])
        return

    # Multiple results — list them
    speak(f"I found {len(files[:5])} files.")
    for i, f in enumerate(files[:5], 1):
        name     = os.path.basename(f)
        # Get readable location
        location = f.replace(os.path.expanduser("~"), "home")
        location = os.path.dirname(location)
        speak(f"File {i}: {name} in {location}.")
        print(f"  {i}. {name} — {f}")

    speak("Which one do you want? Say the number.")

    # Listen for user's choice
    from core.speech_to_text import listen
    choice = listen()
    print(f"📝 Choice: {choice}")

    # Extract number from choice
    number = None
    for word in choice.split():
        if word.isdigit():
            number = int(word)
            break
        # Handle spoken numbers
        word_map = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
                   "first": 1, "second": 2, "third": 3}
        if word.lower() in word_map:
            number = word_map[word.lower()]
            break

    if number and 1 <= number <= len(files[:5]):
        chosen = files[number - 1]
        name   = os.path.basename(chosen)
        speak(f"Opening {name}.")
        subprocess.Popen(["open", chosen])

        # If text file — offer to read it
        if chosen.endswith((".txt", ".py", ".md", ".js", ".json", ".csv")):
            speak("Want me to read the contents? Say yes or no.")
            answer = listen()
            if "yes" in answer.lower():
                from control.mac.file_ops import read_file
                read_file(name)
    else:
        speak("Didn't catch that. Try searching again.")