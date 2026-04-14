import sys

if sys.platform == "darwin":
    from control.mac.open_apps import open_vscode, open_safari, open_terminal, open_any_app
    from control.mac.system_actions import lock_screen, shutdown_pc, restart_pc, sleep_mac
    from control.mac.system_controls import (
        volume_up, volume_down, mute, unmute, get_volume,
        brightness_up, brightness_down, take_screenshot,
        minimise_all, minimise_app, show_desktop, close_window,
        get_battery, start_work_day, end_work_day,
        close_app, switch_to_app, fullscreen, mission_control,
        close_tab, new_tab
    )
    from control.mac.folder_control import open_folder, create_folder, search_file
    from control.mac.briefing import morning_briefing
    from control.mac.weather import tell_weather
    from control.mac.file_ops import (
        read_file, create_file, delete_file,
        rename_file, get_recent_files, copy_file, edit_file
    )

elif sys.platform == "win32":
    from control.windows.open_apps import open_vscode, open_safari, open_terminal, open_any_app
    from control.windows.system_actions import lock_screen, shutdown_pc, restart_pc, sleep_mac
    from control.windows.system_controls import (
        volume_up, volume_down, mute, unmute, get_volume,
        brightness_up, brightness_down, take_screenshot,
        minimise_all, minimise_app, show_desktop, close_window,
        get_battery, start_work_day, end_work_day,
        close_app, switch_to_app, fullscreen, mission_control,
        close_tab, new_tab
    )
    from control.windows.folder_control import open_folder, create_folder, search_file
    from control.windows.briefing import morning_briefing
    from control.windows.weather import tell_weather
    from control.windows.file_ops import (
        read_file, create_file, delete_file,
        rename_file, get_recent_files, copy_file, edit_file
    )

# These are same on all platforms
from control.web_search import search_google
from control.time_utils import tell_time, tell_date
from control.email_control import read_emails, search_emails, send_email, open_gmail
from control.pdf_summariser import summarise_latest_pdf