"""Axis-aligned geometry used by the reference drawing driver.

The reference model represents elements as rectangles or polygons in a plan
coordinate system where +x is east and +y is north (SKILL.md 22,
"Orientation").  Real CAD/BIM drivers replace this module with the host
application's own geometry engine; everything above the driver layer only
consumes :class:`Box`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

DIRECTIONS = {
    "north": (0.0, 1.0),
    "south": (0.0, -1.0),
    "east": (1.0, 0.0),
    "west": (-1.0, 0.0),
}

AXIS_OF = {"north": "y", "south": "y", "east": "x", "west": "x"}


@dataclass(frozen=True)
class Box:
    """Axis-aligned bounding box."""

    x: float
    y: float
    w: float
    h: float

    @property
    def x_max(self) -> float:
        return self.x + self.w

    @property
    def y_max(self) -> float:
        return self.y + self.h

    @property
    def area(self) -> float:
        return self.w * self.h

    @property
    def centre(self) -> tuple[float, float]:
        return (self.x + self.w / 2, self.y + self.h / 2)

    def edge(self, direction: str) -> float:
        """Coordinate of the named edge."""
        if direction == "north":
            return self.y_max
        if direction == "south":
            return self.y
        if direction == "east":
            return self.x_max
        if direction == "west":
            return self.x
        raise ValueError(f"unknown direction: {direction!r}")

    def moved(self, dx: float, dy: float) -> "Box":
        return Box(self.x + dx, self.y + dy, self.w, self.h)

    def resized(self, w: float | None = None, h: float | None = None, anchor: str = "south_west") -> "Box":
        new_w = self.w if w is None else w
        new_h = self.h if h is None else h
        x, y = self.x, self.y
        if "east" in anchor:  # east edge held fixed, grow westwards
            x = self.x_max - new_w
        elif "centre" in anchor or "center" in anchor:
            x = self.centre[0] - new_w / 2
        if "north" in anchor:
            y = self.y_max - new_h
        elif "centre" in anchor or "center" in anchor:
            y = self.centre[1] - new_h / 2
        return Box(x, y, new_w, new_h)

    def to_dict(self) -> dict:
        return {"kind": "rect", "x": self.x, "y": self.y, "w": self.w, "h": self.h}


def box_from_dict(data: dict) -> Box:
    kind = data.get("kind", "rect")
    if kind == "rect":
        return Box(float(data["x"]), float(data["y"]), float(data["w"]), float(data["h"]))
    if kind in ("polygon", "polyline"):
        pts = [(float(p[0]), float(p[1])) for p in data["points"]]
        if not pts:
            raise ValueError("polygon with no points")
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        return Box(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))
    raise ValueError(f"unsupported geometry kind: {kind!r}")


def polygon_area(points: list[tuple[float, float]]) -> float:
    """Shoelace area of a closed polygon."""
    total = 0.0
    n = len(points)
    for i in range(n):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % n]
        total += x1 * y2 - x2 * y1
    return abs(total) / 2.0


def overlap(a: Box, b: Box) -> float:
    """Overlapping area of two boxes (0.0 when they do not overlap)."""
    dx = min(a.x_max, b.x_max) - max(a.x, b.x)
    dy = min(a.y_max, b.y_max) - max(a.y, b.y)
    if dx <= 0 or dy <= 0:
        return 0.0
    return dx * dy


def clear_gap(a: Box, b: Box) -> float:
    """Shortest clear distance between two boxes; 0.0 if they touch or overlap."""
    dx = max(a.x - b.x_max, b.x - a.x_max, 0.0)
    dy = max(a.y - b.y_max, b.y - a.y_max, 0.0)
    return math.hypot(dx, dy)


def centre_distance(a: Box, b: Box) -> float:
    ax, ay = a.centre
    bx, by = b.centre
    return math.hypot(ax - bx, ay - by)


def setback(element: Box, plot: Box, direction: str) -> float:
    """Clear distance from an element edge to the plot line on that side."""
    if direction in ("north", "east"):
        return plot.edge(direction) - element.edge(direction)
    return element.edge(direction) - plot.edge(direction)


def union(boxes: list[Box]) -> Box | None:
    if not boxes:
        return None
    x = min(b.x for b in boxes)
    y = min(b.y for b in boxes)
    x_max = max(b.x_max for b in boxes)
    y_max = max(b.y_max for b in boxes)
    return Box(x, y, x_max - x, y_max - y)
