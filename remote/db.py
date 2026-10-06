import os
import sqlite3
import json
import threading
import atexit

DB_PATH = os.getenv("ARC_DB_PATH") or os.path.join(os.path.dirname(__file__), "..", "data", "remote.db")

_local = threading.local()
# Track all open connections so atexit can close them
_all_conns: list = []
_all_conns_lock = threading.Lock()

def get_db():
    if not hasattr(_local, "conn"):
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=10000")
        conn.execute("PRAGMA foreign_keys=ON")
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
        conn.execute("CREATE INDEX IF NOT EXISTS idx_job_events_job ON job_events(job_id, id)")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS devices (
                id TEXT PRIMARY KEY,
                name TEXT,
                created_at REAL,
                last_seen REAL,
                revoked INTEGER DEFAULT 0,
                push_token TEXT,
                push_platform TEXT
            )
        """)
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



# ── Jobs (history survives restarts) ─────────────────────────

def get_job(job_id: str):
    """Return {id, command, source, user, status, created_at} or None."""
    row = get_db().execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return dict(row) if row else None


def update_job_status(job_id: str, status: str):
    conn = get_db()
    with conn:
        conn.execute("UPDATE jobs SET status = ? WHERE id = ?", (status, job_id))


def get_job_events(job_id: str, since: int = 0) -> list[dict]:
    rows = get_db().execute(
        "SELECT type, message, data, timestamp FROM job_events WHERE job_id = ? ORDER BY id LIMIT -1 OFFSET ?",
        (job_id, max(0, since)),
    ).fetchall()
    out = []
    for r in rows:
        try:
            data = json.loads(r["data"]) if r["data"] else {}
        except Exception:
            data = {}
        out.append({"type": r["type"], "message": r["message"], "data": data, "timestamp": r["timestamp"]})
    return out


def prune_old_jobs(max_age_days: int = 30):
    import time
    cutoff = time.time() - max_age_days * 86400
    conn = get_db()
    with conn:
        conn.execute("DELETE FROM jobs WHERE created_at < ?", (cutoff,))
        conn.execute("DELETE FROM audit_log WHERE timestamp < ?", (cutoff,))


# ── Device registry ──────────────────────────────────────────

def register_device(device_id: str, name: str, now: float):
    conn = get_db()
    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO devices (id, name, created_at, last_seen, revoked) VALUES (?, ?, ?, ?, 0)",
            (device_id, name, now, now),
        )


def device_is_active(device_id: str) -> bool:
    row = get_db().execute("SELECT revoked FROM devices WHERE id = ?", (device_id,)).fetchone()
    return bool(row) and not row["revoked"]


def touch_device(device_id: str, now: float):
    conn = get_db()
    with conn:
        conn.execute("UPDATE devices SET last_seen = ? WHERE id = ?", (now, device_id))


def list_devices() -> list[dict]:
    rows = get_db().execute(
        "SELECT id, name, created_at, last_seen, revoked FROM devices ORDER BY created_at DESC"
    ).fetchall()
    return [dict(r) for r in rows]


def revoke_device(device_id: str) -> bool:
    conn = get_db()
    with conn:
        cur = conn.execute("UPDATE devices SET revoked = 1 WHERE id = ?", (device_id,))
    return cur.rowcount > 0


def set_push_token(device_id: str, token: str, platform: str):
    conn = get_db()
    with conn:
        conn.execute(
            "UPDATE devices SET push_token = ?, push_platform = ? WHERE id = ?",
            (token, platform, device_id),
        )


def list_jobs(user: str, limit: int = 20) -> list[dict]:
    rows = get_db().execute(
        "SELECT id, command, source, status, created_at FROM jobs WHERE user = ? ORDER BY created_at DESC LIMIT ?",
        (user, limit),
    ).fetchall()
    return [dict(r) for r in rows]
