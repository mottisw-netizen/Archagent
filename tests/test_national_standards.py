"""National (Israeli) planning-regulation defaults, wired into the ledger.

Proves the actual gap PERMIT_LEARNING_MISSION.md's owner asked to close:
before this, `archagent.traffic.parking.validate_space` existed and was
correct but was never called outside its own tests - a parking space could
be genuinely undersized with no municipal comment ever mentioning it, and
Archagent would never catch it. These tests prove the national minimum is
now checked unconditionally, from the drawing model alone.
"""

from __future__ import annotations

import pytest

from archagent.constraints import ConstraintLedger, evaluate_constraint
from archagent.drawing.json_model import JSONModelDriver
from archagent.models import Priority
from archagent.national_standards import (
    DRIVEWAY_MIN_WIDTH_ONE_WAY,
    DRIVEWAY_MIN_WIDTH_TWO_WAY,
    PARKING_MIN_LENGTH,
    PARKING_MIN_WIDTH,
    PARKING_MIN_WIDTH_ACCESSIBLE,
    derive_national_constraints,
)

SITE = {"plot": {"kind": "rect", "x": 0.0, "y": 0.0, "w": 40.0, "h": 30.0}}


def _driver(elements):
    return JSONModelDriver({
        "project_id": "p", "units": "m", "north": "+y", "site": SITE,
        "sheets": [], "elements": elements, "schedules": {},
    })


def _parking(element_id, w, h, category=None):
    props = {"width_axis": "x"}
    if category:
        props["category"] = category
    return {"id": element_id, "type": "parking", "label": element_id,
           "geometry": {"kind": "rect", "x": 0.0, "y": 0.0, "w": w, "h": h},
           "properties": props}


def _driveway(element_id, w, h, direction=None):
    props = {"width_axis": "x"}
    if direction:
        props["direction"] = direction
    return {"id": element_id, "type": "driveway", "label": element_id,
           "geometry": {"kind": "rect", "x": 0.0, "y": 0.0, "w": w, "h": h},
           "properties": props}


def test_an_undersized_space_is_flagged_even_with_no_comment_at_all():
    """The core gap this closes: no comment, no explicit project requirement -
    just a real space that is narrower than the law allows."""
    driver = _driver([_parking("p1", 2.0, 5.0)])
    ledger = ConstraintLedger()
    created = derive_national_constraints(driver, ledger)

    width_constraints = [c for c in created if c.test.metric == "width"]
    assert len(width_constraints) == 1
    constraint = width_constraints[0]
    assert constraint.test.value == pytest.approx(PARKING_MIN_WIDTH.value)

    result = evaluate_constraint(driver, constraint)
    assert result.status == "fail"


def test_an_unconfirmed_standard_is_sourced_and_prioritised_honestly():
    """PARKING_MIN_WIDTH's exact statutory origin was checked directly and
    disproven for the regulation it was first (wrongly) cited to - see the
    module docstring and docs/NATIONAL_VS_LOCAL_STANDARDS.md. It stays wired
    as a real, sensible default, but must never claim "Planning Regulation"
    rank/CRITICAL priority it has not earned - that would be exactly the kind
    of fabricated-confidence citation this whole survey exists to avoid."""
    assert PARKING_MIN_WIDTH.basis == "unconfirmed"
    driver = _driver([_parking("p1", 2.0, 5.0)])
    ledger = ConstraintLedger()
    created = derive_national_constraints(driver, ledger)
    constraint = next(c for c in created if c.test.metric == "width")
    assert constraint.source == "Reference"
    assert constraint.priority is Priority.MEDIUM
    assert constraint.confidence < 1.0


def test_a_guideline_standard_ranks_above_unconfirmed_but_below_statute():
    """DRIVEWAY_MIN_WIDTH_* was confirmed by directly reading a real ministry
    guideline PDF - real and citable, but advisory, not a Knesset statute.
    It must sit honestly between the two: never CRITICAL like a proven
    statute, but never lumped in with a merely-plausible unconfirmed guess
    either."""
    assert DRIVEWAY_MIN_WIDTH_ONE_WAY.basis == "guideline"
    driver = _driver([_driveway("d1", 2.0, 10.0)])
    ledger = ConstraintLedger()
    created = derive_national_constraints(driver, ledger)
    constraint = next(c for c in created if c.test.metric == "width")
    assert constraint.source == "Planning Guideline"
    assert constraint.confidence == pytest.approx(1.0)  # the text WAS read directly


