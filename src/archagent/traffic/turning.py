"""Turning-radius validation (spec §7.2).

The record asks to "note the turning radii" (``יש לציין רדיוסים בסיבוב``); the
spec is explicit that a number in text is not enough - the system must be
able to show the turning path graphically. :func:`turning_path_points`
produces the actual inner/outer arc geometry so a caller (a preview renderer,
a report figure) has real points to draw, not a claim that a radius was
mentioned.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from ..models import Serialisable
from .model import TurningPath


def turning_path_points(center: tuple[float, float], inner_radius: float,
                        outer_radius: float, start_angle: float = 0.0,
                        end_angle: float = 90.0, steps: int = 16
                        ) -> dict[str, list[tuple[float, float]]]:
    """Points along the inner and outer edges of a turning path, in degrees.

    ``start_angle``/``end_angle`` are measured counter-clockwise from the
    positive x-axis, matching how the rest of the drawing model places points.
    """
    if inner_radius < 0 or outer_radius < 0:
        raise ValueError("radii must not be negative")
    if outer_radius < inner_radius:
        raise ValueError("outer_radius must be >= inner_radius")
    cx, cy = center
    span = end_angle - start_angle
    points = {"inner": [], "outer": []}
    for step in range(steps + 1):
        angle = math.radians(start_angle + span * step / steps)
        points["inner"].append((cx + inner_radius * math.cos(angle),
                                cy + inner_radius * math.sin(angle)))
        points["outer"].append((cx + outer_radius * math.cos(angle),
                                cy + outer_radius * math.sin(angle)))
    return points


@dataclass
class TurningValidation(Serialisable):
    path_id: str
    issues: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues


def validate_turning_path(path: TurningPath, required_inner_radius: float,
                          required_outer_radius: float) -> TurningValidation:
    """Do not merely verify that a radius number appears as text (spec §7.2) -
    this compares the modelled radii against the requirement directly."""
    issues = []
    if path.inner_radius < required_inner_radius:
        issues.append(f"inner radius {path.inner_radius:.2f} m is below the "
                      f"required {required_inner_radius:.2f} m")
    if path.outer_radius < required_outer_radius:
        issues.append(f"outer radius {path.outer_radius:.2f} m is below the "
                      f"required {required_outer_radius:.2f} m")
    return TurningValidation(path_id=path.path_id, issues=issues)
