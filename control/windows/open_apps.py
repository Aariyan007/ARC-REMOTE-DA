import subprocess
import os

def open_vscode():
    subprocess.Popen(["code"], shell=True)

def open_safari():
    # Windows doesn't have Safari — open default browser
    import webbrowser
    webbrowser.open("https://google.com")

def open_terminal():
    subprocess.Popen(["cmd.exe"])

def open_chrome():
    subprocess.Popen(["start", "chrome"], shell=True)

def open_browser():
    import webbrowser
    webbrowser.open("https://google.com")

def open_notepad():
    subprocess.Popen(["notepad.exe"])

def open_explorer():
    subprocess.Popen(["explorer.exe"])