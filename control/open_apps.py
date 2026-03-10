import subprocess


def open_vscode():
    """Opens Visual Studio Code."""
    print("🖥️  Opening VS Code...")
    subprocess.Popen(["open", "-a", "Visual Studio Code"])


def open_safari():
    """Opens Safari browser."""
    print("🌐  Opening Safari...")
    subprocess.Popen(["open", "-a", "Safari"])


def open_terminal():
    """Opens Terminal."""
    print("💻  Opening Terminal...")
    subprocess.Popen(["open", "-a", "Terminal"])


# ─── Quick test ──────────────────────────────────────────────
# Run: python3 control/open_apps.py
if __name__ == "__main__":
    import time

    print("Testing open_apps.py...")
    print("-" * 30)

    print("1. Opening VS Code in 2 seconds...")
    time.sleep(2)
    open_vscode()

    print("2. Opening Safari in 2 seconds...")
    time.sleep(2)
    open_safari()

    print("3. Opening Terminal in 2 seconds...")
    time.sleep(2)
    open_terminal()

    print("\n✅ All apps launched!")