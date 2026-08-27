"""One run, more than one live tool - the point of the adapter layer.

Everything below the orchestrator (mapper, planner, executor, validator) was
already driver-parameterised; what was missing was the orchestrator actually
using more than one of them in a single run. These tests build a project split
across two independent sources - a live Revit-protocol host holding the
architecture, and a plain JSON file holding the parking layout - and prove the
run edits both, validates each against the driver that can actually measure
it, and reports one merged result naming which tool did what.
"""

import json
import socket

import pytest

from archagent.consult import ScriptedResponder, auto_approve
from archagent.drawing.dwg import DwgDriver
from archagent.drawing.mock_host import serve
from archagent.drawing.revit import RevitDriver
from archagent.models import CommentStatus
from archagent.orchestrator import Orchestrator


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


SITE = {"plot": {"kind": "rect", "x": 0.0, "y": 0.0, "w": 40.0, "h": 30.0},
        "plot_number": "12/4", "zoning": "XYZ/123"}
SHEETS = [{"id": "A-101", "name": "Ground Floor Plan"}]

#: Only the architecture: what a Revit host would hold.
ARCH_MODEL = {
    "project_id": "riverside-12", "units": "m", "north": "+y", "site": SITE, "sheets": SHEETS,
    "elements": [
        {"id": "building", "type": "building", "label": "Residential building",
         "layer": "A-BLDG", "level": "Ground Floor", "sheet": "A-101",
         "geometry": {"kind": "rect", "x": 5.0, "y": 20.0, "w": 20.0, "h": 7.4},
         "properties": {"width_axis": "x", "anchor": "south_west",
                        "counts_as_floor_area": True, "floor_area_factor": 12,
                        "storeys": 12, "consultant": "architecture"}},
    ],
    "schedules": {},
}

#: Only the parking layout: what a second, separate tool would hold.
TRAFFIC_MODEL = {
    "project_id": "riverside-12", "units": "m", "north": "+y", "site": SITE, "sheets": SHEETS,
    "elements": [
        {"id": "parking_p11", "type": "parking", "label": "P11", "layer": "A-PARK",
         "level": "Ground Floor", "sheet": "A-101",
         "geometry": {"kind": "rect", "x": 6.0, "y": 2.0, "w": 2.4, "h": 5.0},
         "properties": {"width_axis": "x", "anchor": "south_west", "approved": True,
                        "category": "resident", "related_elements": ["parking_p12"]}},
        {"id": "parking_p12", "type": "parking", "label": "P12", "layer": "A-PARK",
         "level": "Ground Floor", "sheet": "A-101",
         "geometry": {"kind": "rect", "x": 8.5, "y": 2.0, "w": 2.4, "h": 5.0},
         "properties": {"width_axis": "x", "anchor": "south_west", "category": "resident",
                        "related_elements": ["parking_p11", "parking_p13"]}},
        {"id": "parking_p13", "type": "parking", "label": "P13", "layer": "A-PARK",
         "level": "Ground Floor", "sheet": "A-101",
         "geometry": {"kind": "rect", "x": 10.9, "y": 2.0, "w": 2.4, "h": 5.0},
         "properties": {"width_axis": "x", "anchor": "south_west", "approved": True,
                        "category": "visitor", "related_elements": ["parking_p12"]}},
        {"id": "dim_p12_width", "type": "dimension", "label": "P12 width", "layer": "A-DIMS",
         "level": "Ground Floor", "sheet": "A-101", "text": "2.40",
         "geometry": {"kind": "rect", "x": 8.5, "y": 1.2, "w": 2.4, "h": 0.3},
         "properties": {"value": 2.4, "measures": {"element_id": "parking_p12", "parameter": "width"}}},
    ],
    "schedules": {
        "parking_table": {"title": "Parking schedule", "sheet": "A-101",
                          "source": {"type": "parking"},
                          "fields": {"Mark": "label", "Width": "width", "Length": "length",
                                    "Category": "category"},
                          "rows": [{"Mark": "P11", "Width": 2.4, "Length": 5.0, "Category": "resident"},
                                  {"Mark": "P12", "Width": 2.4, "Length": 5.0, "Category": "resident"},
                                  {"Mark": "P13", "Width": 2.4, "Length": 5.0, "Category": "visitor"}],
                          "total": 3},
    },
}

