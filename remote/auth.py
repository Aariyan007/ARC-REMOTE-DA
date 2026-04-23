import os
import jwt
import time
import secrets
from typing import Optional

SECRET_KEY = os.getenv("ARC_SECRET_KEY", secrets.token_hex(32))
ALGORITHM = "HS256"

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

def create_access_token(device_name: str) -> str:
    payload = {
        "sub": "arc_user",
        "device": device_name,
        "iat": time.time(),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def verify_access_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.PyJWTError:
        return None
