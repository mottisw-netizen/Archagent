"""Parking validators (spec §7.1, §7.4).

Two distinct checks, kept distinct on purpose:

1. does each *space* meet its own dimension/clearance requirements
   (:func:`validate_space`)?
2. does the *schedule* (the parking-balance table) match what is actually
   drawn (:func:`reconcile_balance`)? The record's own comment - the parking
   balance table "could not be understood" - is exactly the failure mode
   §7.4 warns about: never trust the table alone.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..models import Serialisable
from .model import ParkingBalance, ParkingSpace


@dataclass
class SpaceValidation(Serialisable):
    space_id: str
    issues: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues


def validate_space(space: ParkingSpace, min_width: float, min_length: float,
                   min_clearance_to_column: float = 0.5,
                   min_clearance_to_wall: float = 0.5) -> SpaceValidation:
    """Width, length and clearance are independent checks (spec §7.1) -
    never folded into one generic ``width`` metric."""
    issues = []
    if space.width < min_width:
        issues.append(f"width {space.width:.2f} m is below the required {min_width:.2f} m")
    if space.length < min_length:
        issues.append(f"length {space.length:.2f} m is below the required {min_length:.2f} m")
    if space.clearance_to_column is not None and space.clearance_to_column < min_clearance_to_column:
        issues.append(f"clearance to column {space.clearance_to_column:.2f} m is below "
                      f"the required {min_clearance_to_column:.2f} m")
    if space.clearance_to_wall is not None and space.clearance_to_wall < min_clearance_to_wall:
        issues.append(f"clearance to wall {space.clearance_to_wall:.2f} m is below "
                      f"the required {min_clearance_to_wall:.2f} m")
    return SpaceValidation(space_id=space.space_id, issues=issues)


@dataclass
class BalanceReconciliation(Serialisable):
    """Schedule vs. actual geometry (spec §7.4)."""

    table_total: int = 0
    actual_total: int = 0
    table_accessible: int = 0
    actual_accessible: int = 0
    table_visitor: int = 0
    actual_visitor: int = 0
    discrepancies: list[str] = field(default_factory=list)

    @property
    def matches(self) -> bool:
        return not self.discrepancies


def reconcile_balance(balance: ParkingBalance, actual_spaces: list[ParkingSpace]
                      ) -> BalanceReconciliation:
    """Compare ``parking_schedule`` against ``actual_parking_elements``.

    The table is never authoritative by itself - this always measures the
    actually-drawn spaces and reports every place the two disagree, rather
    than reporting only whether the total matches.
    """
    actual_total = len(actual_spaces)
    actual_accessible = sum(1 for space in actual_spaces if space.accessible)
    actual_visitor = sum(1 for space in actual_spaces if space.visitor)

    discrepancies = []
    if balance.provided_spaces != actual_total:
        discrepancies.append(
            f"schedule claims {balance.provided_spaces} provided spaces; "
            f"{actual_total} are actually drawn")
    if balance.accessible_spaces != actual_accessible:
        discrepancies.append(
            f"schedule claims {balance.accessible_spaces} accessible spaces; "
            f"{actual_accessible} are actually drawn")
    if balance.visitor_spaces != actual_visitor:
        discrepancies.append(
            f"schedule claims {balance.visitor_spaces} visitor spaces; "
            f"{actual_visitor} are actually drawn")
    if actual_total < balance.required_spaces:
        discrepancies.append(
            f"only {actual_total} spaces are drawn against a requirement of "
            f"{balance.required_spaces}")

    return BalanceReconciliation(
        table_total=balance.provided_spaces, actual_total=actual_total,
        table_accessible=balance.accessible_spaces, actual_accessible=actual_accessible,
        table_visitor=balance.visitor_spaces, actual_visitor=actual_visitor,
        discrepancies=discrepancies)
