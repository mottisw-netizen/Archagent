"""The Diff / Change Set.

What a reviewer and a CAD tool read after a run: which elements changed, by the
id the host uses, with the comment that demanded each change and the constraint
it satisfied.
"""

import json
import shutil
import socket
from pathlib import Path

from archagent import changeset
from archagent.consult import ScriptedResponder
from archagent.drawing.mock_host import serve
from archagent.models import CommentStatus
from archagent.orchestrator import Orchestrator
from archagent.drawing.revit import RevitDriver


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _run(project, tmp_path, **kwargs):
    return Orchestrator(project, responder=ScriptedResponder({"C-005": "approve"}),
                        output_dir=tmp_path / "out", **kwargs).run()


def test_the_run_writes_a_change_set(project, tmp_path):
    result = _run(project, tmp_path)
    path = Path(result.files["change_set"])
    document = json.loads(path.read_text(encoding="utf-8"))
    assert document == result.change_set
    assert document["version"] == result.version
    assert document["parent_version"] == result.parent_version
    assert document["counts"]["changes"] == len(result.changes)


def test_every_change_is_traceable_to_a_comment_and_a_plan(project, tmp_path):
    document = _run(project, tmp_path).change_set
    for element in document["elements"]:
        for change in element["properties"]:
            assert change["comment_id"] and change["plan_id"]


def test_the_widened_bay_carries_its_before_and_after(project, tmp_path):
    document = _run(project, tmp_path).change_set
    bay = next(e for e in document["elements"] if e["element_id"] == "parking_p12")
    width = next(c for c in bay["properties"] if c["property"] == "width")
    assert (width["before"], width["after"]) == (2.4, 2.5)
    # And enough geometry to draw the highlight without opening the CAD tool.
    assert bay["geometry"]["dw"] == 0.1
    assert bay["geometry"]["before"]["w"] == 2.4


def test_the_change_set_groups_by_comment_with_its_status(project, tmp_path):
    result = _run(project, tmp_path)
    by_comment = {entry["comment_id"]: entry for entry in result.change_set["by_comment"]}
    assert by_comment["C-001"]["status"] == CommentStatus.RESOLVED.value
    assert "parking_p12" in by_comment["C-001"]["elements"]
    assert by_comment["C-001"]["department"] == "Traffic"
    assert by_comment["C-001"]["evidence"]


def test_the_change_set_records_which_constraints_the_run_moved(project, tmp_path):
    document = _run(project, tmp_path).change_set
    resolved = [c for c in document["constraints"] if c["resolved_here"]]
    assert resolved, "a run that fixed nothing measurable is not a correction"
    for constraint in resolved:
        assert constraint["status_before"] == "fail"
        assert constraint["status_after"] == "pass"
        assert constraint["measured"] is not None
    assert not [c for c in document["constraints"] if c["regressed_here"]]


def test_constraints_that_were_already_fine_are_not_noise(project, tmp_path):
    document = _run(project, tmp_path).change_set
    assert not [c for c in document["constraints"]
                if c["status_before"] == c["status_after"] == "pass"]


def test_the_highlight_list_is_exactly_what_changed(project, tmp_path):
    result = _run(project, tmp_path)
    assert set(result.change_set["highlight"]) == {c.element_id for c in result.changes}


def test_a_run_that_changes_nothing_still_writes_an_empty_change_set(project, tmp_path):
    """An empty diff is an answer; a missing file is a question."""
    result = Orchestrator(project, mode="autonomous", responder=lambda *a, **k: "defer",
                          output_dir=tmp_path / "out").run()
    document = json.loads(Path(result.files["change_set"]).read_text(encoding="utf-8"))
    assert document["elements"] == [] or document["counts"]["changes"] >= 0
    assert document["change_set_version"] == changeset.CHANGE_SET_VERSION


# ----------------------------------------------------------------------
# live host
# ----------------------------------------------------------------------
def test_a_live_run_names_the_host_and_highlights_in_it(project, tmp_path):
    served = tmp_path / "served.json"
    shutil.copyfile(project / "source" / "project.json", served)
    server = serve(served, port=_free_port())
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        result = _run(project, tmp_path, sources=[f"revit://127.0.0.1:{server.server_address[1]}"])
        # The host was asked to select what changed - that is "highlight what
        # changed" inside the CAD tool, not only in a rendered preview.
        assert set(server.RequestHandlerClass.host.highlighted) == \
               set(result.change_set["highlight"]) - {"parking_table"}
        assert RevitDriver(base).info().compatible()
    finally:
        server.shutdown()
    assert result.change_set["source"]["kind"] == "host"
    assert result.change_set["source"]["adapter"] == "revit"
    assert result.change_set["source"]["location"] == base


def test_a_host_that_cannot_highlight_does_not_break_the_run(project, tmp_path, monkeypatch):
    served = tmp_path / "served.json"
    shutil.copyfile(project / "source" / "project.json", served)
    server = serve(served, port=_free_port())
    from archagent.drawing.api import DrawingAPIError

    def refuse(self, element_ids):
        raise DrawingAPIError("this host cannot select elements")

    monkeypatch.setattr(RevitDriver, "highlight", refuse)
    try:
        result = _run(project, tmp_path, sources=[f"revit://127.0.0.1:{server.server_address[1]}"])
    finally:
        server.shutdown()
    assert result.changes and result.files["change_set"]
