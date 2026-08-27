"""Ramp validation (spec §6-7: "ramp cross-section" among the traffic tests).

A `Ramp` carries a `slope` directly when it was measured, or enough to derive
one (`top_elevation`, `bottom_elevation`, `length`) when it was not - either
way this never invents a slope the object doesn't actually have.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..models import Serialisable
from .model import Ramp


def effective_slope(ramp: Ramp) -> float | None:
    """``ramp.slope`` if set; otherwise derived from elevations and length."""
    if ramp.slope is not None:
        return ramp.slope
    if (ramp.top_elevation is not None and ramp.bottom_elevation is not None
            and ramp.length):
        return (ramp.top_elevation - ramp.bottom_elevation) / ramp.length
    return None


@dataclass
class RampValidation(Serialisable):
    ramp_id: str
    issues: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues


def validate_ramp_slope(ramp: Ramp, max_slope: float, min_width: float | None = None
                        ) -> RampValidation:
    """``max_slope`` is a ratio (e.g. ``0.125`` for a 1:8 grade), not a percent.

    A ramp with no slope derivable at all (no `slope`, and no elevations/
    length to compute one from) is reported as such rather than silently
    passed - the same "no testable requirement, no fabricated pass" rule as
    the rest of the constraint engine.
    """
    issues = []
    slope = effective_slope(ramp)
    if slope is None:
        issues.append(f"{ramp.ramp_id}: no slope could be measured or derived")
    elif abs(slope) > max_slope:
        issues.append(f"{ramp.ramp_id}: slope {slope:.3f} exceeds the maximum {max_slope:.3f}")
    if min_width is not None and ramp.width < min_width:
        issues.append(f"{ramp.ramp_id}: width {ramp.width:.2f} m is below the "
                      f"required {min_width:.2f} m")
    return RampValidation(ramp_id=ramp.ramp_id, issues=issues)
