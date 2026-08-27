"""The headless DWG path: a plain .dxf file, no CAD seat anywhere.

DxfModelDriver parses a DXF into the same model shape JSONModelDriver already
uses and then *is* one - every query, measurement and mutation is the
reference implementation, already fully tested elsewhere. What is new here,
and what these tests actually cover: reading a real DXF into that shape,
writing mutations back into real entities, and the adapter/driver seams
(suffix detection, the ODA-converter-missing refusal, versioning in the
driver's own format).
"""

import json

import pytest

ezdxf = pytest.importorskip("ezdxf")

from archagent.adapters import DwgAdapter, SourceRef  # noqa: E402
from archagent.consult import auto_approve  # noqa: E402
from archagent.drawing.api import DrawingAPIError, NotAuthorised  # noqa: E402
from archagent.drawing.dxf_model import DxfModelDriver, read_dxf  # noqa: E402
from archagent.orchestrator import Orchestrator  # noqa: E402


def _drawing(insunits=6):
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = insunits
    msp = doc.modelspace()
    p11 = msp.add_lwpolyline([(6.0, 2.0), (8.4, 2.0), (8.4, 7.0), (6.0, 7.0)],
                             close=True, dxfattribs={"layer": "A-PARK"})
    p11.set_xdata("ARCHAGENT", [(1000, json.dumps({"label": "P11"}))])
    p12 = msp.add_lwpolyline([(8.5, 2.0), (10.9, 2.0), (10.9, 7.0), (8.5, 7.0)],
                             close=True, dxfattribs={"layer": "A-PARK"})
    p12.set_xdata("ARCHAGENT", [(1000, json.dumps({"label": "P12"}))])
    dim = msp.add_text("2.40", dxfattribs={"insert": (8.5, 1.2), "layer": "A-DIMS"})
    dim.set_xdata("ARCHAGENT", [(1000, json.dumps(
        {"label": "P12 width", "properties": {"measures": {"element_id": p12.dxf.handle,
                                                           "parameter": "width"}}}))])
    return doc, p11, p12, dim


@pytest.fixture
def dxf_file(tmp_path):
    doc, p11, p12, dim = _drawing()
    path = tmp_path / "traffic.dxf"
    doc.saveas(path)
    return path, p11.dxf.handle, p12.dxf.handle, dim.dxf.handle


# ----------------------------------------------------------------------
# parsing
# ----------------------------------------------------------------------
def test_layer_name_gives_a_category_with_no_tagging_at_all(tmp_path):
    doc = ezdxf.new("R2018")
    doc.modelspace().add_lwpolyline(
        [(0, 0), (20, 0), (20, 7), (0, 7)], close=True, dxfattribs={"layer": "A-BLDG"})
    path = tmp_path / "arch.dxf"
    doc.saveas(path)
    _, model = read_dxf(path)
    assert model["elements"][0]["type"] == "building"


@pytest.mark.parametrize("layer,expected_type", [
    ("C-DRAIN-MUNI", "municipal_drain"),
    ("C-DRAIN-CHAMBER", "drainage_chamber"),
    ("C-DRAIN-MANHOLE", "catch_basin"),
    ("C-DRAIN-PIPE", "drainage_pipe"),
    ("C-CURB", "curb"),
    ("A-RAMP", "ramp"),
    ("L-TREE", "tree"),
    ("L-PLNT", "landscape_zone"),
])
def test_civil_and_landscape_layer_names_resolve_to_semantic_types(tmp_path, layer, expected_type):
    doc = ezdxf.new("R2018")
    doc.modelspace().add_lwpolyline(
        [(0, 0), (1, 0), (1, 1), (0, 1)], close=True, dxfattribs={"layer": layer})
    path = tmp_path / "civil.dxf"
    doc.saveas(path)
    _, model = read_dxf(path)
    assert model["elements"][0]["type"] == expected_type


def test_municipal_drain_keyword_wins_over_the_more_generic_drain_keyword(tmp_path):
    """LAYER_CATEGORIES checks entries in order - MUNI must be listed before
    the more general DRAIN so a combined layer name still resolves specifically."""
    doc = ezdxf.new("R2018")
    doc.modelspace().add_lwpolyline(
        [(0, 0), (1, 0), (1, 1), (0, 1)], close=True, dxfattribs={"layer": "C-DRAIN-MUNI-LINE"})
    path = tmp_path / "civil.dxf"
    doc.saveas(path)
    _, model = read_dxf(path)
    assert model["elements"][0]["type"] == "municipal_drain"


def test_xdata_tag_overrides_the_layer_guess(dxf_file):
    path, p11, p12, dim = dxf_file
    _, model = read_dxf(path)
    by_id = {e["id"]: e for e in model["elements"]}
    assert by_id[p12]["label"] == "P12"
    assert by_id[dim]["type"] == "text"       # TEXT entities are typed regardless of layer


