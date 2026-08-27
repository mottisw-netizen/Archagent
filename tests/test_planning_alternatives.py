"""Multi-disciplinary planning alternatives (spec §25/§45)."""

from __future__ import annotations

from archagent.planning_alternatives import drainage_setback_alternatives


def test_drainage_setback_alternatives_never_recommends_on_its_own():
    plan = drainage_setback_alternatives("REQ-1", setback_distance=1.2, required=2.0)
    assert plan.recommended_option_id == ""  # no automatic pick
    assert {a.option_id for a in plan.alternatives} == {"A", "B", "C"}


def test_option_a_impacts_architecture_structure_and_parking_not_civil_alone():
    plan = drainage_setback_alternatives("REQ-1", setback_distance=1.2)
    move_wall = plan.option("A")
    assert "architecture" in move_wall.impacted_disciplines
    assert "structure" in move_wall.impacted_disciplines
    assert move_wall.requires_authority_approval is False


def test_options_b_and_c_require_authority_approval_and_civil_ownership():
    plan = drainage_setback_alternatives("REQ-1", setback_distance=1.2)
    for option_id in ("B", "C"):
        option = plan.option(option_id)
        assert option.requires_authority_approval is True
        assert option.consultant_ownership == "roads/drainage consultant"


def test_deficit_is_computed_from_actual_vs_required_distance():
    plan = drainage_setback_alternatives("REQ-1", setback_distance=1.5, required=2.0)
    assert "0.50 m" in plan.option("A").description
