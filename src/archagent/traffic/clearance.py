"""Column/wall clearance to the drive path edge (spec §7.3).

The record's clearances are concrete and distinct: 0.5 m from the edge of
travel generally, 0.75 m for service-level-2 parking. This module treats a
column or wall as an independent obstruction object and measures its distance
to a drive-path edge as real 2D geometry (point-to-segment distance), not a
text match on a number.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..models import Serialisable

Point = tuple[float, float]


def point_to_segment_distance(point: Point, seg_a: Point, seg_b: Point) -> float:
    px, py = point
    ax, ay = seg_a
    bx, by = seg_b
    dx, dy = bx - ax, by - ay
    length_sq = dx * dx + dy * dy
    if length_sq == 0:
        return math_hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length_sq))
    closest = (ax + t * dx, ay + t * dy)
    return math_hypot(px - closest[0], py - closest[1])


def math_hypot(dx: float, dy: float) -> float:
    return (dx * dx + dy * dy) ** 0.5


@dataclass
class ClearanceViolation(Serialisable):
    element_id: str
    distance: float
    required: float

    def to_dict(self) -> dict:
        return {"element_id": self.element_id, "distance": round(self.distance, 3),
                "required": self.required}


@dataclass
class ClearanceReport(Serialisable):
    edge: tuple[Point, Point]
    required: float
    violations: list[ClearanceViolation] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.violations


def check_clearances(obstructions: dict[str, Point], drive_edge: tuple[Point, Point],
                     required: float) -> ClearanceReport:
    """distance(element, drive_path_edge) for every column/wall obstruction.

    ``obstructions`` maps an element id to its position; each is measured
    independently, matching spec §7.3's rule that columns and walls are their
    own collision/clearance objects, not folded into one generic distance.
    """
    violations = []
    for element_id, point in obstructions.items():
        distance = point_to_segment_distance(point, drive_edge[0], drive_edge[1])
        if distance < required:
            violations.append(ClearanceViolation(element_id, distance, required))
    return ClearanceReport(edge=drive_edge, required=required, violations=violations)
