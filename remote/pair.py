"""
Desktop pairing helper.

    python -m remote.pair

Generates a fresh single-use pairing code and prints it with a QR code the
ARC mobile app can scan. The running daemon picks the code up from disk, so no
network endpoint ever exposes it.

Environment:
  ARC_PUBLIC_URL  URL the phone should use (e.g. https://my-mac.tailnet.ts.net).
                  Defaults to http://<LAN IP>:<ARC_PORT or 8000>.
"""

import os
import socket
from urllib.parse import quote

from remote.auth import generate_pairing_code


def _lan_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


def public_url() -> str:
    url = os.getenv("ARC_PUBLIC_URL")
    if url:
        return url.rstrip("/")
    return f"http://{_lan_ip()}:{os.getenv('ARC_PORT', '8000')}"


def pairing_uri(url: str, code: str) -> str:
    return f"arc://pair?u={quote(url, safe='')}&c={code}"


def announce_pairing(code: str = None) -> str:
    code = code or generate_pairing_code(announce=False)
    url = public_url()
    uri = pairing_uri(url, code)
    print("\n" + "=" * 52)
    print("  ARC Remote pairing")
    print("=" * 52)
    print(f"  Server : {url}")
    print(f"  Code   : {code}   (single use, expires in 5 min)")
    try:
        import qrcode
        qr = qrcode.QRCode(border=1)
        qr.add_data(uri)
        qr.make(fit=True)
        print("\n  Scan with the ARC app:\n")
        qr.print_ascii(invert=True)
    except ImportError:
        print(f"\n  (pip install qrcode for a QR)  Pair link: {uri}")
    print("=" * 52 + "\n")
    return code


if __name__ == "__main__":
    announce_pairing()
