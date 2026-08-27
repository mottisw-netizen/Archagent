"""Traffic semantic model (Petah Tikva spec §6-8)."""

from __future__ import annotations

import math

import pytest

from archagent.traffic import (
    ParkingBalance,
    ParkingSpace,
    TurningPath,
    check_clearances,
    reconcile_balance,
    turning_path_points,
    validate_space,
    validate_turning_path,
)


# ----------------------------------------------------------------------
# parking space dimensions - distinct metrics, not one generic "width"
# ----------------------------------------------------------------------
def test_parking_space_dimension_and_clearance_are_independent_checks():
    space = ParkingSpace(space_id="P-17", width=2.3, length=5.0, clearance_to_column=0.4)
    result = validate_space(space, min_width=2.5, min_length=5.0,
                            min_clearance_to_column=0.5)
    assert not result.ok
    assert any("width" in issue for issue in result.issues)
    assert any("clearance to column" in issue for issue in result.issues)
    assert not any("length" in issue for issue in result.issues)


def test_compliant_space_has_no_issues():
    space = ParkingSpace(space_id="P-1", width=2.5, length=5.0, clearance_to_wall=0.6)
    result = validate_space(space, min_width=2.5, min_length=5.0, min_clearance_to_wall=0.5)
    assert result.ok


# ----------------------------------------------------------------------
# parking balance - never trust the table alone (spec §7.4)
# ----------------------------------------------------------------------
def test_balance_reconciliation_flags_table_vs_geometry_mismatch():
    balance = ParkingBalance(required_spaces=40, provided_spaces=40, accessible_spaces=3)
    actual = [ParkingSpace(space_id=f"P-{i}") for i in range(37)]
    actual[0].accessible = True
    reconciliation = reconcile_balance(balance, actual)
    assert not reconciliation.matches
    assert any("40 provided" in d and "37" in d for d in reconciliation.discrepancies)
    assert any("3 accessible" in d for d in reconciliation.discrepancies)


def test_balance_matches_when_geometry_agrees():
    balance = ParkingBalance(required_spaces=2, provided_spaces=2, accessible_spaces=1)
    actual = [ParkingSpace(space_id="P-1", accessible=True), ParkingSpace(space_id="P-2")]
    reconciliation = reconcile_balance(balance, actual)
    assert reconciliation.matches


# ----------------------------------------------------------------------
# columns/walls vs drive path edge - 0.5m / 0.75m (spec §7.3)
# ----------------------------------------------------------------------
def test_general_clearance_0_5m_from_drive_edge():
    edge = ((0.0, 0.0), (10.0, 0.0))
    report = check_clearances({"COL-1": (5.0, 0.3), "COL-2": (5.0, 0.8)}, edge, required=0.5)
    assert not report.ok
    violating = {v.element_id for v in report.violations}
    assert violating == {"COL-1"}


def test_service_level_2_clearance_0_75m():
    edge = ((0.0, 0.0), (10.0, 0.0))
    report = check_clearances({"COL-3": (5.0, 0.6)}, edge, required=0.75)
    assert not report.ok
    assert report.violations[0].distance == pytest.approx(0.6)
    assert report.violations[0].required == 0.75


# ----------------------------------------------------------------------
# turning radii - real geometry, not a text match (spec §7.2)
# ----------------------------------------------------------------------
def test_turning_path_points_form_valid_arcs():
    points = turning_path_points((0.0, 0.0), inner_radius=3.0, outer_radius=6.0,
                                 start_angle=0.0, end_angle=90.0, steps=4)
    assert len(points["inner"]) == len(points["outer"]) == 5
    for x, y in points["inner"]:
        assert math.hypot(x, y) == pytest.approx(3.0)
    for x, y in points["outer"]:
        assert math.hypot(x, y) == pytest.approx(6.0)


def test_turning_path_rejects_inverted_radii():
    with pytest.raises(ValueError):
        turning_path_points((0, 0), inner_radius=6.0, outer_radius=3.0)


def test_turning_radius_below_requirement_is_flagged():
    path = TurningPath(path_id="TP-1", inner_radius=3.0, outer_radius=5.5)
    result = validate_turning_path(path, required_inner_radius=3.5, required_outer_radius=6.0)
    assert not result.ok
    assert len(result.issues) == 2
