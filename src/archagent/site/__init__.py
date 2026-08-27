"""The site topology / drainage semantic model (Petah Tikva spec §9-14).

A discipline-neutral site model (roads, curbs, drainage) plus an elevation
graph and a drainage-network validator - the biggest technical gap the spec
identifies in the generic DWG/Civil 3D path.
"""

from .drainage import (
    DrainageEdge,
    DrainageNetwork,
    DrainageNode,
    validate_capacity_evidence,
    validate_coverage,
    validate_elevation_consistency,
    validate_flow_direction,
    validate_municipal_line_setback,
)
from .elevations import ElevationGraph, ElevationPoint, SlopeResult
from .surfaces import Surface
from .topology import SiteElement, SiteRelation, SiteTopology
from .trees import Tree, validate_preservation_radius

__all__ = [
    "DrainageEdge", "DrainageNetwork", "DrainageNode", "ElevationGraph",
    "ElevationPoint", "SiteElement", "SiteRelation", "SiteTopology", "SlopeResult",
    "Surface", "Tree", "validate_capacity_evidence", "validate_coverage",
    "validate_elevation_consistency", "validate_flow_direction",
    "validate_municipal_line_setback", "validate_preservation_radius",
]
