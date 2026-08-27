"""Typed road/curb/pipe objects (spec §9-10, §13).

`SiteElement(kind="drainage_pipe")` (or `"curb"`, `"road"`, `"sidewalk"`) is
enough to place these in the topology and relate them to other things, but a
pipe's diameter and invert levels, or a curb's height and whether it is
mountable/dropped, are exactly the numbers the record's comments turn on
(`אבן שפה מונמכת`, `אבן עליה רכב`, pipe diameter/`I.L.`/length). These give
those specific comments their own typed fields instead of a properties dict.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..models import Serialisable


@dataclass
class Road(Serialisable):
    road_id: str
    width: float = 0.0
    level: float | None = None


@dataclass
class Sidewalk(Serialisable):
    sidewalk_id: str
    width: float = 0.0
    slope: float | None = None
    level: float | None = None


@dataclass
class Curb(Serialisable):
    """A standard curb, a dropped curb (`אבן שפה מונמכת`), or a mountable
    curb (`אבן עליה רכב`) - distinguished by ``kind``, not three classes."""

    curb_id: str
    kind: str = "standard"  # standard | dropped | mountable
    height: float | None = None


@dataclass
class Pipe(Serialisable):
    """One drainage pipe run between two :class:`~.drainage.DrainageNode`
    ids - an edge with its own attributes, not just a `"flows_to"` relation."""

    pipe_id: str
    from_node: str
    to_node: str
    diameter: float | None = None
    length: float | None = None
    material: str = ""
    upstream_invert_level: float | None = None
    downstream_invert_level: float | None = None


def pipe_slope(pipe: Pipe) -> float | None:
    """Derived from invert levels and length - never fabricated when either
    is missing."""
    if (pipe.upstream_invert_level is not None and pipe.downstream_invert_level is not None
            and pipe.length):
        return (pipe.upstream_invert_level - pipe.downstream_invert_level) / pipe.length
    return None


def validate_curb_height(curb: Curb, minimum: float | None = None,
                         maximum: float | None = None) -> list[str]:
    issues = []
    if curb.height is None:
        return issues
    if minimum is not None and curb.height < minimum:
        issues.append(f"{curb.curb_id}: height {curb.height:.3f} m is below the "
                      f"required {minimum:.3f} m")
    if maximum is not None and curb.height > maximum:
        issues.append(f"{curb.curb_id}: height {curb.height:.3f} m exceeds the "
                      f"maximum {maximum:.3f} m")
    return issues


def validate_sidewalk_slope(sidewalk: Sidewalk, minimum: float | None = None,
                            maximum: float | None = None) -> list[str]:
    """e.g. the record's own "at least 1% paved-area slope" requirement."""
    issues = []
    if sidewalk.slope is None:
        return issues
    if minimum is not None and sidewalk.slope < minimum:
        issues.append(f"{sidewalk.sidewalk_id}: slope {sidewalk.slope:.3f} is below the "
                      f"required minimum {minimum:.3f}")
    if maximum is not None and sidewalk.slope > maximum:
        issues.append(f"{sidewalk.sidewalk_id}: slope {sidewalk.slope:.3f} exceeds the "
                      f"maximum {maximum:.3f}")
    return issues
