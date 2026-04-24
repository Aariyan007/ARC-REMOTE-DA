import os
import time
import secrets
import json
import base64
import hmac
import hashlib
from typing import Optional

SECRET_KEY = os.getenv("ARC_SECRET_KEY", secrets.token_hex(32))

# For LAN pairing, generate a simple 6-digit code
# In production, this might be displayed on the desktop UI
_current_pairing_code = None
_pairing_code_expiry = 0

def generate_pairing_code() -> str:
    global _current_pairing_code, _pairing_code_expiry
    # 6-digit code
    _current_pairing_code = "".join([str(secrets.randbelow(10)) for _ in range(6)])
    _pairing_code_expiry = time.time() + 300  # valid for 5 mins
    print(f"\n[ARC SECURITY] New pairing code generated: {_current_pairing_code}")
    print("[ARC SECURITY] Enter this code on your mobile device within 5 minutes.\n")
    return _current_pairing_code

def verify_pairing_code(code: str) -> bool:
    global _current_pairing_code
    if not _current_pairing_code:
        return False
    if time.time() > _pairing_code_expiry:
        _current_pairing_code = None
        return False
    
    if code == _current_pairing_code:
        _current_pairing_code = None  # consume the code
        return True
    return False

def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")


def _b64url_decode(value: str) -> bytes:
    padding = "=" * ((4 - (len(value) % 4)) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _sign(payload_bytes: bytes) -> str:
    digest = hmac.new(SECRET_KEY.encode("utf-8"), payload_bytes, hashlib.sha256).digest()
    return _b64url_encode(digest)


def create_access_token(device_name: str) -> str:
    payload = {
        "sub": "arc_user",
        "device": device_name,
        "iat": time.time(),
        "exp": time.time() + (60 * 60 * 24 * 30),
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
        if exp and time.time() > float(exp):
            return None
        return payload
    except Exception:
        return None
