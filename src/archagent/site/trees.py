"""Trees / forestry (spec §11, §30).

The record asks for tree surveys, cutting licenses, replacement planting and
preservation declarations with an explicit preservation radius - a tree is a
site object with its own state, not an annotation on the landscape zone it
sits in. It participates in the same :class:`~.topology.SiteTopology` as
everything else in this package (``kind="tree"``); this module adds the
tree-specific fields and the one check the record cares about: nothing
proposed may land inside a preserved tree's radius.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from ..models import Serialisable

#: preservation_status values - never fabricate "preserve" or "removal_approved"
#: without a source (a survey, an authority license).
PRESERVATION_STATUSES = ("unassessed", "preserve", "removal_approved")
REMOVAL_STATUSES = ("not_removed", "pending", "removed")

#: Forest Ordinance (פקודת היערות) definition of a "mature tree" (עץ בוגר):
#: trunk diameter, measured 130 cm above ground, of at least 10 cm - or at
#: least 20 cm on a plot zoned for residential use. Felling, severe pruning,
#: root-cutting or building within the canopy radius of a mature (or
#: otherwise protected) tree needs a forestry-officer license.
#:
#: Provenance note, in the same spirit as `archagent.national_standards`'s
#: `basis` field (this module predates that mechanism, so it is only a
#: docstring note here, not a structural one): these two figures came from a
#: search-result summary quoting the Ordinance's definition, not from this
#: session directly opening and reading nevo.co.il's text of פקודת היערות
#: itself. A parking-regulation citation that looked equally solid from a
#: summary turned out to be wrong once actually fetched (see
#: docs/NATIONAL_VS_LOCAL_STANDARDS.md) - treat these two numbers with the
#: same "real but not yet verified against primary text" caution until
#: someone actually reads the Ordinance directly.
MATURE_TREE_MIN_DIAMETER = 0.10
MATURE_TREE_MIN_DIAMETER_RESIDENTIAL = 0.20


@dataclass
class Tree(Serialisable):
    tree_id: str
    species: str = ""
    trunk_diameter: float | None = None
    canopy: float | None = None
    preservation_status: str = "unassessed"
    preservation_radius: float | None = None
    removal_status: str = "not_removed"
    replacement_requirement: int | None = None
    authority_license: str = ""
    x: float = 0.0
    y: float = 0.0


def requires_felling_license(tree: Tree, plot_use: str = "other") -> bool | None:
    """Does this tree meet the Forest Ordinance's *diameter* criterion for a
    "mature tree" (עץ בוגר), for which felling/severe pruning/root-cutting/
    building within the canopy needs a forestry-officer license?

    This checks trunk diameter only - the Ordinance's full definition is
    height >= 2 m *and* trunk diameter over the threshold, and ``Tree`` has
    no height field, so this can only confirm the diameter half of the test.
    Returns ``None`` (not measured, never a guessed False) when
    ``trunk_diameter`` is unknown - the same "never fabricate" rule as
    ``preservation_status`` above, and distinct from it: this is a factual
    classification against the law, not the authority's own preserve/approve
    decision, and never overrides ``preservation_status``.
    """
    if tree.trunk_diameter is None:
        return None
    threshold = (MATURE_TREE_MIN_DIAMETER_RESIDENTIAL if plot_use == "residential"
                else MATURE_TREE_MIN_DIAMETER)
    return tree.trunk_diameter >= threshold


def validate_preservation_radius(tree: Tree, works: dict[str, tuple[float, float]]
                                 ) -> list[str]:
    """Every planned work point inside a preserved tree's radius is a violation.

    Only checked when ``preservation_status == "preserve"`` - an unassessed or
    removal-approved tree is not this check's concern; that decision belongs
    to the forestry officer's own record, never inferred here.
    """
    if tree.preservation_status != "preserve" or tree.preservation_radius is None:
        return []
    issues = []
    for work_id, (x, y) in works.items():
        distance = math.hypot(x - tree.x, y - tree.y)
        if distance < tree.preservation_radius:
            issues.append(
                f"{work_id} is {distance:.2f} m from tree {tree.tree_id}, inside its "
                f"{tree.preservation_radius:.2f} m preservation radius")
    return issues
