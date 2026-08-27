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
