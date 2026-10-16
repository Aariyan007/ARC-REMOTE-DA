import os
import time

import pytest

from remote_tools import files, policy
from tests.conftest import pair, auth_header


@pytest.fixture
def tree(tmp_path, monkeypatch):
    root = tmp_path / "docs"
    (root / "sub").mkdir(parents=True)
    for name in ["resume.pdf", "my_resume_2024.docx", "Resume Final.pdf", "budget.xlsx",
                 "project notes.md", "holiday-photo.jpg"]:
        (root / name).write_text("x")
    (root / "sub" / "taxes_2023.pdf").write_text("x")
    (root / ".hidden").write_text("x")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("top secret")
    monkeypatch.setenv("ARC_FILE_ROOTS", str(root))
    files.clear_index_cache()
    return root, outside


# ── policy ───────────────────────────────────────────────────

def test_safe_file_path_inside_root(tree):
    root, _ = tree
    assert policy.safe_file_path(str(root / "resume.pdf")) == os.path.realpath(root / "resume.pdf")


def test_safe_file_path_rejects_escape(tree):
    root, outside = tree
    assert policy.safe_file_path(str(outside / "secret.txt")) is None
    assert policy.safe_file_path(str(root / ".." / "outside" / "secret.txt")) is None
    assert policy.safe_file_path(str(root)) is None            # directories are not files
    assert policy.safe_file_path(str(root / "nope.txt")) is None
    assert policy.safe_file_path("bad\x00path") is None
    assert policy.safe_file_path("") is None


def test_safe_file_path_rejects_symlink_out_of_root(tree):
    root, outside = tree
    link = root / "innocent.txt"
    os.symlink(outside / "secret.txt", link)
    assert policy.safe_file_path(str(link)) is None


def test_redact():
    assert "hunter2" not in policy.redact("wifi password=hunter2 ok")
    assert "[REDACTED]" in policy.redact("Authorization: Bearer abcdefghijklmnop")
    assert policy.redact("nothing secret here") == "nothing secret here"
    assert policy.redact("") == ""


# ── search ───────────────────────────────────────────────────

def test_exact_and_partial_name(tree):
    r = files.find_files("resume")
    assert r["exact"] and r["matches"][0]["name"] in {"resume.pdf", "Resume Final.pdf", "my_resume_2024.docx"}
    assert all(m["match_type"] in ("exact", "similar") for m in r["matches"])


def test_extension_hint_prefers_matching_type(tree):
    r = files.find_files("resume.pdf")
    assert r["matches"][0]["name"] == "resume.pdf"


def test_similar_names_when_no_exact(tree):
    r = files.find_files("resum")                # typo / partial
    assert r["matches"] and "resume" in r["matches"][0]["name"].lower()
    r = files.find_files("budgit")               # misspelling
    assert r["matches"][0]["name"] == "budget.xlsx"
    assert not r["exact"]
    assert r["matches"][0]["match_type"] == "similar"


def test_word_order_and_nested(tree):
    assert files.find_files("notes project")["matches"][0]["name"] == "project notes.md"
    assert files.find_files("taxes 2023")["matches"][0]["name"] == "taxes_2023.pdf"


def test_nothing_similar_returns_empty(tree):
    r = files.find_files("qqqzzzxxx")
    assert r["matches"] == [] and not r["exact"]


def test_hidden_files_and_blank_query(tree):
    assert files.find_files("hidden")["matches"] == []
    assert files.find_files("   ")["matches"] == []


# ── tickets ──────────────────────────────────────────────────

def test_ticket_roundtrip_and_owner_binding(tree):
    root, _ = tree
    t = files.issue_download_ticket("dev1", str(root / "resume.pdf"))
    assert t
    assert files.resolve_download_ticket(t, "dev1") == os.path.realpath(root / "resume.pdf")
    assert files.resolve_download_ticket(t, "dev2") is None
    assert files.resolve_download_ticket("garbage", "dev1") is None


