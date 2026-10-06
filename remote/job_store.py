import secrets
import threading
import time
from typing import Dict, List, Optional, Any

from remote.db import save_job_event

TERMINAL_TYPES = ("result", "error")
ASK_TIMEOUT = 120.0
# Finished jobs stay in memory this long (history is always in SQLite).
JOB_RETENTION_SECONDS = 3600


class JobEvent:
    def __init__(self, type: str, message: str, data: dict = None):
        self.type = type       # "ack", "clarify", "confirm", "executing", "verify", "result", "error", "progress"
        self.message = message
        self.data = data or {}
        self.timestamp = time.time()

    def to_dict(self):
        return {
            "type": self.type,
            "message": self.message,
            "data": self.data,
            "timestamp": self.timestamp,
        }


class JobState:
    def __init__(self, job_id: str, device: str = ""):
        self.job_id = job_id
        self.device = device
        self.events: List[JobEvent] = []
        self.finished = False
        self.finished_at = 0.0
        self.cancelled = False
        self.lock = threading.Lock()

        # Condition variable for streaming events
        self.new_event_cond = threading.Condition(self.lock)

        # Reply hand-off: only accepted while a prompt is pending, so a stale
        # or early reply can never answer a later prompt.
        self._reply_cond = threading.Condition(threading.Lock())
        self._waiting = False
        self._reply_data: Any = None
        self._reply_ready = False
        self.pending_nonce: Optional[str] = None

        # General purpose per-job memory for multi-step workflows
        self.memory: Dict[str, Any] = {}

    def add_event(self, event: JobEvent) -> bool:
        """Append an event. Ignored (False) once the job is finished."""
        with self.new_event_cond:
            if self.finished:
                return False
            self.events.append(event)
            if event.type in TERMINAL_TYPES:
                self.finished = True
                self.finished_at = time.time()
            self.new_event_cond.notify_all()
        # Persist outside the lock so slow disk never blocks stream readers.
        try:
            save_job_event(self.job_id, event.type, event.message, event.data, event.timestamp)
        except Exception as e:
            print(f"Warning: could not persist job event: {e}")
        if event.type in TERMINAL_TYPES:
            self.release_waiter()
        return True

    def is_waiting(self) -> bool:
        with self._reply_cond:
            return self._waiting

    def set_reply(self, data: Any, nonce: Optional[str] = None) -> bool:
        """Deliver a reply to the pending prompt. False if nothing is waiting
        or the nonce doesn't match the pending prompt."""
        with self._reply_cond:
            if not self._waiting:
                return False
            if nonce is not None and nonce != self.pending_nonce:
                return False
            self._reply_data = data
            self._reply_ready = True
            self._reply_cond.notify_all()
            return True

    def begin_wait(self) -> str:
        nonce = secrets.token_hex(8)
        with self._reply_cond:
            self._waiting = True
            self._reply_ready = False
            self._reply_data = None
            self.pending_nonce = nonce
        return nonce

    def wait_for_reply(self, timeout: float = 60.0) -> Any:
        deadline = time.time() + timeout
        with self._reply_cond:
            while not self._reply_ready:
                remaining = deadline - time.time()
                if remaining <= 0:
                    break
                self._reply_cond.wait(remaining)
            data = self._reply_data if self._reply_ready else None
            self._waiting = False
            self._reply_ready = False
            self._reply_data = None
            self.pending_nonce = None
            return data

    def release_waiter(self):
        """Unblock a pending prompt with no answer (cancel / timeout / finish)."""
        with self._reply_cond:
            self._reply_ready = True
            self._reply_data = None
            self._reply_cond.notify_all()


class JobStore:
    def __init__(self):
        self._jobs: Dict[str, JobState] = {}
        self._lock = threading.Lock()

    def _evict_locked(self):
        cutoff = time.time() - JOB_RETENTION_SECONDS
        stale = [jid for jid, j in self._jobs.items() if j.finished and j.finished_at < cutoff]
        for jid in stale:
            self._jobs.pop(jid, None)

    def get_or_create(self, job_id: str, device: str = "") -> JobState:
        with self._lock:
            self._evict_locked()
            if job_id not in self._jobs:
                self._jobs[job_id] = JobState(job_id, device)
            return self._jobs[job_id]

    def create(self, job_id: str, command: str = "", source: str = "", device: str = "") -> JobState:
        """Create a job and persist its row (used by non-HTTP producers)."""
        from remote.db import save_job
        job = self.get_or_create(job_id, device)
        save_job(job_id, command=command, source=source, user=device, status="created", created_at=time.time())
        return job

    def get(self, job_id: str) -> Optional[JobState]:
        with self._lock:
            return self._jobs.get(job_id)

    def running_count(self, device: str = None) -> int:
        with self._lock:
            return sum(
                1 for j in self._jobs.values()
                if not j.finished and (device is None or j.device == device)
            )


_job_store = JobStore()


def get_job_store() -> JobStore:
    return _job_store


def ask_user(job_id: str, prompt: str, event_type: str = "clarify", data: dict = None) -> str:
    """
    Emit a clarify/confirm event to the job stream and block until the user replies.
    The event carries a `nonce` the client echoes back so a reply can only
    answer the prompt it was shown for.
    """
    job = get_job_store().get(job_id)
    if not job or job.finished:
        return ""

    nonce = job.begin_wait()
    payload = dict(data or {})
    payload["nonce"] = nonce
    payload["expires_at"] = time.time() + ASK_TIMEOUT
    job.add_event(JobEvent(event_type, prompt, data=payload))
    reply = job.wait_for_reply(timeout=ASK_TIMEOUT)
    return reply or ""
