import subprocess
import os
import re
from core.voice_response import speak

def volume_up(amount: int = 10) -> None:
    # Uses nircmd if available, else PowerShell
    try:
        subprocess.Popen(["nircmd.exe", "changesysvolume", str(amount * 655)])
    except:
        # PowerShell fallback
        steps = amount // 2
        for _ in range(steps):
            subprocess.Popen(["powershell", "-c",
                "$obj = New-Object -ComObject WScript.Shell; $obj.SendKeys([char]175)"])
    print(f"🔊 Volume +{amount}")

def volume_down(amount: int = 10) -> None:
    try:
        subprocess.Popen(["nircmd.exe", "changesysvolume", str(-amount * 655)])
    except:
        steps = amount // 2
        for _ in range(steps):
            subprocess.Popen(["powershell", "-c",
                "$obj = New-Object -ComObject WScript.Shell; $obj.SendKeys([char]174)"])
    print(f"🔊 Volume -{amount}")

def mute() -> None:
    subprocess.Popen(["powershell", "-c",
        "$obj = New-Object -ComObject WScript.Shell; $obj.SendKeys([char]173)"])
    print("🔇 Muted")

def unmute() -> None:
    mute()  # Toggle
    print("🔊 Unmuted")

def get_volume() -> None:
    speak("Volume control on Windows.")

def brightness_up() -> None:
    subprocess.Popen(["powershell", "-c",
        "(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods).WmiSetBrightness(1,80)"])
    print("☀️ Brightness up")

def brightness_down() -> None:
    subprocess.Popen(["powershell", "-c",
        "(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods).WmiSetBrightness(1,40)"])
    print("🌑 Brightness down")

def take_screenshot() -> None:
    import datetime
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path = os.path.expanduser(f"~/Desktop/screenshot_{timestamp}.png")
    subprocess.Popen(["powershell", "-c",
        f"Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.Screen]::PrimaryScreen | Out-Null; $bitmap = [System.Drawing.Bitmap]::new([System.Windows.Forms.SystemInformation]::VirtualScreen.Width, [System.Windows.Forms.SystemInformation]::VirtualScreen.Height); $graphics = [System.Drawing.Graphics]::FromImage($bitmap); $graphics.CopyFromScreen([System.Windows.Forms.SystemInformation]::VirtualScreen.Location, [System.Drawing.Point]::Empty, [System.Windows.Forms.SystemInformation]::VirtualScreen.Size); $bitmap.Save('{path}')"])
    print(f"📸 Screenshot saved: {path}")

def minimise_all() -> None:
    subprocess.Popen(["powershell", "-c",
        "$shell = New-Object -ComObject Shell.Application; $shell.MinimizeAll()"])
    print("🔽 Minimised all")

def minimise_app(app_name: str) -> None:
    import pygetwindow as gw
    try:
        app_map = {
            "vscode": "Visual Studio Code",
            "chrome": "Google Chrome",
            "terminal": "Command Prompt",
        }
        title = app_map.get(app_name.lower(), app_name)
        windows = gw.getWindowsWithTitle(title)
        if windows:
            windows[0].minimize()
    except:
        print(f"❌ Could not minimise {app_name}")
    print(f"🔽 Minimised: {app_name}")

def show_desktop() -> None:
    minimise_all()

def close_window() -> None:
    import pyautogui
    pyautogui.hotkey('alt', 'f4')

def close_tab() -> None:
    import pyautogui
    pyautogui.hotkey('ctrl', 'w')

def new_tab() -> None:
    import pyautogui
    pyautogui.hotkey('ctrl', 't')

def fullscreen() -> None:
    import pyautogui
    pyautogui.press('f11')

def mission_control() -> None:
    import pyautogui
    pyautogui.hotkey('win', 'tab')

def close_app(app_name: str) -> None:
    app_map = {
        "chrome":   "chrome.exe",
        "vscode":   "Code.exe",
        "terminal": "cmd.exe",
    }
    exe = app_map.get(app_name.lower(), app_name)
    subprocess.Popen(["taskkill", "/f", "/im", exe])
    print(f"❌ Closed: {exe}")

def switch_to_app(app_name: str) -> None:
    import pygetwindow as gw
    try:
        app_map = {
            "vscode": "Visual Studio Code",
            "chrome": "Google Chrome",
        }
        title = app_map.get(app_name.lower(), app_name)
        windows = gw.getWindowsWithTitle(title)
        if windows:
            windows[0].activate()
    except Exception as e:
        print(f"❌ Could not switch: {e}")

def get_battery() -> None:
    result = subprocess.run(
        ["powershell", "-c", "Get-WmiObject Win32_Battery | Select-Object EstimatedChargeRemaining"],
        capture_output=True, text=True
    )
    match = re.search(r'\d+', result.stdout)
    if match:
        percent = match.group()
        speak(f"Battery is at {percent} percent.")
        print(f"🔋 Battery: {percent}%")
    else:
        speak("Couldn't read battery level.")

def start_work_day() -> None:
    speak("Starting your work day.")
    subprocess.Popen(["code"], shell=True)
    subprocess.Popen(["cmd.exe"])
    import webbrowser
    webbrowser.open("https://google.com")

def end_work_day() -> None:
    speak("Ending your work day. Good work today.")
    import ctypes
    ctypes.windll.user32.LockWorkStation()