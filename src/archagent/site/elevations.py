"""The elevation graph (spec §11).

Site elevations are not isolated text annotations - a road level, a curb
level, a sidewalk level, a plot-entry level and a basement-ramp top/bottom
form a chain, and the slope between consecutive points is what a comment like
"sidewalk slope toward the roadway" or "ramp elevations" is actually asking
about. Every point carries its measured basis (``source``, ``sheet``), so a
reported slope is always traceable back to where its two elevations came from.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from ..models import Serialisable


@dataclass
class ElevationPoint(Serialisable):
    label: str
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    source: str = ""
    sheet: str = ""
    confidence: float = 1.0


@dataclass
class SlopeResult(Serialisable):
    from_point: str
    to_point: str
    slope: float
    delta_z: float
    horizontal_distance: float
    basis: str = ""


class ElevationGraph:
    """A chain of :class:`ElevationPoint`, in downstream order.

    ``road_level -> curb_level -> sidewalk_level -> plot_entry_level ->
    basement_ramp_top -> basement_ramp_bottom`` is the canonical Petah Tikva
    chain (spec §11); this class does not hard-code it, it just orders
    whatever points are added via :meth:`add`.
    """

    def __init__(self) -> None:
        self.points: dict[str, ElevationPoint] = {}
        self.order: list[str] = []

    def add(self, point: ElevationPoint) -> ElevationPoint:
        if point.label not in self.points:
            self.order.append(point.label)
        self.points[point.label] = point
        return point

    def slope(self, from_label: str, to_label: str) -> SlopeResult:
        a, b = self.points[from_label], self.points[to_label]
        horizontal = math.hypot(b.x - a.x, b.y - a.y)
        delta_z = b.z - a.z
        value = delta_z / horizontal if horizontal else float("inf")
        basis = f"{a.label} ({a.source or 'unspecified source'}) -> {b.label} ({b.source or 'unspecified source'})"
        return SlopeResult(from_point=from_label, to_point=to_label, slope=value,
                           delta_z=delta_z, horizontal_distance=horizontal, basis=basis)

    def chain_slopes(self) -> list[SlopeResult]:
        """The slope of every consecutive pair in insertion order."""
        return [self.slope(self.order[i], self.order[i + 1])
                for i in range(len(self.order) - 1)]