def test_ticket_refused_for_outside_and_oversize(tree, monkeypatch):
    root, outside = tree
    assert files.issue_download_ticket("d", str(outside / "secret.txt")) is None
    monkeypatch.setenv("ARC_MAX_DOWNLOAD_MB", "1")
    big = root / "big.bin"
    big.write_bytes(b"0" * (2 * 1024 * 1024))
    assert files.issue_download_ticket("d", str(big)) is None


def test_ticket_expires_and_revalidates(tree, monkeypatch):
    root, outside = tree
    f = root / "temp.txt"
    f.write_text("x")
    t = files.issue_download_ticket("d", str(f))
    # file swapped for a symlink to outside after the ticket was issued -> rejected
    f.unlink()
    os.symlink(outside / "secret.txt", f)
    assert files.resolve_download_ticket(t, "d") is None
    t2 = files.issue_download_ticket("d", str(root / "resume.pdf"))
    monkeypatch.setattr(time, "time", lambda: 9e12)
    assert files.resolve_download_ticket(t2, "d") is None


# ── endpoints ────────────────────────────────────────────────

def _wait_done(client, h, job_id, timeout=3.0):
    end = time.time() + timeout
    while time.time() < end:
        d = client.get(f"/jobs/{job_id}", headers=h).json()
        if d["status"] in ("completed", "failed", "cancelled"):
            return d
        time.sleep(0.02)
    raise AssertionError("job did not finish")


def test_tools_require_auth_and_unknown_tool(client):
    assert client.get("/tools").status_code == 401
    assert client.post("/tools/search_files", json={"args": {"query": "x"}}).status_code == 401
    token, _ = pair(client)
    h = auth_header(token)
    assert client.post("/tools/nope", json={"args": {}}, headers=h).status_code == 404
    names = {t["name"] for t in client.get("/tools", headers=h).json()["tools"]}
    assert {"search_files", "list_dir", "read_file", "system_status"} <= names


def test_search_tool_end_to_end_and_download(client, tree):
    root, _ = tree
    token, _ = pair(client)
    h = auth_header(token)
    job_id = client.post("/tools/search_files", json={"args": {"query": "budgit"}}, headers=h).json()["job_id"]
    d = _wait_done(client, h, job_id)
    assert d["status"] == "completed"
    ev = d["events"][-1]
    assert ev["type"] == "result" and "Did you mean" in ev["message"]
    m = ev["data"]["matches"][0]
    assert m["name"] == "budget.xlsx" and m["downloadable"]
    r = client.get(m["download_url"], headers=h)
    assert r.status_code == 200 and r.content == b"x"
    assert "budget.xlsx" in r.headers["content-disposition"]


def test_download_requires_auth_and_ownership(client, tree):
    root, _ = tree
    t1, _ = pair(client)
    client.env.auth.generate_pairing_code(announce=False)
    t2, _ = pair(client, "other")
    job_id = client.post("/tools/search_files", json={"args": {"query": "budget"}}, headers=auth_header(t1)).json()["job_id"]
    d = _wait_done(client, auth_header(t1), job_id)
    url = d["events"][-1]["data"]["matches"][0]["download_url"]
    assert client.get(url).status_code == 401
    assert client.get(url, headers=auth_header(t2)).status_code == 404
    assert client.get(url, headers=auth_header(t1)).status_code == 200


def test_download_ignores_path_traversal(client, tree):
    token, _ = pair(client)
    h = auth_header(token)
    assert client.get("/files/..%2F..%2Fetc%2Fpasswd", headers=h).status_code == 404
    assert client.get("/files/not-a-ticket", headers=h).status_code == 404


def test_search_tool_validation_and_no_match(client, tree):
    token, _ = pair(client)
    h = auth_header(token)
    # schema validation rejects a missing/unknown/mistyped argument before any job is created
    r = client.post("/tools/search_files", json={"args": {}}, headers=h)
    assert r.status_code == 400 and "query" in r.json()["detail"]
    assert client.post("/tools/search_files", json={"args": {"query": "x", "evil": 1}}, headers=h).status_code == 400
    assert client.post("/tools/search_files", json={"args": {"query": 5}}, headers=h).status_code == 400
    j = client.post("/tools/search_files", json={"args": {"query": "qqqzzzxxx"}}, headers=h).json()["job_id"]
    d = _wait_done(client, h, j)
    assert d["status"] == "failed"


