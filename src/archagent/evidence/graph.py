"""The project-wide evidence graph (spec §21-22).

Drawing-to-document traceability: a requirement should be explainable as a
path through the things that actually satisfy it - an element, a sheet, a
report, an approval - not just a status string. This is a small, separate
graph from :class:`archagent.graph.DependencyGraph`: that one orders *changes*
(what must execute before what); this one records *evidence* (what backs a
requirement up), and the two vocabularies of node/edge kinds are deliberately
different so they are never confused for each other.
"""

from __future__ import annotations

from dataclasses import dataclass, field

NODE_KINDS = (
    "comment", "requirement", "drawing_element", "sheet", "document",
    "calculation", "approval", "professional", "version", "measurement",
    "photo", "external_reference",
)
EDGE_KINDS = (
    "supports", "contradicts", "satisfies", "supersedes", "depends_on",
    "prepared_by", "approved_by", "measured_from", "shown_on", "derived_from",
)


@dataclass
class EvidenceGraph:
    nodes: dict[str, dict] = field(default_factory=dict)
    edges: list[dict] = field(default_factory=list)

    def add_node(self, node_id: str, kind: str, label: str = "") -> str:
        if kind not in NODE_KINDS:
            raise ValueError(f"unknown evidence node kind: {kind!r}")
        self.nodes.setdefault(node_id, {"node_id": node_id, "kind": kind,
                                        "label": label or node_id})
        return node_id

    def add_edge(self, source: str, target: str, relation: str) -> None:
        if relation not in EDGE_KINDS:
            raise ValueError(f"unknown evidence relation: {relation!r}")
        edge = {"from": source, "to": target, "relation": relation}
        if edge not in self.edges:
            self.edges.append(edge)

    def to_dict(self) -> dict:
        return {"nodes": list(self.nodes.values()), "edges": self.edges}

    # ------------------------------------------------------------------
    def trace(self, requirement_id: str) -> list[dict]:
        """Every node reachable downstream from one requirement, in edge order.

        This is what backs SKILL.md-style traceability lines such as
        ``Requirement R-123 -> ParkingSpace P-17 -> Traffic plan A-TR-02 ->
        Parking balance table -> Traffic engineer approval`` (spec §22): the
        path is read directly off recorded edges, never inferred.
        """
        if requirement_id not in self.nodes:
            return []
        visited = {requirement_id}
        order: list[dict] = [self.nodes[requirement_id]]
        frontier = [requirement_id]
        while frontier:
            current = frontier.pop(0)
            for edge in self.edges:
                if edge["from"] != current or edge["to"] in visited:
                    continue
                visited.add(edge["to"])
                order.append(self.nodes[edge["to"]])
                frontier.append(edge["to"])
        return order
