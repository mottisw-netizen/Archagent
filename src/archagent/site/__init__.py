"""The site topology / drainage semantic model (Petah Tikva spec §9-14).

A discipline-neutral site model (roads, curbs, drainage) plus an elevation
graph and a drainage-network validator - the biggest technical gap the spec
identifies in the generic DWG/Civil 3D path.
"""

from .drainage import (
    DrainageEdge,
    DrainageNetwork,
    DrainageNode,
    chamber_volume,
    validate_capacity_evidence,
    validate_coverage,
    validate_elevation_consistency,
    validate_flow_direction,
    validate_municipal_line_setback,
)
from .elevations import CrossSectionPoint, ElevationGraph, ElevationPoint, SlopeResult
from .roads import (
    Curb,
    Pipe,
    Road,
    Sidewalk,
    pipe_slope,
    validate_curb_height,
    validate_sidewalk_slope,
)
from .surfaces import Surface
from .topology import SiteElement, SiteRelation, SiteTopology
from .trees import (
    MATURE_TREE_MIN_DIAMETER,
    MATURE_TREE_MIN_DIAMETER_RESIDENTIAL,
    Tree,
    requires_felling_license,
    validate_preservation_radius,
)

__all__ = [
    "Curb", "CrossSectionPoint", "DrainageEdge", "DrainageNetwork", "DrainageNode",
    "ElevationGraph", "chamber_volume",
    "ElevationPoint", "MATURE_TREE_MIN_DIAMETER", "MATURE_TREE_MIN_DIAMETER_RESIDENTIAL",
    "Pipe", "Road", "Sidewalk", "SiteElement", "SiteRelation",
    "SiteTopology", "SlopeResult", "Surface", "Tree", "pipe_slope",
    "requires_felling_license",
    "validate_capacity_evidence", "validate_coverage", "validate_curb_height",
    "validate_elevation_consistency", "validate_flow_direction",
    "validate_municipal_line_setback", "validate_preservation_radius",
    "validate_sidewalk_slope",
]
