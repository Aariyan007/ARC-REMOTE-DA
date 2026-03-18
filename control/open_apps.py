import subprocess
from core.responder import generate_response
from core.voice_response import speak


def open_vscode(user_said: str = "open vscode"):
    response = generate_response("open_vscode", user_said)
    speak(response)
    subprocess.Popen(["open", "-a", "Visual Studio Code"])


def open_safari(user_said: str = "open safari"):
    response = generate_response("open_safari", user_said)
    speak(response)
    subprocess.Popen(["open", "-a", "Safari"])


def open_terminal(user_said: str = "open terminal"):
    response = generate_response("open_terminal", user_said)
    speak(response)
    subprocess.Popen(["open", "-a", "Terminal"])