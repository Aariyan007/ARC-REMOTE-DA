import time
from remote.db import get_db


def log_audit_event(job_id: str, device: str, action: str, details: str):
    """
    Record security-relevant events: commands, results, pairing, revocation, auth failures.
    """
    conn = get_db()
    with conn:
        conn.execute(
            "INSERT INTO audit_log (job_id, device, action, details, timestamp) VALUES (?, ?, ?, ?, ?)",
            (job_id, device, action, (details or "")[:2000], time.time()),
        )
