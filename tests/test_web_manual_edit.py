"""Manual editing endpoints (move/resize/delete) on the Web Editor's API."""

import json

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from archagent.web import server  # noqa: E402
from archagent.web.projects import ProjectStore  # noqa: E402

MODEL = {
    "project_id": "p", "units": "m", "north": "+y",
    "site": {"plot": {"kind": "rect", "x": 0.0, "y": 0.0, "w": 40.0, "h": 30.0}},
    "sheets": [], "elements": [
        {"id": "wall-1", "type": "wall", "label": "Wall 1",
         "geometry": {"kind": "rect", "x": 5.0, "y": 5.0, "w": 2.0, "h": 0.2},
         "properties": {"width_axis": "x", "anchor": "south_west"}},
    ],
    "schedules": {},
}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "projects", ProjectStore(tmp_path / "workspace"))
    monkeypatch.setattr(server, "runs", server.RunManager())
    with TestClient(server.app) as test_client:
        yield test_client


@pytest.fixture
def project_id(client):
    response = client.post("/api/projects", data={"name": "edit-test"}, files=[
        ("source_model", ("project.json", json.dumps(MODEL).encode("utf-8"), "application/json")),
    ])
    return response.json()["project_id"]


def test_versions_start_with_only_original(client, project_id):
    body = client.get(f"/api/projects/{project_id}/versions").json()
    assert body["versions"] == ["original"]


def test_get_model_reads_the_original_source(client, project_id):
    body = client.get(f"/api/projects/{project_id}/model").json()
    assert body["version"] == "original"
    assert body["model"]["elements"][0]["id"] == "wall-1"


def test_move_creates_a_version_reachable_afterwards(client, project_id):
    response = client.post(f"/api/projects/{project_id}/edit", json={
        "action": "move", "element_id": "wall-1", "distance": 1.5, "direction": "east",
    })
    assert response.status_code == 200
    body = response.json()
    assert body["version"] == "v1"
    assert body["parent_version"] == "original"
    moved = next(e for e in body["model"]["elements"] if e["id"] == "wall-1")
    assert moved["geometry"]["x"] == pytest.approx(6.5)

    versions_after = client.get(f"/api/projects/{project_id}/versions").json()["versions"]
    assert versions_after == ["original", "v1"]

    at_v1 = client.get(f"/api/projects/{project_id}/model", params={"version": "v1"}).json()
    assert at_v1["model"]["elements"][0]["geometry"]["x"] == pytest.approx(6.5)


def test_delete_then_undo_by_reopening_the_original_version(client, project_id):
    client.post(f"/api/projects/{project_id}/edit", json={
        "action": "delete", "element_id": "wall-1",
    })
    at_v1 = client.get(f"/api/projects/{project_id}/model", params={"version": "v1"}).json()
    assert at_v1["model"]["elements"] == []

    # "Undo" = go back to viewing/editing an earlier version - nothing was
    # destroyed, v1 still exists, editing "original" again just forks.
    response = client.post(f"/api/projects/{project_id}/edit", json={
        "base_version": "original", "action": "move", "element_id": "wall-1",
        "distance": 1.0, "direction": "north",
    })
    assert response.status_code == 200
    assert response.json()["version"] == "v2"
    assert response.json()["parent_version"] == "original"


def test_unknown_action_returns_400(client, project_id):
    response = client.post(f"/api/projects/{project_id}/edit", json={
        "action": "teleport", "element_id": "wall-1",
    })
    assert response.status_code == 400


def test_missing_element_id_returns_400(client, project_id):
    response = client.post(f"/api/projects/{project_id}/edit", json={"action": "move"})
    assert response.status_code == 400


def test_unknown_project_returns_404(client):
    assert client.get("/api/projects/does-not-exist/model").status_code == 404
    assert client.post("/api/projects/does-not-exist/edit",
                       json={"action": "move", "element_id": "x"}).status_code == 404


# ----------------------------------------------------------------------
# regressions found in code review
# ----------------------------------------------------------------------
def test_asking_for_original_returns_the_source_not_the_latest_version(client, project_id):
    """The frontend sends version=original explicitly; the server must honour
    it. Resolving it to the newest version instead would render a later
    model under an 'original' label and silently fork the next edit off the
    pristine source, losing the changes the user was looking at."""
    client.post(f"/api/projects/{project_id}/edit", json={
        "action": "move", "element_id": "wall-1", "distance": 3.0, "direction": "east",
    })
    body = client.get(f"/api/projects/{project_id}/model",
                      params={"version": "original"}).json()
    assert body["version"] == "original"
    assert body["model"]["elements"][0]["geometry"]["x"] == pytest.approx(5.0)


def test_listing_versions_does_not_create_a_versions_directory(client, project_id, tmp_path):
    """Merely opening the editor must not write into a project - the bundled
    examples/ tree especially."""
    project_dir = server.projects.directory(project_id)
    versions_dir = project_dir / "versions"
    assert not versions_dir.exists()
    client.get(f"/api/projects/{project_id}/versions")
    assert not versions_dir.exists()


def test_a_non_json_version_is_a_400_not_a_500(client, project_id):
    """A run that versioned a DXF project saves project_v1.dxf; manual
    editing is JSON-only, so it must say so rather than raising a
    VersionError out of the endpoint."""
    project_dir = server.projects.directory(project_id)
    version_dir = project_dir / "versions" / "v1"
    version_dir.mkdir(parents=True)
    (version_dir / "project_v1.dxf").write_text("not json", encoding="utf-8")

    assert client.get(f"/api/projects/{project_id}/versions").json()["versions"] == [
        "original", "v1"]
    response = client.get(f"/api/projects/{project_id}/model", params={"version": "v1"})
    assert response.status_code == 404
    assert "JSON model projects only" in response.json()["detail"]


def test_a_manual_edit_writes_an_audit_entry(client, project_id):
    client.post(f"/api/projects/{project_id}/edit", json={
        "action": "move", "element_id": "wall-1", "distance": 1.0, "direction": "east",
    })
    audit = server.projects.directory(project_id) / "versions" / "v1" / "audit.jsonl"
    assert audit.exists()
    entry = json.loads(audit.read_text(encoding="utf-8").splitlines()[0])
    assert entry["actor"] == "manual_edit"
    assert entry["params"]["element_id"] == "wall-1"
    assert entry["params"]["action"] == "move"
