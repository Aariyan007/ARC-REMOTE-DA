"""
Pairing + device-token auth for the ARC remote daemon.

- The signing key is persisted (env ARC_SECRET_KEY, else data/.secret) so paired
  devices survive restarts.
- Pairing codes are single-use, short-lived, compared in constant time and
  protected by a failure lockout.
- Access tokens are HMAC-signed, carry a device id (`jti`) and are checked
  against the device registry (see remote.db) so they can be revoked.
- WebSocket clients exchange a bearer token for a short-lived one-time ticket
  so tokens never appear in URLs / proxy logs.
"""

import os
import time
import secrets
import json
import base64
import hmac
import hashlib
import threading
from typing import Optional

_DATA_DIR = os.getenv("ARC_DATA_DIR") or os.path.join(os.path.dirname(__file__), "..", "data")

TOKEN_TTL_SECONDS = 60 * 60 * 24 * 30
PAIRING_CODE_TTL = 300
MAX_PAIR_FAILURES = int(os.getenv("ARC_MAX_PAIR_FAILURES", "5"))
PAIR_LOCKOUT_SECONDS = int(os.getenv("ARC_PAIR_LOCKOUT_SECONDS", str(15 * 60)))
WS_TICKET_TTL = 30


def _load_secret_key() -> str:
    env = os.getenv("ARC_SECRET_KEY")
    if env:
        return env
    path = os.path.abspath(os.path.join(_DATA_DIR, ".secret"))
    try:
        with open(path, "r", encoding="utf-8") as f:
            key = f.read().strip()
            if key:
                return key
    except FileNotFoundError:
        pass
    key = secrets.token_hex(32)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(key)
    return key


SECRET_KEY = _load_secret_key()

_lock = threading.Lock()
# client key (ip) -> [failure_count, locked_until]
_failures: dict = {}
# ticket -> (device_id, device_name, expiry)
_ws_tickets: dict = {}


def _pairing_path() -> str:
    return os.path.abspath(os.path.join(_DATA_DIR, ".pairing_code.json"))


def _write_pairing(code: Optional[str], expiry: float = 0.0) -> None:
    path = _pairing_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if code is None:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
        return
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump({"code": code, "expires": expiry}, f)


def _read_pairing() -> tuple:
    try:
        with open(_pairing_path(), "r", encoding="utf-8") as f:
            d = json.load(f)
        return d.get("code"), float(d.get("expires", 0))
    except Exception:
        return None, 0.0


def generate_pairing_code(announce: bool = True) -> str:
    """Create a fresh single-use code. It lives in a 0600 file under data/ so
    the desktop CLI (`python -m remote.pair`) and the daemon share it; it is
    never exposed over HTTP."""
    code = "".join(str(secrets.randbelow(10)) for _ in range(6))
    with _lock:
        _write_pairing(code, time.time() + PAIRING_CODE_TTL)
    if announce:
        print(f"\n[ARC SECURITY] New pairing code: {code}")
        print("[ARC SECURITY] Enter it on your phone within 5 minutes.\n")
    return code


def is_locked_out(client: str) -> int:
    """Return seconds remaining on a lockout for `client`, or 0."""
    with _lock:
        entry = _failures.get(client)
        if not entry:
            return 0
        remaining = entry[1] - time.time()
        if remaining > 0:
            return int(remaining) + 1
        if entry[1]:
            _failures.pop(client, None)
        return 0


def verify_pairing_code(code: str, client: str = "unknown") -> bool:
    """Constant-time check. Consumes the code on success; counts failures."""
    with _lock:
        current, expiry = _read_pairing()
        if not current or time.time() > expiry:
            ok = False
            if current:
                _write_pairing(None)
        else:
            ok = hmac.compare_digest(str(code or ""), current)
        if ok:
            _write_pairing(None)
            _failures.pop(client, None)
            return True
        entry = _failures.setdefault(client, [0, 0.0])
        entry[0] += 1
        if entry[0] >= MAX_PAIR_FAILURES:
            entry[1] = time.time() + PAIR_LOCKOUT_SECONDS
            entry[0] = 0
            # Burn the current code so a brute-forcer can't keep guessing it.
            _write_pairing(None)
        return False


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")


def _b64url_decode(value: str) -> bytes:
    padding = "=" * ((4 - (len(value) % 4)) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _sign(payload_bytes: bytes) -> str:
    digest = hmac.new(SECRET_KEY.encode("utf-8"), payload_bytes, hashlib.sha256).digest()
    return _b64url_encode(digest)


def create_access_token(device_name: str, device_id: Optional[str] = None) -> str:
    now = time.time()
    payload = {
        "sub": "arc_user",
        "device": device_name,
        "jti": device_id or secrets.token_hex(8),
        "iat": now,
        "exp": now + TOKEN_TTL_SECONDS,
    }
    payload_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return f"{_b64url_encode(payload_bytes)}.{_sign(payload_bytes)}"


def verify_access_token(token: str) -> Optional[dict]:
    try:
        payload_part, sig_part = token.split(".", 1)
        payload_bytes = _b64url_decode(payload_part)
        if not hmac.compare_digest(_sign(payload_bytes), sig_part):
            return None
        payload = json.loads(payload_bytes.decode("utf-8"))
        exp = payload.get("exp")
        if not exp or time.time() > float(exp):
            return None
        return payload
    except Exception:
        return None


def issue_ws_ticket(device_id: str, device_name: str) -> str:
    ticket = secrets.token_urlsafe(24)
    now = time.time()
    with _lock:
        for t in [t for t, v in _ws_tickets.items() if v[2] < now]:
            _ws_tickets.pop(t, None)
        _ws_tickets[ticket] = (device_id, device_name, now + WS_TICKET_TTL)
    return ticket


def redeem_ws_ticket(ticket: str) -> Optional[tuple]:
    """One-time use. Returns (device_id, device_name) or None."""
    with _lock:
        entry = _ws_tickets.pop(ticket or "", None)
    if not entry or entry[2] < time.time():
        return None
    return entry[0], entry[1]
