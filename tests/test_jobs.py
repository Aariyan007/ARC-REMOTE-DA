import threading
import time

from tests.conftest import pair, auth_header, _Resp


def _wait_for(pred, timeout=3.0):
    end = time.time() + timeout
    while time.time() < end:
        if pred():
            return True
        time.sleep(0.02)
    return False


def _second_device(client):
    client.env.auth.generate_pairing_code(announce=False)
    return pair(client, "other")


def test_command_runs_and_events_persisted(client):
    token, _ = pair(client)
    h = auth_header(token)
    r = client.post("/command", json={"text": "open chrome", "source": "controller"}, headers=h)
    assert r.status_code == 200
    job_id = r.json()["job_id"]
    assert _wait_for(lambda: client.get(f"/jobs/{job_id}", headers=h).json()["status"] == "completed")
    data = client.get(f"/jobs/{job_id}", headers=h).json()
    types = [e["type"] for e in data["events"]]
    assert types[0] == "ack" and types[-1] == "result"
    # since= resumes after already-seen events
    tail = client.get(f"/jobs/{job_id}?since={len(types) - 1}", headers=h).json()["events"]
    assert [e["type"] for e in tail] == ["result"]


def test_remote_cannot_claim_voice_source(client):
    token, _ = pair(client)
    client.post("/command", json={"text": "hi", "source": "voice"}, headers=auth_header(token))
    assert _wait_for(lambda: client.env.rt.calls)
    assert client.env.rt.calls[0][1] == "api"


def test_dangerous_command_rejected(client):
    token, _ = pair(client)
    r = client.post("/command", json={"text": "rm -rf /"}, headers=auth_header(token))
    assert r.status_code == 400
    assert client.env.rt.calls == []


def test_503_when_not_booted(client):
    token, _ = pair(client)
    client.env.rt._booted = False
    client.env.server._boot_error = "boom"
    r = client.post("/command", json={"text": "hi"}, headers=auth_header(token))
    assert r.status_code == 503 and "boom" in r.json()["detail"]
    assert client.get("/health").json()["boot_error"] == "boom"


def test_jobs_are_private_to_their_device(client):
    t1, _ = pair(client)
    t2, _ = _second_device(client)
    job_id = client.post("/command", json={"text": "hi"}, headers=auth_header(t1)).json()["job_id"]
    assert client.get(f"/jobs/{job_id}", headers=auth_header(t2)).status_code == 404
    assert client.post(f"/reply/{job_id}", json={"answer": "yes"}, headers=auth_header(t2)).status_code == 404
    assert client.post(f"/jobs/{job_id}/cancel", headers=auth_header(t2)).status_code == 404
    assert client.get(f"/jobs/{job_id}", headers=auth_header(t1)).status_code == 200


def test_clarify_reply_roundtrip_with_nonce(client):
    from remote.job_store import ask_user
    token, _ = pair(client)
    h = auth_header(token)
    answers = []

    def handler(text, job_id):
        answers.append(ask_user(job_id, "which file?", "clarify"))
        return _Resp("completed", "done")

    client.env.rt.handler = handler
    job_id = client.post("/command", json={"text": "find"}, headers=h).json()["job_id"]

    def prompt():
        evs = client.get(f"/jobs/{job_id}", headers=h).json()["events"]
        return next((e for e in evs if e["type"] == "clarify"), None)

    assert _wait_for(prompt)
    nonce = prompt()["data"]["nonce"]
    # wrong nonce is refused and does not answer the prompt
    assert client.post(f"/reply/{job_id}", json={"answer": "x", "nonce": "nope"}, headers=h).status_code == 409
    assert client.post(f"/reply/{job_id}", json={"answer": "resume.pdf", "nonce": nonce}, headers=h).status_code == 200
    assert _wait_for(lambda: answers == ["resume.pdf"])
    assert _wait_for(lambda: client.get(f"/jobs/{job_id}", headers=h).json()["status"] == "completed")
    # nothing waiting any more -> late reply refused
    assert client.post(f"/reply/{job_id}", json={"answer": "late"}, headers=h).status_code == 409


def test_cancel_unblocks_job(client):
    from remote.job_store import ask_user
    token, _ = pair(client)
    h = auth_header(token)
    got = []

    def handler(text, job_id):
        got.append(ask_user(job_id, "sure?", "confirm"))
        raise RuntimeError("stop")

    client.env.rt.handler = handler
    job_id = client.post("/command", json={"text": "delete it"}, headers=h).json()["job_id"]
    assert _wait_for(lambda: any(e["type"] == "confirm" for e in client.get(f"/jobs/{job_id}", headers=h).json()["events"]))
    assert client.post(f"/jobs/{job_id}/cancel", headers=h).status_code == 200
    assert _wait_for(lambda: got == [""])          # blocked thread released with no answer
    evs = client.get(f"/jobs/{job_id}", headers=h).json()["events"]
    assert evs[-1]["type"] == "error" and "Cancelled" in evs[-1]["message"]
    assert client.get(f"/jobs/{job_id}", headers=h).json()["status"] == "cancelled" or _wait_for(
        lambda: client.get(f"/jobs/{job_id}", headers=h).json()["status"] == "cancelled")


