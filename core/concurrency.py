"""
Concurrency Control — ensures actions, speech, and background
tasks don't overlap or conflict.

Components:
- ActionExecutor:  Thread pool for running actions in background
- SpeechQueue:     Ensures only one speech at a time
- CommandLock:     Prevents overlapping command execution
"""

import threading
import queue
from concurrent.futures import ThreadPoolExecutor, Future
from typing import Callable, Any, Optional


# ─── Command Lock ────────────────────────────────────────────
# Prevents two commands from executing simultaneously.
_command_lock = threading.Lock()
_is_processing = threading.Event()


def acquire_command() -> bool:
    """Try to acquire command processing lock. Returns False if already processing."""
    acquired = _command_lock.acquire(blocking=False)
    if acquired:
        _is_processing.set()
    return acquired


def release_command() -> None:
    """Release command processing lock."""
    _is_processing.clear()
    try:
        _command_lock.release()
    except RuntimeError:
        pass  # Already released


def is_processing() -> bool:
    """Check if a command is currently being processed."""
    return _is_processing.is_set()


# ─── Action Executor ─────────────────────────────────────────
# Thread pool for running actions without blocking the main loop.
_executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="jarvis_action")


def run_action_async(func: Callable, *args, **kwargs) -> Future:
    """
    Runs an action function in a background thread.
    Returns a Future that can be checked for completion.

    Usage:
        future = run_action_async(open_vscode)
        # ... do other stuff ...
        result = future.result()  # blocks until done
    """
    return _executor.submit(func, *args, **kwargs)


def run_action_sync(func: Callable, *args, timeout: float = 10.0, **kwargs) -> Any:
    """
    Runs an action and waits for it, with timeout.
    Returns the result, or None if timed out.
    """
    future = _executor.submit(func, *args, **kwargs)
    try:
        return future.result(timeout=timeout)
    except Exception as e:
        print(f"⚠️ Action error: {e}")
        return None


# ─── Speech Queue ────────────────────────────────────────────
# Ensures only one speech at a time, queues follow-ups.
_speech_queue: queue.Queue = queue.Queue()
_speech_lock  = threading.Lock()
_speech_thread: Optional[threading.Thread] = None


def _speech_worker():
    """Background worker that processes speech queue."""
    while True:
        try:
            item = _speech_queue.get(timeout=1.0)
            if item is None:  # Poison pill
                break

            text, speak_func, use_elevenlabs = item
            with _speech_lock:
                speak_func(text, use_elevenlabs)
            _speech_queue.task_done()
        except queue.Empty:
            continue
        except Exception as e:
            print(f"⚠️ Speech worker error: {e}")


def start_speech_worker():
    """Start the background speech worker thread."""
    global _speech_thread
    if _speech_thread is None or not _speech_thread.is_alive():
        _speech_thread = threading.Thread(target=_speech_worker, daemon=True, name="jarvis_speech")
        _speech_thread.start()


def queue_speech(text: str, speak_func: Callable, use_elevenlabs: bool = False):
    """
    Queue a speech item. Will be spoken when previous speeches complete.
    """
    _speech_queue.put((text, speak_func, use_elevenlabs))


def clear_speech_queue():
    """Clear all pending speech items."""
    while not _speech_queue.empty():
        try:
            _speech_queue.get_nowait()
        except queue.Empty:
            break


def is_speech_queued() -> bool:
    """Check if there are pending speeches in the queue."""
    return not _speech_queue.empty()


# ─── Background Task Runner ─────────────────────────────────
# For optional background Gemini calls and other non-blocking work.
_bg_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="jarvis_bg")


def run_background(func: Callable, *args, **kwargs) -> Future:
    """
    Runs a function in background without blocking.
    Used for optional Gemini enhancement calls.
    """
    return _bg_executor.submit(func, *args, **kwargs)


# ─── Cleanup ─────────────────────────────────────────────────
def shutdown():
    """Cleanly shut down all thread pools."""
    clear_speech_queue()
    _speech_queue.put(None)  # Poison pill for speech worker
    _executor.shutdown(wait=False)
    _bg_executor.shutdown(wait=False)
    print("🔄 Concurrency pools shut down")


# ─── Quick test ──────────────────────────────────────────────
if __name__ == "__main__":
    import time

    print("=" * 60)
    print("  CONCURRENCY CONTROL TEST")
    print("=" * 60)

    # Test command lock
    print("\n── Command Lock ──")
    assert acquire_command() == True
    assert acquire_command() == False  # Already locked
    assert is_processing() == True
    release_command()
    assert is_processing() == False
    print("  ✅ Command lock works")

    # Test async action
    print("\n── Async Action ──")
    def slow_action():
        time.sleep(0.5)
        return "done"

    future = run_action_async(slow_action)
    print(f"  Action submitted, done={future.done()}")
    result = future.result(timeout=2.0)
    print(f"  Action result: {result}")
    print("  ✅ Async action works")

    # Test background task
    print("\n── Background Task ──")
    def bg_task():
        time.sleep(0.3)
        return "bg_result"

    bg_future = run_background(bg_task)
    print(f"  Background task submitted")
    bg_result = bg_future.result(timeout=2.0)
    print(f"  Background result: {bg_result}")
    print("  ✅ Background task works")

    shutdown()
    print("\n✅ All tests passed")
