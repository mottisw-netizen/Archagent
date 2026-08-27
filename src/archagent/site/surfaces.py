"""A minimal read-only site surface (spec §10, §33).

A real TIN/``Surface`` object (Civil 3D) is not read here - see SKILL.md's
authority-profile / adapter notes: that is explicit P1 scope requiring a live
Civil 3D host, not something this data model fabricates. What this module
does provide is a simple point-cloud surface: elevation-at-a-point by nearest
known spot elevation, which is enough to answer "what is the ground level
near here" for a set of surveyed points without pretending to be a TIN.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .elevations import ElevationPoint


@dataclass
class Surface:
    """A cloud of surveyed spot elevations - not a triangulated surface."""

    name: str
    points: list[ElevationPoint] = field(default_factory=list)

    def add(self, point: ElevationPoint) -> None:
        self.points.append(point)

    def elevation_near(self, x: float, y: float) -> ElevationPoint | None:
        """The nearest known spot elevation to ``(x, y)``, or ``None`` if empty.

        This is deliberately not interpolation: with only a handful of survey
        points, inventing a triangulated value between them would be exactly
        the kind of measurement the model must never estimate.
        """
        if not self.points:
            return None
        return min(self.points, key=lambda p: math.hypot(p.x - x, p.y - y))
