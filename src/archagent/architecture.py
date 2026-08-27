"""Architecture semantic objects beyond walls and dimensions (spec §5, §10).

The Petah Tikva record's architecture comments are not limited to ordinary
room/wall dimensions: facade cladding colour, pergola slat spacing, balcony
railings, laundry screens, and a set of landscape/development ratios
(landscaping share, permeable area, soil depth, distance to the plot
boundary, site level difference) all need their own semantic objects rather
than being folded into the generic element model. This module is deliberately
data plus small pure-function validators - the same pattern as
:mod:`archagent.traffic.parking` and :mod:`archagent.site.drainage` - not a
second measurement engine: a real drawing measurement still comes from a
:class:`~archagent.drawing.api.DrawingDriver` through the existing constraint
engine (§8) wherever a driver can produce one.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import Serialisable


# ----------------------------------------------------------------------
# building envelope / facade (spec §5.1)
# ----------------------------------------------------------------------
@dataclass
class Facade(Serialisable):
    facade_id: str
    orientation: str = ""  # e.g. "north", "street-facing"
    elevation_sheet: str = ""


@dataclass
class FacadePanel(Serialisable):
    panel_id: str
    facade_id: str = ""
    material: str = ""
    color: str = ""
    finish: str = ""


@dataclass
class Balcony(Serialisable):
    balcony_id: str
    railing_id: str = ""
    detail_sheet: str = ""


@dataclass
class Railing(Serialisable):
    railing_id: str
    height: float | None = None
    material: str = ""


@dataclass
class Louver(Serialisable):
    louver_id: str
    facade_id: str = ""
    slat_spacing: float | None = None


@dataclass
class Pergola(Serialisable):
    pergola_id: str
    slat_spacing: float | None = None


@dataclass
class Screen(Serialisable):
    """A laundry/utility screen - its own object per spec §5.1, distinct
    from a louver or a pergola even though all three are slatted elements."""

    screen_id: str
    slat_spacing: float | None = None


@dataclass
class ElevationDetail(Serialisable):
    detail_id: str
    sheet: str = ""
    scale: str = ""


# ----------------------------------------------------------------------
# landscape / development validators (spec §5.2)
# ----------------------------------------------------------------------
def validate_area_ratio(numerator: float, denominator: float, minimum_ratio: float,
                        label: str = "area ratio") -> list[str]:
    """landscape_area/plot_area, permeable_area/plot_area, etc.

    A ratio of two measured areas is not something the generic single-metric
    ``Requirement``/``ConstraintLedger`` comparison computes on its own (it
    compares one measured value against a threshold); this is the composite
    check spec §5.2 asks for, given both areas already measured.
    """
    if denominator <= 0:
        return [f"cannot compute {label}: the denominator ({denominator}) is zero or negative"]
    ratio = numerator / denominator
    if ratio < minimum_ratio:
        return [f"{label} is {ratio:.1%}, below the required {minimum_ratio:.1%}"]
    return []


def validate_soil_depth(actual: float, minimum: float) -> list[str]:
    if actual < minimum:
        return [f"planting soil depth {actual:.2f} m is below the required {minimum:.2f} m"]
    return []


def validate_distance_to_plot_boundary(distance: float, minimum: float) -> list[str]:
    if distance < minimum:
        return [f"distance to plot boundary {distance:.2f} m is below the "
               f"required {minimum:.2f} m"]
    return []


def validate_site_level_difference(actual_difference: float, maximum: float | None = None,
                                   minimum: float | None = None) -> list[str]:
    issues = []
    if maximum is not None and actual_difference > maximum:
        issues.append(f"site level difference {actual_difference:.2f} m exceeds the "
                      f"maximum {maximum:.2f} m")
    if minimum is not None and actual_difference < minimum:
        issues.append(f"site level difference {actual_difference:.2f} m is below the "
                      f"minimum {minimum:.2f} m")
    return issues
