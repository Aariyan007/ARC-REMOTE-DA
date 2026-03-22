import subprocess

def open_vscode():
    subprocess.Popen(["open", "-a", "Visual Studio Code"])

def open_safari():
    subprocess.Popen(["open", "-a", "Safari"])

def open_terminal():
    subprocess.Popen(["open", "-a", "Terminal"])
    
def open_settings():
    subprocess.Popen(["open", "-a", "System Preferences"])