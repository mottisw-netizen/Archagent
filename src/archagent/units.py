"""Units, tolerance and conservative rounding.

Implements SKILL.md section 22. Every measurement that leaves the system
passes through here, so that no value is ever rounded in the direction that
makes a constraint look satisfied when it is not.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

DEFAULT_UNIT = "m"
DEFAULT_TOLERANCE = 0.005  # 5 mm, SKILL.md 22
REPORT_DECIMALS = 2
EPS = 1e-9

_TO_METRES = {
    "m": 1.0,
    "cm": 0.01,
    "mm": 0.001,
    "m2": 1.0,
    "sqm": 1.0,
    "unit": 1.0,
    "count": 1.0,
}

OPS = {
    ">=": lambda a, b: a >= b - EPS,
    ">": lambda a, b: a > b + EPS,
    "<=": lambda a, b: a <= b + EPS,
    "<": lambda a, b: a < b - EPS,
    "==": lambda a, b: abs(a - b) <= EPS,
    "!=": lambda a, b: abs(a - b) > EPS,
}


class UnitError(ValueError):
    """Raised when two values cannot be compared in a common unit."""


def to_metres(value: float, unit: str) -> float:
    """Convert *value* to metres (or leave counts/areas untouched)."""
    key = (unit or DEFAULT_UNIT).lower()
    if key not in _TO_METRES:
        raise UnitError(f"unsupported unit: {unit!r}")
    return value * _TO_METRES[key]


def convert(value: float, from_unit: str, to_unit: str) -> float:
    from_key = (from_unit or DEFAULT_UNIT).lower()
    to_key = (to_unit or DEFAULT_UNIT).lower()
    if from_key == to_key:
        return value
    if from_key not in _TO_METRES or to_key not in _TO_METRES:
        raise UnitError(f"cannot convert {from_unit!r} -> {to_unit!r}")
    if (from_key in {"m2", "sqm"}) != (to_key in {"m2", "sqm"}):
        raise UnitError(f"cannot convert {from_unit!r} -> {to_unit!r}: incompatible dimensions")
    return to_metres(value, from_key) / _TO_METRES[to_key]


def round_conservative(value: float, op: str, decimals: int = REPORT_DECIMALS) -> float:
    """Round *value* away from compliance.

    For a ``>=`` requirement the reported value is rounded down; for ``<=`` it
    is rounded up.  A borderline value therefore never reads as compliant
    because of presentation.
    """
    factor = 10 ** decimals
    # Snap binary-float noise (5.999999999999999 is 6.0) before rounding away
    # from compliance, so the direction of the rounding stays meaningful.
    scaled = round(value * factor, 6)
    if op in (">=", ">"):
        return math.floor(scaled) / factor
    if op in ("<=", "<"):
        return math.ceil(scaled) / factor
    return round(scaled) / factor


@dataclass(frozen=True)
class Comparison:
    """Outcome of testing a measured value against a required value."""

    measured: float
    required: float
    op: str
    unit: str
    passes: bool
    at_limit: bool
    margin: float

    def describe(self) -> str:
        verdict = "pass" if self.passes else "fail"
        if self.at_limit:
            verdict += " (at the limit)"
        return (
            f"{format_value(self.measured, self.unit, self.op)} {self.op} "
            f"{format_value(self.required, self.unit)} -> {verdict}"
        )

    def to_dict(self) -> dict:
        return {
            "measured": round_conservative(self.measured, self.op),
            "required": self.required,
            "op": self.op,
            "unit": self.unit,
            "passes": self.passes,
            "at_limit": self.at_limit,
            "margin": round(self.margin, 4),
        }


def compare(
    measured: float,
    op: str,
    required: float,
    unit: str = DEFAULT_UNIT,
    measured_unit: str | None = None,
    tolerance: float = DEFAULT_TOLERANCE,
) -> Comparison:
    """Compare a measurement with a requirement.

    The comparison itself is strict: tolerance only decides whether the value
    is *reported* as sitting on the limit, it never turns a fail into a pass.
    """
    if op not in OPS:
        raise ValueError(f"unsupported operator: {op!r}")
    value = convert(measured, measured_unit or unit, unit)
    passes = OPS[op](value, required)
    at_limit = abs(value - required) <= tolerance
    return Comparison(
        measured=value,
        required=required,
        op=op,
        unit=unit,
        passes=passes,
        at_limit=at_limit,
        margin=value - required,
    )


def format_value(value: float, unit: str = DEFAULT_UNIT, op: str | None = None) -> str:
    if unit in ("count", "unit"):
        return f"{int(round(value))}"
    shown = round_conservative(value, op) if op else round(value, REPORT_DECIMALS)
    suffix = "m²" if unit in ("m2", "sqm") else unit
    return f"{shown:.{REPORT_DECIMALS}f}{suffix}"
