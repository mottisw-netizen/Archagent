"""Adapters, the workspace, and where a comment gets worked.

The product is multi-discipline: one municipal comment can land in the Revit
model, in a consultant's DWG, or in a document. These tests pin the two things
that must never regress - an unavailable adapter says exactly what it needs
instead of failing quietly, and a comment nobody can work becomes an open item
rather than disappearing.
"""

import shutil
import socket

import pytest

from archagent.adapters import (
    ARCHITECTURE,
    DRAINAGE,
    EDIT,
    TRAFFIC,
    AdapterRegistry,
    AdapterUnavailable,
    DwgAdapter,
    JsonAdapter,
    PdfAdapter,
    RevitAdapter,
    Router,
    SourceRef,
    Workspace,
    default_registry,
)
from archagent.comments import CommentAnalyzer
from archagent.drawing.mock_host import serve


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _comment(text: str, department: str):
    document = f"Department: {department}\n\nC-001: {text}\n"
    return CommentAnalyzer().analyze_document(document, source_ref="test.md")[0]


# ----------------------------------------------------------------------
# source references
# ----------------------------------------------------------------------
@pytest.mark.parametrize("value, kind, location", [
    ("/plans/project.json", "file", "/plans/project.json"),
    ("revit://127.0.0.1:8735", "host", "http://127.0.0.1:8735"),
    ("http://10.0.0.5:9000", "host", "http://10.0.0.5:9000"),
])
def test_a_source_is_read_from_a_plain_string(value, kind, location):
    source = SourceRef.parse(value)
    assert (source.kind, source.location) == (kind, location)


def test_a_revit_url_names_the_revit_host():
    assert SourceRef.parse("revit://127.0.0.1:8735").options["host"] == "revit"


# ----------------------------------------------------------------------
# which adapter opens what
# ----------------------------------------------------------------------
def test_each_source_finds_its_adapter(project):
    registry = default_registry()
    model = str(project / "source" / "project.json")
    for value, expected in [(model, "json"), ("traffic.dwg", "dwg"),
                            ("survey.dxf", "dwg"), ("appendix.pdf", "pdf"),
                            ("model.rvt", "revit"), ("revit://127.0.0.1:1", "revit")]:
        adapter = registry.for_source(SourceRef.parse(value))
        assert adapter is not None and adapter.name == expected, value


def test_a_json_file_that_is_not_a_plan_model_is_not_claimed(tmp_path):
    """Answer files and settings live in projects too; only a model has elements."""
    stray = tmp_path / "answers.json"
    stray.write_text('{"C-001": "approve"}', encoding="utf-8")
    assert default_registry().for_source(SourceRef.parse(str(stray))) is None


def test_an_unknown_source_has_no_adapter():
    assert default_registry().for_source(SourceRef.parse("survey.las")) is None


def test_disciplines_are_covered_by_the_adapters_that_claim_them():
    registry = default_registry()
    assert [a.name for a in registry.for_discipline(ARCHITECTURE)] == ["revit", "json"]
    assert "dwg" in [a.name for a in registry.for_discipline(TRAFFIC)]
    assert [a.name for a in registry.for_discipline(DRAINAGE)] == ["dwg"]


def test_a_rvt_file_on_disk_is_refused_with_an_instruction():
    """Revit's API only exists inside Revit; saying so beats a broken driver."""
    status = RevitAdapter().status(SourceRef.parse("/plans/permit.rvt"))
    assert not status.available
    assert "only runs inside" in status.reason and "add-in" in status.reason


def test_an_unreachable_revit_names_what_is_missing():
    status = RevitAdapter(f"http://127.0.0.1:{_free_port()}").status(
        SourceRef.parse("revit://127.0.0.1:1"))
    assert not status.available and "Revit" in status.reason


def test_a_bare_dwg_file_states_what_it_needs_instead_of_pretending():
    """No live document to edit or get approval against - same reasoning as Revit."""
    status = DwgAdapter().status(SourceRef.parse("traffic.dwg"))
    assert not status.available
    assert "AutoCAD" in status.reason and "live document" in status.reason
    with pytest.raises(AdapterUnavailable):
        DwgAdapter().open(SourceRef.parse("traffic.dwg"))


def test_an_unreachable_autocad_host_names_what_is_missing():
    status = DwgAdapter(f"http://127.0.0.1:{_free_port()}").status(
        SourceRef.parse("autocad://127.0.0.1:1"))
    assert not status.available and "Revit" not in status.reason


