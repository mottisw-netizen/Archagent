"""The traffic semantic model (Petah Tikva spec §6-8).

Traffic review is a specialised engineering domain, not a set of ordinary
architectural dimensions: a parking space has a width *and* a length *and* a
clearance to the nearest column, each a different metric, and a parking
schedule is a claim to be checked against geometry, never trusted on its own
(§7.4). These dataclasses give that domain real objects instead of folding
everything into one generic ``width`` measurement.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..models import Serialisable


@dataclass
class ParkingSpace(Serialisable):
    space_id: str
    width: float = 0.0
    length: float = 0.0
    type: str = "standard"
    accessible: bool = False
    visitor: bool = False
    service_level: int | None = None
    adjacent_obstructions: list[str] = field(default_factory=list)
    clearance_to_column: float | None = None
    clearance_to_wall: float | None = None
    sheet: str = ""


@dataclass
class DriveAisle(Serialisable):
    aisle_id: str
    width: float = 0.0
    sheet: str = ""


@dataclass
class Ramp(Serialisable):
    ramp_id: str
    width: float = 0.0
    slope: float | None = None
    top_elevation: float | None = None
    bottom_elevation: float | None = None
    sheet: str = ""


@dataclass
class TurningPath(Serialisable):
    path_id: str
    inner_radius: float = 0.0
    outer_radius: float = 0.0
    vehicle_template: str = ""
    sheet: str = ""


@dataclass
class ParkingBalance(Serialisable):
    """The schedule/table side of §7.4 - never trusted alone."""

    required_spaces: int = 0
    provided_spaces: int = 0
    accessible_spaces: int = 0
    visitor_spaces: int = 0
    spaces_by_unit_type: dict[str, int] = field(default_factory=dict)
    spaces_by_use: dict[str, int] = field(default_factory=dict)
    source: str = ""

    @property
    def deficit(self) -> int:
        return max(0, self.required_spaces - self.provided_spaces)

    @property
    def surplus(self) -> int:
        return max(0, self.provided_spaces - self.required_spaces)
