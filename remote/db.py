import os
import sqlite3
import json
import threading

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "remote.db")

_local = threading.local()

def get_db():
    if not hasattr(_local, "conn"):
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        # Check if same thread
        _local.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _local.conn.row_factory = sqlite3.Row
        _init_db(_local.conn)
    return _local.conn

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
            (job_id, event_type, message, json.dumps(data), timestamp)
        )
