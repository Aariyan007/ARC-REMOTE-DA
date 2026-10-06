"""
Test harness for the remote daemon.

core.runtime pulls in the whole desktop/ML stack, so it is replaced with a small
stub. Each test gets a fresh temp data dir (DB + secret + pairing code).
"""
import importlib
import sys
import types

import pytest


class _Status:
    def __init__(self, value):
        self.value = value


class _Resp:
    def __init__(self, status, text, action="open_app"):
        self.status = _Status(status)
        self.final_result = text
        self.interpreted_action = action

    def to_dict(self):
        return {"status": self.status.value, "final_result": self.final_result,
                "interpreted_action": self.interpreted_action}

    @classmethod
    def ok(cls, *a, **k):
        return cls("completed", "ok")


def _make_runtime():
    rt = types.ModuleType("core.runtime")
    rt._booted = True
    rt.CommandResponse = _Resp
    rt.calls = []

    def execute_text_command(text, source="api", session_id=None, user="u"):
        rt.calls.append((text, source, session_id, user))
        handler = getattr(rt, "handler", None)
        if handler:
            return handler(text, session_id)
        return _Resp("completed", f"did: {text}")

    rt.execute_text_command = execute_text_command
    rt.boot = lambda voice=False: True
    return rt


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("ARC_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ARC_DB_PATH", str(tmp_path / "remote.db"))
    monkeypatch.setenv("ARC_SECRET_KEY", "test-secret")

    rt = _make_runtime()
    import core
    monkeypatch.setitem(sys.modules, "core.runtime", rt)
    monkeypatch.setattr(core, "runtime", rt, raising=False)

    for name in [m for m in sys.modules if m == "remote" or m.startswith("remote.")]:
        del sys.modules[name]
    server = importlib.import_module("remote.server")
    auth = importlib.import_module("remote.auth")
    dbm = importlib.import_module("remote.db")
    yield types.SimpleNamespace(server=server, auth=auth, db=dbm, rt=rt, tmp=tmp_path)
    # close thread-local connections so tmp dirs can be removed cleanly
    try:
        dbm.get_db().close()
    except Exception:
        pass


@pytest.fixture
def client(env):
    from fastapi.testclient import TestClient
    with TestClient(env.server.app) as c:  # runs lifespan -> writes a pairing code
        c.env = env
        yield c


def pair(client, name="Test Phone"):
    code, _ = client.env.auth._read_pairing()
    r = client.post("/pair", json={"code": code, "device_name": name})
    assert r.status_code == 200, r.text
    body = r.json()
    return body["token"], body["device_id"]


def auth_header(token):
    return {"Authorization": f"Bearer {token}"}