COMMENTS = """\
Department: Planning

C-005: The northern setback must be at least 3.0 m.

Department: Traffic

C-001: Increase parking space P12 width to 2.50 m.
"""


@pytest.fixture
def split_project(tmp_path):
    """A project whose two disciplines live in two different tools."""
    project = tmp_path / "project"
    (project / "municipal_comments").mkdir(parents=True)
    (project / "municipal_comments" / "comments.md").write_text(COMMENTS, encoding="utf-8")

    served = tmp_path / "arch_open_in_host.json"
    served.write_text(json.dumps(ARCH_MODEL), encoding="utf-8")
    host = serve(served, port=_free_port())

    traffic_path = tmp_path / "traffic.json"
    traffic_path.write_text(json.dumps(TRAFFIC_MODEL), encoding="utf-8")

    yield project, f"http://127.0.0.1:{host.server_address[1]}", traffic_path
    host.shutdown()


def _run(project, host_base, traffic_path, output_dir):
    return Orchestrator(
        project, mode="consultation", responder=ScriptedResponder({"C-005": "approve"}),
        output_dir=output_dir,
        sources=[f"revit://{host_base.removeprefix('http://')}", str(traffic_path)],
    ).run()


def test_one_run_edits_both_tools(split_project, tmp_path):
    project, host_base, traffic_path = split_project
    result = _run(project, host_base, traffic_path, tmp_path / "out")

    adapters = {change.adapter for change in result.changes}
    assert adapters == {"revit", "json"}, adapters

    resolved = {item.comment_id: item.status for item in result.validation.comments}
    assert resolved["C-005"] is CommentStatus.RESOLVED   # measured through the Revit host
    assert resolved["C-001"] is CommentStatus.RESOLVED   # measured through the traffic file

    # each comment's evidence really came from measuring its own tool
    by_id = {item.comment_id: item for item in result.validation.comments}
    assert by_id["C-005"].evidence["metric"] == "setback"
    assert by_id["C-001"].evidence["metric"] == "width"


def test_the_traffic_file_on_disk_is_never_overwritten(split_project, tmp_path):
    """The rule that protects the primary's original file protects every source."""
    project, host_base, traffic_path = split_project
    before = traffic_path.read_text(encoding="utf-8")
    _run(project, host_base, traffic_path, tmp_path / "out")
    assert traffic_path.read_text(encoding="utf-8") == before


def test_the_secondary_source_is_snapshotted_into_the_version(split_project, tmp_path):
    project, host_base, traffic_path = split_project
    result = _run(project, host_base, traffic_path, tmp_path / "out")

    snapshot = project / "versions" / result.version / f"project_{result.version}_json.json"
    assert snapshot.exists()
    model = json.loads(snapshot.read_text(encoding="utf-8"))
    widths = {e["id"]: e["geometry"]["w"] for e in model["elements"] if e["type"] == "parking"}
    assert widths["parking_p12"] == 2.5


def test_each_host_is_asked_to_highlight_only_its_own_elements(split_project, tmp_path):
    project, host_base, traffic_path = split_project
    _run(project, host_base, traffic_path, tmp_path / "out")

    change_set = json.loads((tmp_path / "out" / "change_set.json").read_text(encoding="utf-8"))
    assert change_set["multi_source"] is True
    assert set(change_set["highlight_by_source"]["revit"]) == {"building"}
    assert "parking_p12" in change_set["highlight_by_source"]["json"]
    assert set(change_set["highlight_by_source"]["revit"]).isdisjoint(
        change_set["highlight_by_source"]["json"])


def test_the_change_set_names_every_source_the_run_touched(split_project, tmp_path):
    project, host_base, traffic_path = split_project
    result = _run(project, host_base, traffic_path, tmp_path / "out")

    adapters = {entry["adapter"] for entry in result.change_set["sources"]}
    assert adapters == {"revit", "json"}


