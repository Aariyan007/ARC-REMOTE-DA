"""
Jarvis — Voice entry point (thin wrapper over core.runtime).

This file handles ONLY:
  - SpeechBrain lazy-module patch
  - Wake-word loop
  - Voice assistant loop

All initialization and execution logic lives in core/runtime.py.
"""

import os
import sys

# Ensure running in venv
VENV_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "venv"))
if sys.prefix != VENV_PATH:
    python_exe = os.path.join(VENV_PATH, "bin", "python")
    if os.path.exists(python_exe):
        os.execv(python_exe, [python_exe] + sys.argv)
    else:
        print("Error: venv not found. Please create it first.", file=sys.stderr)
        sys.exit(1)

# ── Fix speechbrain lazy module crashes ──────────────────────
try:
    import speechbrain.utils.importutils as _sb_importutils
    _OrigLazyModule = _sb_importutils.LazyModule

    _orig_ensure = _OrigLazyModule.ensure_module
    def _safe_ensure(self, *args, **kwargs):
        try:
            return _orig_ensure(self, *args, **kwargs)
        except (ImportError, Exception):
            import types
            target_name = getattr(self, 'target', 'unknown')
            dummy = types.ModuleType(target_name)
            dummy.__file__ = target_name.replace('.', '/') + '.py'
            dummy.__path__ = []
            dummy.__package__ = target_name
            self.lazy_module = dummy
            return dummy
    _OrigLazyModule.ensure_module = _safe_ensure

    _orig_getattr = _OrigLazyModule.__getattr__
    def _safe_getattr(self, attr):
        if attr == '__file__':
            try:
                mod = self.ensure_module(1)
                f = getattr(mod, '__file__', None)
                if f is not None:
                    return f
            except Exception:
                pass
            target = getattr(self, 'target', 'unknown')
            return target.replace('.', '/') + '.py'
        return _orig_getattr(self, attr)
    _OrigLazyModule.__getattr__ = _safe_getattr
except Exception:
    pass
# ─────────────────────────────────────────────────────────────

import warnings
os.environ["TORCHCODEC_DISABLE_LOAD"] = "1"
if sys.platform == "darwin":
    os.environ["PATH"] = "/opt/homebrew/bin:" + os.environ.get("PATH", "")
warnings.filterwarnings("ignore", message=".*torchcodec.*")
warnings.filterwarnings("ignore", message=".*FFmpeg.*")
warnings.filterwarnings("ignore", category=UserWarning)

try:
    import pkg_resources
except ImportError:
    class _MockDistribution:
        def __init__(self, version='2.0.10'):
            self.version = version
    class _MockPkgResources:
        def get_distribution(self, name):
            return _MockDistribution()
    sys.modules['pkg_resources'] = _MockPkgResources()

try:
    import dotenv
    dotenv.load_dotenv()
except ImportError:
    pass

# ─── Runtime ──────────────────────────────────────────────────
import core.runtime as runtime


def assistant_loop():
    """Single activation cycle: listen until 'goodbye'."""
    from core.voice_response import speak, speak_and_wait
    from core.speech_to_text import listen
    from core.logger import print_todays_summary
    from core.memory import clear_conversation
    from core.reinforcement import is_correction, handle_correction

    speak("Activated Sir")
    print("\n✅ Jarvis activated — listening for your command...")

    # Daily greeting (background, won't freeze the mic)
    try:
        from core.daily_greeting import should_greet, daily_greeting
        if should_greet():
            import threading
            threading.Thread(target=daily_greeting, daemon=True).start()
    except Exception:
        pass

    while True:
        command = listen()
        if not command:
            print("⚠️  Didn't catch that. Try again.")
            continue

        if any(word in command for word in ["goodbye", "go to sleep", "stop listening"]):
            clear_conversation()
            print_todays_summary()
            speak_and_wait("Going to sleep. Goodbye.")
            print("😴 Jarvis going to sleep...")
            break

        if is_correction(command):
            print("🔄 Correction detected — learning from mistake")
            result = handle_correction(command, runtime.ACTIONS)
            print(f"📚 Correction result: {result}")
            continue

        # ── All commands go through the canonical entry point ──
        response = runtime.execute_text_command(command, source="voice")
        if not response.status == "completed" and response.final_result:
            print(f"[Route] {response.status}: {response.final_result}")


def start_api_server_in_background():
    import subprocess
    import sys
    print("🌐 Starting background API server for remote phone commands (Port 8000)...")
    try:
        return subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "main_ui:app", "--host", "0.0.0.0", "--port", "8000"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
    except Exception as e:
        print(f"⚠️  Could not start background API server: {e}")
        return None



def main():
    if not runtime.boot(voice=True):
        return

    api_process = start_api_server_in_background()
    print("\nSay the wake word to activate Jarvis...\n")

    try:
        from core.listener import start_listener
    except ImportError as e:
        print(f"⚠️  Wake-word listener unavailable: {e}")
        return

    try:
        while True:
            activated = start_listener()
            if activated:
                assistant_loop()
                print("\nWaiting for wake word again...\n")
    except KeyboardInterrupt:
        print("\n⚠️  Shutting down...")
    finally:
        if api_process:
            try:
                api_process.terminate()
            except Exception:
                pass
    print("✅ Jarvis shut down.")


if __name__ == "__main__":
    main()
