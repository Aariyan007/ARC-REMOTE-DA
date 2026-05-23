import os
import sqlite3
import json
import threading
import atexit

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "remote.db")

_local = threading.local()
# Track all open connections so atexit can close them
_all_conns: list = []
_all_conns_lock = threading.Lock()

def get_db():
    if not hasattr(_local, "conn"):
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        _init_db(conn)
        _local.conn = conn
        # BUG-M FIX: track every connection so we can close them on exit.
        # Thread-local connections are never auto-closed when a thread dies or
        # the process exits, causing a resource leak in long-running servers.
        with _all_conns_lock:
            _all_conns.append(conn)
    return _local.conn

@atexit.register
def _close_all_db_connections():
    """Close every SQLite connection registered from any thread."""
    with _all_conns_lock:
        for conn in _all_conns:
            try:
                conn.close()
            except Exception:
                pass
        _all_conns.clear()

def _init_db(conn):
    with conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                command TEXT,
                source TEXT,
                user TEXT,
                status TEXT,
                created_at REAL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS job_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT,
                type TEXT,
                message TEXT,
                data TEXT,
                timestamp REAL,
                FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE
            )
        """)

def save_job(job_id: str, command: str = "", source: str = "", user: str = "", status: str = "created", created_at: float = 0.0):
    conn = get_db()
    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO jobs (id, command, source, user, status, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (job_id, command, source, user, status, created_at)
        )

def save_job_event(job_id: str, event_type: str, message: str, data: dict, timestamp: float):
    conn = get_db()
    with conn:
        conn.execute(
            "INSERT INTO job_events (job_id, type, message, data, timestamp) VALUES (?, ?, ?, ?, ?)",
            # BUG 19 FIX: data can be None if passed explicitly; json.dumps(None) = "null"
            # which frontend parses as null (not {}), breaking event.data || {} fallback.
            (job_id, event_type, message, json.dumps(data or {}), timestamp)
        )


def get_recent_commands(user: str, limit: int = 5) -> list[dict]:
    """
    Returns the last `limit` distinct commands run by a device/user.
    Excludes empty commands and health-check noise.
    """
    conn = get_db()
    try:
        rows = conn.execute(
            """
            SELECT command, MAX(created_at) AS ts
            FROM jobs
            WHERE user = ?
              AND command IS NOT NULL
              AND command != ''
              AND command NOT LIKE '%health%'
            GROUP BY command
            ORDER BY ts DESC
            LIMIT ?
            """,
            (user, limit),
        ).fetchall()
        return [{"command": r["command"], "timestamp": r["ts"]} for r in rows]
    except Exception:
        return []

