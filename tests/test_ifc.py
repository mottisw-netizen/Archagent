"""Minimal read-only IFC (STEP/SPF) entity extraction.

Scope, matching the module's own docstring: entity type + GlobalId + Name
only, no geometry, no property sets, no round-trip, no live adapter wiring.
"""

from __future__ import annotations

from archagent.drawing.ifc_model import read_ifc

SAMPLE_IFC = """\
ISO-10303-21;
HEADER;
FILE_DESCRIPTION((''),'2;1');
FILE_NAME('','',(''),(''),'','','');
FILE_SCHEMA(('IFC4'));
ENDSEC;
DATA;
#1=IFCWALL('1a2b3c4d5e6f7g8h9i0jkl',#2,'Basement Wall','Exterior wall',$,#10,#20,$,$);
#2=IFCOWNERHISTORY($,$,$,$,$,$,$,0);
#3=IFCDOOR('2a2b3c4d5e6f7g8h9i0jkl',#2,'Main Entrance Door',$,$,#11,#21,$,2.1,0.9);
#4=IFCSPACE('3a2b3c4d5e6f7g8h9i0jkl',#2,'Living Room',$,$,#12,#22,$,.ELEMENT.,.INTERNAL.,$);
#5=IFCFASTENER('4a2b3c4d5e6f7g8h9i0jkl',#2,'Some Fastener',$,$,#13,#23,$);
ENDSEC;
END-ISO-10303-21;
"""

#: The same wall record, split across two physical lines - STEP records may
#: legally wrap, and the reader must join them before parsing.
SAMPLE_IFC_MULTILINE = """\
ISO-10303-21;
HEADER;
ENDSEC;
DATA;
#1=IFCWALL('1a2b3c4d5e6f7g8h9i0jkl',#2,'Basement Wall',
'Exterior wall',$,#10,#20,$,$);
ENDSEC;
"""


def test_reads_wall_door_and_space_with_global_id_and_name(tmp_path):
    path = tmp_path / "sample.ifc"
    path.write_text(SAMPLE_IFC, encoding="utf-8")
    model = read_ifc(path)

    by_id = {e["id"]: e for e in model["elements"]}
    assert by_id["#1"]["type"] == "wall"
    assert by_id["#1"]["label"] == "Basement Wall"
    assert by_id["#1"]["properties"]["global_id"] == "1a2b3c4d5e6f7g8h9i0jkl"
    assert by_id["#1"]["properties"]["ifc_type"] == "IFCWALL"

    assert by_id["#3"]["type"] == "door"
    assert by_id["#3"]["label"] == "Main Entrance Door"

    assert by_id["#4"]["type"] == "room"
    assert by_id["#4"]["label"] == "Living Room"


def test_no_geometry_is_ever_produced(tmp_path):
    """This reader never claims a geometry it did not interpret."""
    path = tmp_path / "sample.ifc"
    path.write_text(SAMPLE_IFC, encoding="utf-8")
    model = read_ifc(path)
    for element in model["elements"]:
        assert "geometry" not in element


def test_unmapped_ifc_types_are_skipped_not_guessed(tmp_path):
    path = tmp_path / "sample.ifc"
    path.write_text(SAMPLE_IFC, encoding="utf-8")
    model = read_ifc(path)
    types = {e["properties"]["ifc_type"] for e in model["elements"]}
    assert "IFCFASTENER" not in types  # no mapping for it - skipped, not "generic"
    assert "IFCOWNERHISTORY" not in types  # not even a product/element


def test_multiline_step_records_are_joined_before_parsing(tmp_path):
    path = tmp_path / "sample.ifc"
    path.write_text(SAMPLE_IFC_MULTILINE, encoding="utf-8")
    model = read_ifc(path)
    assert len(model["elements"]) == 1
    assert model["elements"][0]["label"] == "Basement Wall"


MIXED_CASE_IFC = """\
ISO-10303-21;
Data;
#1=IfcWall('1a2b3c4d5e6f7g8h9i0jkl',#2,'Basement Wall',$,$,#10,#20,$,$);
#2=ifcwindow('2a2b3c4d5e6f7g8h9i0jkl',#3,'Kitchen Window',$,$,#11,#21,$,1.2,0.9);
Endsec;
"""


def test_step_keywords_are_case_insensitive(tmp_path):
    """STEP (ISO 10303-21) keywords are case-insensitive and real exporters
    differ - reading only uppercase would silently return an empty model for
    a perfectly valid file."""
    path = tmp_path / "mixed.ifc"
    path.write_text(MIXED_CASE_IFC, encoding="utf-8")
    model = read_ifc(path)
    by_id = {e["id"]: e for e in model["elements"]}
    assert by_id["#1"]["type"] == "wall"
    assert by_id["#2"]["type"] == "window"
    # the recorded ifc_type is normalised, so callers can compare it directly
    assert by_id["#2"]["properties"]["ifc_type"] == "IFCWINDOW"


def test_empty_file_gives_no_elements(tmp_path):
    path = tmp_path / "empty.ifc"
    path.write_text("ISO-10303-21;\nEND-ISO-10303-21;\n", encoding="utf-8")
    model = read_ifc(path)
    assert model["elements"] == []
