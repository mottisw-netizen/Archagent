"""Real cross-source geometric conflict detection (spec §12, §14, §44).

A civil drawing's municipal drainage line and an architectural model's
basement wall live in two different files, opened by two different
adapters/drivers - there is no single driver that holds both, so nothing in
:mod:`archagent.graph` can measure a distance between them (its `discipline`
nodes only record that civil *can* constrain architecture, never whether it
actually does - see SKILL.md §25.11). A real project positions every source
in one shared site coordinate system, though, so the two elements' plain
geometry - `x`, `y`, `w`, `h` - is directly comparable across drivers even
though no single `DrawingDriver.calculate_distance` call spans them.

This is centre-to-centre distance in that shared frame - coarser than a
driver's own edge-to-edge `calculate_distance` within one model, but the only
measurement available across two independent files with no shared API.
Nothing here fabricates a conflict: a rule with no matching elements in
either scope produces no violation, and only a real coordinate gap smaller
than the rule's clearance is reported.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .models import Serialisable

Point = tuple[float, float]


@dataclass
class CrossSourceRule(Serialisable):
    source_type: str
    target_type: str
    min_clearance: float
    description: str = ""


@dataclass
class CrossSourceViolation(Serialisable):
    source_scope: str
    source_element: str
    target_scope: str
    target_element: str
    distance: float
    required: float
    description: str = ""


#: The Petah Tikva record's own worked example (spec §12, §14): a municipal
#: drainage line must keep 2 m from a wall unless a diversion solution is
#: submitted - the conditional part of that rule is
#: archagent.conditional.ConditionalRequirement's job, not this module's;
#: this only measures the raw distance.
DEFAULT_RULES = [
    CrossSourceRule(source_type="municipal_drain", target_type="wall", min_clearance=2.0,
                   description="municipal drainage line separation (spec §12)"),
]


def _center(geometry: dict) -> Point | None:
    if not geometry:
        return None
    if geometry.get("kind") == "rect" and "x" in geometry and "y" in geometry:
        return (geometry["x"] + geometry.get("w", 0.0) / 2.0,
                geometry["y"] + geometry.get("h", 0.0) / 2.0)
    if "x" in geometry and "y" in geometry:
        return (geometry["x"], geometry["y"])
    return None


def check_cross_source_clearance(scopes: list, rules: list[CrossSourceRule] = DEFAULT_RULES
                                 ) -> list[CrossSourceViolation]:
    """``scopes`` is a list of objects with ``.adapter_name`` and ``.driver``
    (an opened project's :class:`~archagent.adapters.registry.OpenSource`
    list) - every driver that exposes ``elements()`` is checked against
    every other, for each rule, in both directions is unnecessary since each
    unordered pair of scopes is only checked once.
    """
    violations: list[CrossSourceViolation] = []
    for i, scope_a in enumerate(scopes):
        elements_a = getattr(scope_a.driver, "elements", None)
        if scope_a.driver is None or elements_a is None:
            continue
        for scope_b in scopes[i + 1:]:
            elements_b = getattr(scope_b.driver, "elements", None)
            if scope_b.driver is None or elements_b is None:
                continue
            violations.extend(_check_pair(scope_a, elements_a(), scope_b, elements_b(), rules))
    return violations


def _check_pair(scope_a, index_a: list[dict], scope_b, index_b: list[dict],
                rules: list[CrossSourceRule]) -> list[CrossSourceViolation]:
    found = []
    for rule in rules:
        for forward, backward in ((rule.source_type, rule.target_type),
                                  (rule.target_type, rule.source_type)):
            sources = [e for e in index_a if e.get("type") == forward]
            targets = [e for e in index_b if e.get("type") == backward]
            for element_a in sources:
                center_a = _center(element_a.get("geometry", {}))
                if center_a is None:
                    continue
                for element_b in targets:
                    center_b = _center(element_b.get("geometry", {}))
                    if center_b is None:
                        continue
                    distance = math.hypot(center_a[0] - center_b[0], center_a[1] - center_b[1])
                    if distance < rule.min_clearance:
                        found.append(CrossSourceViolation(
                            source_scope=scope_a.adapter_name, source_element=element_a["id"],
                            target_scope=scope_b.adapter_name, target_element=element_b["id"],
                            distance=round(distance, 3), required=rule.min_clearance,
                            description=rule.description))
    return found