def test_the_pdf_adapter_can_read_but_never_edit():
    assert EDIT not in PdfAdapter().capabilities


# ----------------------------------------------------------------------
# the workspace
# ----------------------------------------------------------------------
def test_the_workspace_opens_a_file_and_reports_it(project):
    workspace = Workspace(AdapterRegistry([JsonAdapter()]))
    entry = workspace.add(SourceRef.parse(str(project / "source" / "project.json")))
    assert entry.available and entry.adapter_name == "json"
    assert workspace.primary() is entry.driver
    workspace.close()


def test_an_unopenable_source_is_recorded_not_raised(project):
    workspace = Workspace(default_registry())
    workspace.add(SourceRef.parse(str(project / "source" / "project.json")))
    blocked = workspace.add(SourceRef.parse("traffic.dwg"))
    assert not blocked.available and blocked.error
    assert [entry.adapter_name for entry in workspace.unavailable()] == ["dwg"]
    # The package still has a usable primary model.
    assert workspace.primary() is not None
    workspace.close()


def test_a_source_no_adapter_handles_says_so():
    entry = Workspace(default_registry()).add(SourceRef.parse("survey.las"))
    assert not entry.available and "no adapter" in entry.error


def test_a_document_is_opened_for_reading_and_never_as_a_drawing():
    entry = Workspace(default_registry()).add(SourceRef.parse("appendix.pdf"))
    assert entry.adapter_name == "pdf"
    assert not entry.available and "nothing in a PDF is edited" in entry.error


def test_the_architectural_model_is_the_primary_even_when_opened_second(project, tmp_path):
    model = tmp_path / "served.json"
    shutil.copyfile(project / "source" / "project.json", model)
    server = serve(model, port=_free_port())
    workspace = Workspace(default_registry())
    try:
        workspace.add(SourceRef.parse("appendix.pdf"))
        live = workspace.add(SourceRef.parse(f"revit://127.0.0.1:{server.server_address[1]}"))
        assert live.available and workspace.primary() is live.driver
    finally:
        workspace.close()
        server.shutdown()


def test_a_live_dwg_host_opens_the_same_way_a_live_revit_host_does(project, tmp_path):
    """The wire protocol is shared - a second live tool is not a special case."""
    model = tmp_path / "traffic.json"
    shutil.copyfile(project / "source" / "project.json", model)
    server = serve(model, port=_free_port())
    try:
        entry = Workspace(default_registry()).add(
            SourceRef.parse(f"autocad://127.0.0.1:{server.server_address[1]}"))
        assert entry.available and entry.adapter_name == "dwg"
        assert entry.can_edit()
        assert DRAINAGE in entry.disciplines and TRAFFIC in entry.disciplines
    finally:
        server.shutdown()


def test_a_civil3d_url_reaches_the_same_dwg_adapter():
    source = SourceRef.parse(f"civil3d://127.0.0.1:{_free_port()}")
    assert source.options["host"] == "civil3d"
    assert default_registry().for_source(source).name == "dwg"


# ----------------------------------------------------------------------
# routing
# ----------------------------------------------------------------------
def test_a_comment_is_routed_to_the_drawing_that_holds_its_element(project):
    workspace = Workspace(AdapterRegistry([JsonAdapter()]))
    workspace.add(SourceRef.parse(str(project / "source" / "project.json")))
    comment = _comment("Parking space P12 must be widened to at least 2.50 m.", "Traffic")
    routing = Router(workspace).route(comment)
    assert routing.routed and routing.source.adapter_name == "json"
    workspace.close()


def test_a_comment_for_an_unavailable_discipline_is_blocked_with_a_reason(project):
    """It must not silently fall through to the architectural model."""
    workspace = Workspace(default_registry())
    workspace.add(SourceRef.parse("traffic.dwg"))
    comment = _comment("The access road must be widened to at least 6.00 m.", "Infrastructure")
    routing = Router(workspace).route(comment)
    assert not routing.routed
    assert routing.reason and routing.needed
    assert routing.to_dict()["routed"] is False
    workspace.close()


def test_routing_survives_a_package_with_no_source_at_all():
    workspace = Workspace(default_registry())
    comment = _comment("Parking space P12 must be widened to at least 2.50 m.", "Traffic")
    routing = Router(workspace).route(comment)
    assert not routing.routed and routing.reason