def test_driveway_width_uses_the_one_way_floor_when_direction_is_unknown():
    driver = _driver([_driveway("d1", 4.0, 10.0)])
    ledger = ConstraintLedger()
    created = derive_national_constraints(driver, ledger)
    constraint = next(c for c in created if c.test.metric == "width")
    assert constraint.test.value == pytest.approx(DRIVEWAY_MIN_WIDTH_ONE_WAY.value)
    assert evaluate_constraint(driver, constraint).status == "pass"  # 4.0 >= 3.50


def test_a_two_way_driveway_is_checked_against_the_stricter_figure():
    driver = _driver([_driveway("d1", 4.0, 10.0, direction="two_way")])
    ledger = ConstraintLedger()
    created = derive_national_constraints(driver, ledger)
    constraint = next(c for c in created if c.test.metric == "width")
    assert constraint.test.value == pytest.approx(DRIVEWAY_MIN_WIDTH_TWO_WAY.value)
    assert evaluate_constraint(driver, constraint).status == "fail"  # 4.0 < 5.80


def test_driveways_are_not_checked_for_length_the_way_parking_is():
    driver = _driver([_driveway("d1", 4.0, 10.0)])
    ledger = ConstraintLedger()
    created = derive_national_constraints(driver, ledger)
    assert not any(c.test.metric == "length" for c in created)


def test_a_space_that_meets_the_national_minimum_passes():
    driver = _driver([_parking("p1", 2.4, 5.0)])
    ledger = ConstraintLedger()
    created = derive_national_constraints(driver, ledger)
    results = [evaluate_constraint(driver, c) for c in created]
    assert all(r.status == "pass" for r in results)


def test_accessible_parking_uses_the_stricter_national_width():
    driver = _driver([_parking("p1", 2.4, 5.0, category="accessible")])
    ledger = ConstraintLedger()
    created = derive_national_constraints(driver, ledger)
    width_constraint = next(c for c in created if c.test.metric == "width")
    assert width_constraint.test.value == pytest.approx(PARKING_MIN_WIDTH_ACCESSIBLE.value)

    result = evaluate_constraint(driver, width_constraint)
    assert result.status == "fail"  # 2.4 m is below the 3.0 m accessible minimum


def test_length_is_checked_against_the_safe_floor():
    driver = _driver([_parking("p1", 2.4, 4.0)])
    ledger = ConstraintLedger()
    created = derive_national_constraints(driver, ledger)
    length_constraint = next(c for c in created if c.test.metric == "length")
    assert length_constraint.test.value == pytest.approx(PARKING_MIN_LENGTH.value)
    assert evaluate_constraint(driver, length_constraint).status == "fail"


def test_non_parking_elements_are_left_alone():
    driver = _driver([{"id": "w1", "type": "wall", "label": "W1",
                       "geometry": {"kind": "rect", "x": 0.0, "y": 0.0, "w": 0.1, "h": 3.0}}])
    ledger = ConstraintLedger()
    assert derive_national_constraints(driver, ledger) == []


def test_an_unmeasurable_element_is_skipped_not_crashed_on():
    """A parking element declared without geometry at all must not blow up
    the whole pass - the same 'skip what cannot be measured' rule every
    other constraint-deriving function in this codebase follows."""
    driver = _driver([{"id": "p1", "type": "parking", "label": "P1", "properties": {}}])
    ledger = ConstraintLedger()
    assert derive_national_constraints(driver, ledger) == []


def test_every_created_constraint_names_its_source_honestly():
    """Every rule text must say where its number comes from, confirmed or
    not - the difference is source/priority (checked above), never whether
    a citation is present at all."""
    driver = _driver([_parking("p1", 2.0, 4.0)])
    ledger = ConstraintLedger()
    created = derive_national_constraints(driver, ledger)
    assert created  # sanity: this test project's fixture actually triggers checks
    for constraint in created:
        assert "ת\"י 1918" in constraint.rule or "תקנות" in constraint.rule
