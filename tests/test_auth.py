import time

from tests.conftest import pair, auth_header


def test_pairing_code_not_exposed_over_http(client):
    assert client.get("/pairing-code").status_code in (404, 405)
    assert client.post("/pairing-code").status_code in (404, 405)


def test_pair_success_and_code_single_use(client):
    code, _ = client.env.auth._read_pairing()
    r = client.post("/pair", json={"code": code, "device_name": "Pixel"})
    assert r.status_code == 200 and r.json()["token"]
    again = client.post("/pair", json={"code": code, "device_name": "Pixel"})
    assert again.status_code == 401


def test_bad_code_rejected_then_lockout(client):
    for _ in range(client.env.auth.MAX_PAIR_FAILURES):
        r = client.post("/pair", json={"code": "000000x", "device_name": "evil"})
    assert r.status_code == 429
    assert "retry-after" in {k.lower() for k in r.headers}
    # even the correct code is refused while locked out, and the code is burned
    r = client.post("/pair", json={"code": "123456", "device_name": "evil"})
    assert r.status_code == 429


def test_expired_code_rejected(client):
    auth = client.env.auth
    code, _ = auth._read_pairing()
    auth._write_pairing(code, time.time() - 1)
    r = client.post("/pair", json={"code": code, "device_name": "late"})
    assert r.status_code == 401


def test_token_requires_auth(client):
    assert client.get("/jobs/health_check_ping").status_code == 401
    assert client.get("/jobs/health_check_ping", headers={"Authorization": "Bearer junk"}).status_code == 401


def test_token_tamper_and_expiry(client):
    token, _ = pair(client)
    assert client.get("/jobs/health_check_ping", headers=auth_header(token)).status_code == 200
    payload, sig = token.split(".")
    assert client.get("/jobs/health_check_ping", headers=auth_header(payload + "." + sig[::-1])).status_code == 401

    auth = client.env.auth
    old = auth.TOKEN_TTL_SECONDS
    auth.TOKEN_TTL_SECONDS = -10
    try:
        expired = auth.create_access_token("x", "someid")
    finally:
        auth.TOKEN_TTL_SECONDS = old
    assert auth.verify_access_token(expired) is None


def test_token_without_registered_device_rejected(client):
    tok = client.env.auth.create_access_token("ghost", "not-registered")
    assert client.get("/jobs/health_check_ping", headers=auth_header(tok)).status_code == 401


def test_revoked_device_rejected(client):
    t1, id1 = pair(client, "one")
    client.env.auth.generate_pairing_code(announce=False)
    t2, id2 = pair(client, "two")
    r = client.delete(f"/devices/{id1}", headers=auth_header(t2))
    assert r.status_code == 200
    assert client.get("/jobs/health_check_ping", headers=auth_header(t1)).status_code == 401
    assert client.get("/jobs/health_check_ping", headers=auth_header(t2)).status_code == 200
    ids = [d["id"] for d in client.get("/devices", headers=auth_header(t2)).json()["devices"]]
    assert id1 not in ids and id2 in ids


def test_secret_key_persisted(tmp_path, monkeypatch):
    import importlib, sys
    monkeypatch.delenv("ARC_SECRET_KEY", raising=False)
    monkeypatch.setenv("ARC_DATA_DIR", str(tmp_path))
    sys.modules.pop("remote.auth", None)
    a = importlib.import_module("remote.auth")
    key1 = a.SECRET_KEY
    tok = a.create_access_token("d", "id1")
    sys.modules.pop("remote.auth", None)
    b = importlib.import_module("remote.auth")
    assert b.SECRET_KEY == key1
    assert b.verify_access_token(tok)["jti"] == "id1"
    assert oct((tmp_path / ".secret").stat().st_mode & 0o777) == "0o600"


def test_refresh_keeps_device(client):
    token, device_id = pair(client)
    r = client.post("/auth/refresh", headers=auth_header(token))
    assert r.status_code == 200
    assert client.env.auth.verify_access_token(r.json()["token"])["jti"] == device_id
