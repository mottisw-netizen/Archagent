"""Drainage network validation (spec §12).

Four checks the spec asks for by name - coverage, flow direction, elevation
consistency, capacity evidence - plus the municipal-line conditional rule
(§12's own "represent this as a conditional rule, not as an unconditional
geometry rule"). The graph here is deliberately small and explicit: nodes are
catch basins, chambers and outlets; edges are "flows to" or "overflows to";
nothing is inferred that was not added.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from ..evidence.checker import PermitEvidenceChecker
from ..evidence.model import EvidenceStatus
from ..models import Serialisable

OUTLET_KINDS = ("drainage_outlet", "overflow")


@dataclass
class DrainageNode(Serialisable):
    node_id: str
    kind: str
    invert_level: float | None = None
    #: drainage areas this node directly serves (spec §12 "coverage")
    drainage_area_ids: list[str] = field(default_factory=list)
    #: chamber dimensions, for chamber_volume() below - a detention/settling
    #: chamber's own geometry, never a hydraulic capacity claim.
    shape: str = "rectangular"  # rectangular | cylindrical
    length: float | None = None
    width: float | None = None
    diameter: float | None = None
    depth: float | None = None


def chamber_volume(node: DrainageNode) -> float | None:
    """Geometric volume from the chamber's own given dimensions.

    This is never a hydraulic-capacity claim (spec §12: "never invent
    capacity") - whether this volume is *sufficient* for the design flow is a
    hydrologic-engineering question, answered only by the required
    `hydrologic_report` evidence (see `validate_capacity_evidence` below),
    never by this geometric calculation.
    """
    if node.shape == "cylindrical":
        if node.diameter is None or node.depth is None:
            return None
        radius = node.diameter / 2.0
        return math.pi * radius * radius * node.depth
    if node.length is None or node.width is None or node.depth is None:
        return None
    return node.length * node.width * node.depth


@dataclass
class DrainageEdge(Serialisable):
    from_node: str
    to_node: str
    kind: str = "flows_to"  # flows_to | overflows_to


class DrainageNetwork:
    def __init__(self) -> None:
        self.nodes: dict[str, DrainageNode] = {}
        self.edges: list[DrainageEdge] = []

    def add_node(self, node: DrainageNode) -> DrainageNode:
        self.nodes[node.node_id] = node
        return node

    def add_edge(self, from_node: str, to_node: str, kind: str = "flows_to") -> DrainageEdge:
        edge = DrainageEdge(from_node=from_node, to_node=to_node, kind=kind)
        self.edges.append(edge)
        return edge

    def outgoing(self, node_id: str) -> list[DrainageEdge]:
        return [edge for edge in self.edges if edge.from_node == node_id]

    def reaches(self, node_id: str, targets: set[str]) -> bool:
        seen = {node_id}
        frontier = [node_id]
        while frontier:
            current = frontier.pop()
            for edge in self.outgoing(current):
                if edge.to_node in targets:
                    return True
                if edge.to_node in seen:
                    continue
                seen.add(edge.to_node)
                frontier.append(edge.to_node)
        return False


# ----------------------------------------------------------------------
def validate_coverage(network: DrainageNetwork, drainage_areas: list[str]) -> list[str]:
    """Every relevant drainage area must have a drainage solution."""
    served = {area for node in network.nodes.values() for area in node.drainage_area_ids}
    return [f"{area} has no drainage solution" for area in drainage_areas if area not in served]


def validate_flow_direction(network: DrainageNetwork) -> list[str]:
    """Water must have a valid downstream path to an outlet or overflow."""
    outlets = {node_id for node_id, node in network.nodes.items() if node.kind in OUTLET_KINDS}
    issues = []
    for node_id, node in network.nodes.items():
        if node.kind in OUTLET_KINDS:
            continue
        if not network.reaches(node_id, outlets):
            issues.append(f"{node_id} has no valid downstream path to an outlet")
    return issues


def validate_elevation_consistency(network: DrainageNetwork) -> list[str]:
    """Pipe/chamber invert levels must form a physically plausible path."""
    issues = []
    for edge in network.edges:
        upstream = network.nodes.get(edge.from_node)
        downstream = network.nodes.get(edge.to_node)
        if upstream is None or downstream is None:
            continue
        if upstream.invert_level is None or downstream.invert_level is None:
            continue
        if downstream.invert_level > upstream.invert_level:
            issues.append(
                f"{edge.from_node} (I.L. {upstream.invert_level:.2f}) flows to "
                f"{edge.to_node} (I.L. {downstream.invert_level:.2f}), which is higher - "
                "water cannot flow uphill")
    return issues


def validate_capacity_evidence(checker: PermitEvidenceChecker, chamber_ids: list[str],
                               project_id: str = "") -> list[str]:
    """Where a hydraulic report is required, never invent capacity."""
    issues = []
    for chamber_id in chamber_ids:
        result = checker.check("hydrologic_report", project_id=project_id,
                               affected_element=chamber_id)
        if result.status != EvidenceStatus.SATISFIED:
            issues.append(f"{chamber_id}: hydrologic report evidence is "
                          f"{result.status.value}, not satisfied")
    return issues


def validate_municipal_line_setback(distance_to_line: float, required: float = 2.0,
                                    diversion_submitted: bool = False) -> list[str]:
    """2 m separation from an existing municipal drainage line, unless a
    diversion solution is submitted (spec §12) - conditional, not absolute."""
    if diversion_submitted:
        return []
    if distance_to_line < required:
        return [f"{distance_to_line:.2f} m from the municipal drainage line is below "
                f"the required {required:.2f} m separation, and no diversion solution "
                "was submitted"]
    return []
