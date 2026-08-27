"""The bundled Petah Tikva authority profile (spec §4)."""

from __future__ import annotations

import pytest

yaml = pytest.importorskip("yaml")

from archagent.authority import petah_tikva  # noqa: E402


def test_profile_loads_departments_and_metadata():
    authority = petah_tikva.load(refresh=True)
    assert authority.name == "petah_tikva"
    assert authority.language == "he"
    assert authority.rtl is True
    assert "roads_drainage" in authority.departments
    assert "architecture" in authority.departments


def test_discipline_routing():
    authority = petah_tikva.load()
    assert authority.discipline_for("roads_drainage") == "civil"
    assert authority.discipline_for("forestry") == "landscape"
    assert authority.discipline_for("unknown_department") == "unknown_department"


def test_evidence_requirements_carry_stage_and_role():
    authority = petah_tikva.load()
    hydro = authority.evidence_for("hydrologic_report")
    assert hydro is not None
    assert hydro["required_stage"] == "design_control"
    assert hydro["professional_role"] == "hydrologist"
    assert authority.evidence_for("does_not_exist") is None


def test_geometry_examples_are_sourced_project_data_not_universal_rules():
    authority = petah_tikva.load()
    ids = {item["id"] for item in authority.geometry_examples}
    assert "common_landscaping_share" in ids
    assert "municipal_drainage_setback" in ids
    setback = next(item for item in authority.geometry_examples
                   if item["id"] == "municipal_drainage_setback")
    assert setback["value"] == 2.0
    assert setback["conditional"] is True


def test_comment_patterns_match_the_bundled_test_cases():
    authority = petah_tikva.load()
    cases_path = petah_tikva.PROFILE_DIR / "test_cases" / "examples.yaml"
    cases = yaml.safe_load(cases_path.read_text(encoding="utf-8"))
    assert cases
    for case in cases:
        matches = authority.matches_pattern(case["text"])
        assert case["expected_pattern"] in matches, case["text"]


def test_terminology_dictionary_has_key_drainage_terms():
    authority = petah_tikva.load()
    assert authority.terminology["ניקוז"] == "drainage"
    assert authority.terminology["שוחת השהייה"] == "detention_chamber"