def test_insunits_is_read_into_metres(tmp_path):
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 4   # millimetres
    doc.modelspace().add_lwpolyline(
        [(0, 0), (2400, 0), (2400, 5000), (0, 5000)], close=True, dxfattribs={"layer": "A-PARK"})
    path = tmp_path / "mm.dxf"
    doc.saveas(path)
    _, model = read_dxf(path)
    box = model["elements"][0]["geometry"]
    assert box["w"] == pytest.approx(2.4) and box["h"] == pytest.approx(5.0)


# ----------------------------------------------------------------------
# the driver: query, measure, mutate, save
# ----------------------------------------------------------------------
def test_the_driver_measures_what_the_reference_driver_measures(dxf_file):
    path, p11, p12, dim = dxf_file
    driver = DxfModelDriver(path)
    assert driver.measure({"element_id": p12}, "width").value == pytest.approx(2.4)


def test_mutation_without_an_approved_plan_is_refused(dxf_file):
    path, p11, p12, dim = dxf_file
    driver = DxfModelDriver(path)
    with pytest.raises(NotAuthorised):
        driver.resize_element(p12, "width", 2.5)


def test_a_resize_is_written_back_into_the_real_entity(dxf_file, tmp_path):
    path, p11, p12, dim = dxf_file
    driver = DxfModelDriver(path)
    with driver.authorised("PLAN-1"):
        record = driver.resize_element(p12, "width", 2.5)
    assert (record.before, record.after) == (2.4, 2.5)

    out = tmp_path / "v2.dxf"
    driver.save_as(out)
    doc2 = ezdxf.readfile(out)
    entity = doc2.entitydb.get(p12)
    xs = [point[0] for point in entity.get_points("xy")]
    assert max(xs) - min(xs) == pytest.approx(2.5)
    # the original file is never touched - only the new version is
    assert ezdxf.readfile(path).entitydb.get(p12).get_points("xy")[1][0] == pytest.approx(10.9)


def test_a_deleted_element_is_gone_from_the_saved_file(dxf_file, tmp_path):
    path, p11, p12, dim = dxf_file
    driver = DxfModelDriver(path)
    with driver.authorised("PLAN-1"):
        driver.delete_element(p11)
    out = tmp_path / "v2.dxf"
    driver.save_as(out)
    assert ezdxf.readfile(out).entitydb.get(p11) is None


def test_the_sandbox_never_writes_to_the_dxf_document(dxf_file):
    path, p11, p12, dim = dxf_file
    driver = DxfModelDriver(path)
    with driver.sandbox() as sandbox:
        with sandbox.authorised("PLAN-1"):
            sandbox.resize_element(p12, "width", 9.0)
        assert sandbox.get_element(p12)["geometry"]["w"] == 9.0
    assert driver.get_element(p12)["geometry"]["w"] == 2.4


# ----------------------------------------------------------------------
# adapter
# ----------------------------------------------------------------------
def test_the_adapter_opens_a_dxf_file_directly(dxf_file):
    path, p11, p12, dim = dxf_file
    status = DwgAdapter().status(SourceRef.parse(str(path)))
    assert status.available and "edit" in status.capabilities
    driver = DwgAdapter().open(SourceRef.parse(str(path)))
    assert isinstance(driver, DxfModelDriver)


def test_a_dwg_file_is_refused_without_the_oda_converter(tmp_path):
    path = tmp_path / "traffic.dwg"
    path.write_bytes(b"not a real dwg")   # status must not need to read it
    status = DwgAdapter().status(SourceRef.parse(str(path)))
    assert not status.available and "File Converter" in status.reason
    with pytest.raises(DrawingAPIError):
        DwgAdapter().open(SourceRef.parse(str(path)))


# ----------------------------------------------------------------------
# the whole pipeline, on a DXF as the only source
# ----------------------------------------------------------------------
def test_a_full_run_versions_in_dxf_not_json(tmp_path, dxf_file):
    path, p11, p12, dim = dxf_file
    project = tmp_path / "project"
    (project / "municipal_comments").mkdir(parents=True)
    (project / "municipal_comments" / "comments.md").write_text(
        "Department: Traffic\n\nC-001: Increase parking space P12 width to 2.50 m.\n",
        encoding="utf-8")

    result = Orchestrator(project, mode="autonomous", responder=auto_approve,
                          output_dir=tmp_path / "out",
                          sources=[str(path)]).run()

    assert result.context.source_format == "DWG"
    assert any(c.element_id == p12 for c in result.changes)
    version_dir = project / "versions" / result.version
    assert (version_dir / f"project_{result.version}.dxf").exists()
    assert not (version_dir / f"project_{result.version}.json").exists()