def test_a_comment_no_open_tool_can_reach_is_not_silently_dropped(tmp_path):
    """Traffic comment, but only the architecture tool is open: an honest gap."""
    project = tmp_path / "project"
    (project / "municipal_comments").mkdir(parents=True)
    (project / "municipal_comments" / "comments.md").write_text(
        "Department: Traffic\n\nC-001: Increase parking space P12 width to 2.50 m.\n",
        encoding="utf-8")
    served = tmp_path / "arch.json"
    served.write_text(json.dumps(ARCH_MODEL), encoding="utf-8")
    host = serve(served, port=_free_port())
    try:
        result = Orchestrator(
            project, mode="autonomous", responder=auto_approve, output_dir=tmp_path / "out",
            sources=[f"revit://127.0.0.1:{host.server_address[1]}"],
        ).run()
    finally:
        host.shutdown()

    # No open source actually holds a parking element, so the only tool open
    # (the architecture host) honestly reports it cannot measure this - it is
    # never silently marked resolved, and it is never dropped from the count.
    item = next(c for c in result.validation.comments if c.comment_id == "C-001")
    assert item.status is CommentStatus.REQUIRES_HUMAN_REVIEW
    assert result.context.open_items and any(
        entry["ref"] == "C-001" for entry in result.context.open_items)


# ----------------------------------------------------------------------
# two live hosts at once - Revit and a second tool, both genuinely edited
# ----------------------------------------------------------------------
def test_a_run_edits_two_live_hosts_at_once(tmp_path):
    """Not a file plus a host - two separate live tools in the same run."""
    project = tmp_path / "project"
    (project / "municipal_comments").mkdir(parents=True)
    (project / "municipal_comments" / "comments.md").write_text(COMMENTS, encoding="utf-8")

    arch_served = tmp_path / "arch_open_in_revit.json"
    arch_served.write_text(json.dumps(ARCH_MODEL), encoding="utf-8")
    arch_host = serve(arch_served, port=_free_port())

    traffic_served = tmp_path / "traffic_open_in_autocad.json"
    traffic_served.write_text(json.dumps(TRAFFIC_MODEL), encoding="utf-8")
    traffic_host = serve(traffic_served, port=_free_port())

    try:
        result = Orchestrator(
            project, mode="consultation", responder=ScriptedResponder({"C-005": "approve"}),
            output_dir=tmp_path / "out",
            sources=[f"revit://127.0.0.1:{arch_host.server_address[1]}",
                    f"autocad://127.0.0.1:{traffic_host.server_address[1]}"],
        ).run()

        assert {change.adapter for change in result.changes} == {"revit", "dwg"}
        resolved = {item.comment_id: item.status for item in result.validation.comments}
        assert resolved["C-005"] is CommentStatus.RESOLVED
        assert resolved["C-001"] is CommentStatus.RESOLVED

        # both live documents were genuinely edited - in the host, not on disk:
        # the seed file each host started from is untouched (SKILL.md 16 extends
        # to every live source, not only the primary).
        arch_seed = json.loads(arch_served.read_text(encoding="utf-8"))
        assert arch_seed["elements"][0]["geometry"]["y"] == 20.0
        traffic_seed = json.loads(traffic_served.read_text(encoding="utf-8"))
        seed_p12 = next(e for e in traffic_seed["elements"] if e["id"] == "parking_p12")
        assert seed_p12["geometry"]["w"] == 2.4

        arch_live = RevitDriver(f"http://127.0.0.1:{arch_host.server_address[1]}")
        assert arch_live.get_element("building")["geometry"]["y"] == 19.6
        traffic_live = DwgDriver(f"http://127.0.0.1:{traffic_host.server_address[1]}")
        assert traffic_live.get_element("parking_p12")["geometry"]["w"] == 2.5
    finally:
        arch_host.shutdown()
        traffic_host.shutdown()