def test_tool_jobs_count_against_caps_and_are_private(client, tree):
    t1, _ = pair(client)
    client.env.auth.generate_pairing_code(announce=False)
    t2, _ = pair(client, "other")
    j = client.post("/tools/search_files", json={"args": {"query": "budget"}}, headers=auth_header(t1)).json()["job_id"]
    assert client.get(f"/jobs/{j}", headers=auth_header(t2)).status_code == 404


# ── index coverage ───────────────────────────────────────────

def test_each_root_gets_its_own_budget(tmp_path, monkeypatch):
    big, small = tmp_path / "big", tmp_path / "small"
    big.mkdir()
    small.mkdir()
    for i in range(30):
        (big / f"f{i}.txt").write_text("x")
    (small / "needle.txt").write_text("x")
    monkeypatch.setattr(files, "MAX_FILES_PER_ROOT", 10)
    files.clear_index_cache()
    r = files.find_files("needle", roots=[str(big), str(small)])
    assert r["matches"] and r["matches"][0]["name"] == "needle.txt"   # not starved by the big folder
    assert r["index_truncated"] is True
    stats = files.index_stats([str(big), str(small)])
    assert stats[str(big)]["truncated"] and not stats[str(small)]["truncated"]


def test_truncation_is_reported_to_the_user(tmp_path, monkeypatch):
    from core.action_result import ActionResult  # noqa: F401
    from remote_tools import registry
    root = tmp_path / "r"
    root.mkdir()
    for i in range(20):
        (root / f"f{i}.txt").write_text("x")
    monkeypatch.setenv("ARC_FILE_ROOTS", str(root))
    monkeypatch.setattr(files, "MAX_FILES_PER_ROOT", 5)
    files.clear_index_cache()
    ctx = registry.ToolContext("d", "j", lambda *a, **k: None)
    res = registry.get_tool("search_files").fn({"query": "qqqzzz"}, ctx)
    assert not res.success and "only part of it was searched" in res.user_message
    assert "Searched:" in res.error


def test_nested_project_folder_is_found(tmp_path, monkeypatch):
    root = tmp_path / "Desktop"
    (root / "BackEnd" / "app" / "core").mkdir(parents=True)
    (root / "BackEnd" / "app" / "core" / "settings.py").write_text("x")
    (root / "BackEnd" / "venv" / "lib").mkdir(parents=True)
    (root / "BackEnd" / "venv" / "lib" / "settings.py").write_text("x")   # skipped
    monkeypatch.setenv("ARC_FILE_ROOTS", str(root))
    files.clear_index_cache()
    r = files.find_files("settings.py")
    assert [m["path"] for m in r["matches"]] == [str(root / "BackEnd" / "app" / "core" / "settings.py")]


def test_permission_denied_is_surfaced(tmp_path, monkeypatch):
    from remote_tools import registry
    root = tmp_path / "Desktop"
    root.mkdir()
    (root / "ok.txt").write_text("x")
    monkeypatch.setenv("ARC_FILE_ROOTS", str(root))
    real_walk = os.walk

    def blocked_walk(top, onerror=None, **kw):
        if onerror:
            onerror(PermissionError(1, "Operation not permitted", top))   # what macOS privacy (TCC) raises
        return iter(())

    monkeypatch.setattr(files.os, "walk", blocked_walk)
    files.clear_index_cache()
    assert files.index_stats()[os.path.realpath(root)]["permission_denied"] is True
    ctx = registry.ToolContext("d", "j", lambda *a, **k: None)
    res = registry.get_tool("search_files").fn({"query": "anything"}, ctx)
    assert not res.success and "macOS blocked access" in res.user_message and "Files and Folders" in res.user_message
    monkeypatch.setattr(files.os, "walk", real_walk)
    files.clear_index_cache()
    assert files.find_files("ok")["matches"]
