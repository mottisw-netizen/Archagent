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

The measurement itself is not re-implemented here: it is
:func:`archagent.drawing.geometry.clear_gap`, the same edge-to-edge clear
distance a single driver's own ``calculate_distance`` uses, applied to the
two elements' bounding boxes in the shared frame. Nothing here fabricates a
conflict: a rule with no matching elements in either scope produces no
violation, and only a real gap smaller than the rule's clearance is reported.
"""

from __future__ import annotations

from dataclasses import dataclass

from .drawing import geometry as geo
from .models import Serialisable


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


def _box(geometry: dict) -> geo.Box | None:
    """The element's bounding box, or ``None`` when its geometry is missing
    or of a kind :mod:`~archagent.drawing.geometry` cannot box."""
    if not geometry:
        return None
    try:
        return geo.box_from_dict(geometry)
    except (KeyError, TypeError, ValueError):
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
        # Each scope holds only its own discipline's elements, so a rule has
        # to be tried both ways round - the drain may be in either file. A
        # rule whose two types are the same would make the second pass
        # identical to the first, reporting (and opening an item for) every
        # violation twice, so it is run once.
        orientations = [(rule.source_type, rule.target_type)]
        if rule.source_type != rule.target_type:
            orientations.append((rule.target_type, rule.source_type))
        for forward, backward in orientations:
            sources = [e for e in index_a if e.get("type") == forward]
            targets = [e for e in index_b if e.get("type") == backward]
            for element_a in sources:
                box_a = _box(element_a.get("geometry", {}))
                if box_a is None:
                    continue
                for element_b in targets:
                    box_b = _box(element_b.get("geometry", {}))
                    if box_b is None:
                        continue
                    distance = geo.clear_gap(box_a, box_b)
                    if distance < rule.min_clearance:
                        found.append(CrossSourceViolation(
                            source_scope=scope_a.adapter_name, source_element=element_a["id"],
                            target_scope=scope_b.adapter_name, target_element=element_b["id"],
                            distance=round(distance, 3), required=rule.min_clearance,
                            description=rule.description))
    return found
