"""Real cross-source geometric conflict detection (spec §12, §14, §44).

Proves the thing archagent.graph's discipline nodes cannot: that a civil
drawing's municipal drainage line and an architecture drawing's basement
wall - two different files, two different drivers - can still be checked
against each other for real, using their shared site coordinates.
"""

from __future__ import annotations

from dataclasses import dataclass

from archagent.cross_source import CrossSourceRule, check_cross_source_clearance
from archagent.drawing.json_model import JSONModelDriver

SITE = {"plot": {"kind": "rect", "x": 0.0, "y": 0.0, "w": 40.0, "h": 30.0}}


def _model(elements):
    return {"project_id": "p", "units": "m", "north": "+y", "site": SITE,
           "sheets": [], "elements": elements, "schedules": {}}


@dataclass
class _Scope:
    adapter_name: str
    driver: object


def test_close_drainage_line_and_wall_across_two_drivers_is_detected():
    civil_driver = JSONModelDriver(_model([
        {"id": "drain-1", "type": "municipal_drain", "label": "municipal drain",
         "geometry": {"kind": "rect", "x": 10.0, "y": 10.0, "w": 0.2, "h": 0.2}},
    ]))
    architecture_driver = JSONModelDriver(_model([
        {"id": "basement-wall", "type": "wall", "label": "basement wall",
         "geometry": {"kind": "rect", "x": 10.5, "y": 10.0, "w": 0.2, "h": 0.2}},
    ]))
    scopes = [_Scope("dwg", civil_driver), _Scope("revit", architecture_driver)]

    violations = check_cross_source_clearance(scopes)
    assert len(violations) == 1
    violation = violations[0]
    assert violation.source_element == "drain-1"
    assert violation.target_element == "basement-wall"
    assert violation.distance < 2.0
    assert violation.required == 2.0


def test_far_apart_elements_are_not_flagged():
    civil_driver = JSONModelDriver(_model([
        {"id": "drain-1", "type": "municipal_drain",
         "geometry": {"kind": "rect", "x": 0.0, "y": 0.0, "w": 0.2, "h": 0.2}},
    ]))
    architecture_driver = JSONModelDriver(_model([
        {"id": "basement-wall", "type": "wall",
         "geometry": {"kind": "rect", "x": 20.0, "y": 20.0, "w": 0.2, "h": 0.2}},
    ]))
    scopes = [_Scope("dwg", civil_driver), _Scope("revit", architecture_driver)]
    assert check_cross_source_clearance(scopes) == []


def test_scope_order_does_not_matter():
    civil_driver = JSONModelDriver(_model([
        {"id": "drain-1", "type": "municipal_drain",
         "geometry": {"kind": "rect", "x": 10.0, "y": 10.0, "w": 0.2, "h": 0.2}},
    ]))
    architecture_driver = JSONModelDriver(_model([
        {"id": "basement-wall", "type": "wall",
         "geometry": {"kind": "rect", "x": 10.5, "y": 10.0, "w": 0.2, "h": 0.2}},
    ]))
    # architecture scope listed first this time
    scopes = [_Scope("revit", architecture_driver), _Scope("dwg", civil_driver)]
    violations = check_cross_source_clearance(scopes)
    assert len(violations) == 1
    assert violations[0].source_element == "basement-wall"
    assert violations[0].target_element == "drain-1"


def test_custom_rule_and_no_violation_when_element_type_absent():
    driver_a = JSONModelDriver(_model([
        {"id": "e-1", "type": "column", "geometry": {"kind": "rect", "x": 0, "y": 0, "w": 0.1, "h": 0.1}},
    ]))
    driver_b = JSONModelDriver(_model([
        {"id": "e-2", "type": "wall", "geometry": {"kind": "rect", "x": 0.1, "y": 0.1, "w": 0.1, "h": 0.1}},
    ]))
    scopes = [_Scope("a", driver_a), _Scope("b", driver_b)]
    rule = CrossSourceRule(source_type="column", target_type="wall", min_clearance=0.5,
                           description="column to wall clearance")
    violations = check_cross_source_clearance(scopes, rules=[rule])
    assert len(violations) == 1

    # A rule naming a type that appears in neither scope produces nothing -
    # never a fabricated conflict.
    empty_rule = CrossSourceRule(source_type="does_not_exist", target_type="also_missing",
                                 min_clearance=5.0)
    assert check_cross_source_clearance(scopes, rules=[empty_rule]) == []