def test_concurrency_cap_per_device(client):
    token, _ = pair(client)
    h = auth_header(token)
    gate = threading.Event()
    client.env.rt.handler = lambda text, jid: (gate.wait(5), _Resp("completed", "ok"))[1]
    try:
        cap = client.env.server.MAX_JOBS_PER_DEVICE
        for _ in range(cap):
            assert client.post("/command", json={"text": "a"}, headers=h).status_code == 200
        assert client.post("/command", json={"text": "a"}, headers=h).status_code == 429
    finally:
        gate.set()


def test_job_timeout(client):
    token, _ = pair(client)
    h = auth_header(token)
    client.env.server.JOB_TIMEOUT = 0.2
    gate = threading.Event()
    client.env.rt.handler = lambda text, jid: (gate.wait(5), _Resp("completed", "late"))[1]
    try:
        job_id = client.post("/command", json={"text": "slow"}, headers=h).json()["job_id"]
        assert _wait_for(lambda: client.get(f"/jobs/{job_id}", headers=h).json()["events"][-1]["type"] == "error")
        assert "Timed out" in client.get(f"/jobs/{job_id}", headers=h).json()["events"][-1]["message"]
    finally:
        gate.set()
    time.sleep(0.1)
    # the late result must not be appended after the timeout error
    assert client.get(f"/jobs/{job_id}", headers=h).json()["events"][-1]["type"] == "error"


def test_ws_ticket_flow_and_resume(client):
    token, _ = pair(client)
    h = auth_header(token)
    job_id = client.post("/command", json={"text": "hi"}, headers=h).json()["job_id"]
    assert _wait_for(lambda: client.get(f"/jobs/{job_id}", headers=h).json()["status"] == "completed")

    ticket = client.post("/ws-ticket", headers=h).json()["ticket"]
    with client.websocket_connect(f"/stream/{job_id}?ticket={ticket}") as ws:
        msgs = []
        while True:
            m = ws.receive_json()
            msgs.append(m)
            if m["type"] in ("result", "error"):
                break
    assert msgs[0]["type"] == "ack" and msgs[-1]["type"] == "result"

    # ticket is single use
    import pytest
    from starlette.websockets import WebSocketDisconnect
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"/stream/{job_id}?ticket={ticket}"):
            pass

    # resume: only events after `since`
    ticket = client.post("/ws-ticket", headers=h).json()["ticket"]
    with client.websocket_connect(f"/stream/{job_id}?ticket={ticket}&since={len(msgs) - 1}") as ws:
        assert ws.receive_json()["type"] == "result"


def test_ws_rejects_bearer_in_url_and_other_device(client):
    import pytest
    from starlette.websockets import WebSocketDisconnect
    t1, _ = pair(client)
    t2, _ = _second_device(client)
    job_id = client.post("/command", json={"text": "hi"}, headers=auth_header(t1)).json()["job_id"]
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"/stream/{job_id}?token={t1}"):
            pass
    ticket2 = client.post("/ws-ticket", headers=auth_header(t2)).json()["ticket"]
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"/stream/{job_id}?ticket={ticket2}"):
            pass


def test_history_survives_memory_loss(client):
    token, _ = pair(client)
    h = auth_header(token)
    job_id = client.post("/command", json={"text": "hi"}, headers=h).json()["job_id"]
    assert _wait_for(lambda: client.get(f"/jobs/{job_id}", headers=h).json()["status"] == "completed")
    from remote.job_store import get_job_store
    get_job_store()._jobs.clear()               # simulate server restart / eviction
    data = client.get(f"/jobs/{job_id}", headers=h).json()
    assert data["events"][-1]["type"] == "result"
    ticket = client.post("/ws-ticket", headers=h).json()["ticket"]
    with client.websocket_connect(f"/stream/{job_id}?ticket={ticket}") as ws:
        got = [ws.receive_json() for _ in range(len(data["events"]))]
    assert got[-1]["type"] == "result"
    assert [j["id"] for j in client.get("/jobs", headers=h).json()["jobs"]] == [job_id]


def test_job_store_eviction(client):
    from remote.job_store import get_job_store, JobEvent
    store = get_job_store()
    job = store.get_or_create("old", "d")
    job.add_event(JobEvent("result", "x"))
    job.finished_at = time.time() - 99999
    store.get_or_create("new", "d")
    assert store.get("old") is None and store.get("new") is not None


def test_proactive_create_exists(client):
    from remote.job_store import get_job_store
    job = get_job_store().create("proactive-1", command="[ARC Proactive]", source="proactive_loop")
    assert job.job_id == "proactive-1"
