import threading
import time
from typing import Dict, List, Optional, Any
from remote.db import save_job_event, save_job

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
            "timestamp": self.timestamp
        }

class JobState:
    def __init__(self, job_id: str):
        self.job_id = job_id
        self.events: List[JobEvent] = []
        self.lock = threading.Lock()
        
        # Condition variable for streaming events
        self.new_event_cond = threading.Condition(self.lock)
        
        # Event for blocking the runtime thread until user replies
        self.reply_event = threading.Event()
        self.reply_data: Any = None
        
        # General purpose per-job memory for multi-step workflows
        self.memory: Dict[str, Any] = {}

    def add_event(self, event: JobEvent):
        with self.new_event_cond:
            self.events.append(event)
            # Persist to SQLite
            save_job_event(self.job_id, event.type, event.message, event.data, event.timestamp)
            self.new_event_cond.notify_all()

    def set_reply(self, data: Any):
        self.reply_data = data
        self.reply_event.set()

    def wait_for_reply(self, timeout: float = 60.0) -> Any:
        self.reply_event.wait(timeout)
        self.reply_event.clear()
        data = self.reply_data
        self.reply_data = None
        return data


class JobStore:
    def __init__(self):
        self._jobs: Dict[str, JobState] = {}
        self._lock = threading.Lock()

    def get_or_create(self, job_id: str) -> JobState:
        with self._lock:
            if job_id not in self._jobs:
                self._jobs[job_id] = JobState(job_id)
            return self._jobs[job_id]

    def get(self, job_id: str) -> Optional[JobState]:
        with self._lock:
            return self._jobs.get(job_id)

_job_store = JobStore()

def get_job_store() -> JobStore:
    return _job_store

def ask_user(job_id: str, prompt: str, event_type: str = "clarify", data: dict = None) -> str:
    """
    Emit a clarify/confirm event to the job stream and block until the user replies.
    """
    store = get_job_store()
    job = store.get(job_id)
    if not job:
        return ""
    
    job.add_event(JobEvent(event_type, prompt, data=data))
    reply = job.wait_for_reply(timeout=120.0)
    return reply or ""
