import time
from remote.db import get_db

def log_audit_event(job_id: str, device: str, action: str, details: str):
    """
    Logs every remote command execution for security auditing.
    """
    conn = get_db()
    with conn:
        # Create table if it doesn't exist
        conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT,
                device TEXT,
                action TEXT,
                details TEXT,
                timestamp REAL
            )
        """)
        conn.execute(
            "INSERT INTO audit_log (job_id, device, action, details, timestamp) VALUES (?, ?, ?, ?, ?)",
            (job_id, device, action, details, time.time())
        )
