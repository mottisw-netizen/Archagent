"""Step 6 - the dependency graph (SKILL.md 6).

Nodes are comments, elements, constraints and changes; edges carry the
relation and the impact order.  The graph decides two things: the order plans
execute in, and which untouched elements still have to be re-validated.
"""

from __future__ import annotations

from collections import deque
from typing import Iterable

from .drawing.api import DrawingAPIError, DrawingDriver
from .models import Constraint, CorrectionPlan, MunicipalComment

RELATIONS = ("requires", "modifies", "constrains", "conflicts_with", "invalidates")
MAX_ORDER = 3
ORDER_NAMES = {1: "direct", 2: "secondary", 3: "tertiary"}

#: roads_drainage/civil findings can force changes in these disciplines
#: (Petah Tikva spec §14) - beyond the generic architecture -> traffic
#: direction the rest of the pipeline already assumes. Keyed by
#: :attr:`MunicipalComment.affected_discipline`.
CROSS_DISCIPLINE_DEPENDENCIES: dict[str, tuple[str, ...]] = {
    "civil": ("architecture", "landscape", "traffic", "structure"),
}


class DependencyGraph:
    def __init__(self) -> None:
        self.nodes: dict[str, dict] = {}
        self.edges: list[dict] = []
        self.truncated = False

    # ------------------------------------------------------------------
    def add_node(self, node_id: str, kind: str, ref: str = "") -> str:
        self.nodes.setdefault(node_id, {"node_id": node_id, "kind": kind, "ref": ref or node_id})
        return node_id

    def add_edge(self, source: str, target: str, relation: str, order: str = "direct",
                 severity: str = "medium") -> None:
        if relation not in RELATIONS:
            raise ValueError(f"unknown relation: {relation!r}")
        edge = {"from": source, "to": target, "relation": relation, "order": order,
                "severity": severity}
        if edge not in self.edges:
            self.edges.append(edge)

    def neighbours(self, node_id: str) -> list[str]:
        return [e["to"] for e in self.edges if e["from"] == node_id]

    def to_dict(self) -> dict:
        return {"nodes": list(self.nodes.values()), "edges": self.edges,
                "truncated": self.truncated}

    # ------------------------------------------------------------------
    def reachable(self, start: str, max_depth: int = MAX_ORDER) -> list[str]:
        seen = {start}
        order: list[str] = []
        queue = deque([(start, 0)])
        while queue:
            node, depth = queue.popleft()
            if depth >= max_depth:
                if self.neighbours(node):
                    self.truncated = True
                continue
            for neighbour in self.neighbours(node):
                if neighbour in seen:
                    continue
                seen.add(neighbour)
                order.append(neighbour)
                queue.append((neighbour, depth + 1))
        return order

    def cycles(self) -> list[list[str]]:
        """Cycles are conflicts, never resolved silently (SKILL.md 6.2)."""
        found: list[list[str]] = []
        colour: dict[str, int] = {}
        stack: list[str] = []

        def visit(node: str) -> None:
            colour[node] = 1
            stack.append(node)
            for neighbour in self.neighbours(node):
                if colour.get(neighbour, 0) == 0:
                    visit(neighbour)
                elif colour.get(neighbour) == 1:
                    cycle = stack[stack.index(neighbour):] + [neighbour]
                    if cycle not in found:
                        found.append(cycle)
            stack.pop()
            colour[node] = 2

        for node in list(self.nodes):
            if colour.get(node, 0) == 0:
                visit(node)
        return found


def build_graph(plans: list[CorrectionPlan], constraints: list[Constraint],
                driver: DrawingDriver,
                comments: Iterable[MunicipalComment] = ()) -> DependencyGraph:
    graph = DependencyGraph()
    add_discipline_dependencies(graph, comments)
    for constraint in constraints:
        graph.add_node(constraint.constraint_id, "constraint", constraint.rule)
    for plan in plans:
        graph.add_node(plan.plan_id, "change", plan.strategy)
        for comment_id in plan.comment_ids:
            graph.add_node(comment_id, "comment", comment_id)
            graph.add_edge(comment_id, plan.plan_id, "requires", "direct", "high")
        for action in plan.plan:
            element_node = graph.add_node(action.element, "element", action.element)
            graph.add_edge(plan.plan_id, element_node, "modifies", "direct", "high")
            for neighbour, relation in _related_elements(driver, action.element):
                graph.add_node(neighbour, "element", neighbour)
                graph.add_edge(element_node, neighbour, relation, "secondary", "medium")
        for effect in plan.expected_effects:
            graph.add_node(effect.element, "element", effect.element)
            graph.add_edge(plan.plan_id, effect.element, "modifies", "secondary",
                           "high" if not effect.still_compliant else "medium")
            if effect.constraint_id:
                graph.add_node(effect.constraint_id, "constraint", effect.constraint_id)
                graph.add_edge(effect.element, effect.constraint_id, "constrains", "secondary",
                               "critical" if not effect.still_compliant else "medium")
    for constraint in constraints:
        for element_id in _constraint_elements(constraint):
            if element_id in graph.nodes:
                graph.add_edge(element_id, constraint.constraint_id, "constrains", "direct", "high")
    return graph


def add_discipline_dependencies(graph: DependencyGraph,
                                comments: Iterable[MunicipalComment]) -> None:
    """Record roads_drainage -> architecture/landscape/parking/structural (spec §14).

    A civil/drainage finding (a municipal drainage line's required setback,
    say) can force an architectural, landscape or structural change even
    though no comment or constraint directly names those elements yet - this
    adds one "discipline" node per discipline actually present among
    ``comments`` and a ``constrains`` edge from an upstream discipline to
    each downstream one it can affect, on top of whatever the rest of
    :func:`build_graph` already built, never in place of it.
    """
    present = {comment.affected_discipline for comment in comments}
    for upstream, downstream_disciplines in CROSS_DISCIPLINE_DEPENDENCIES.items():
        if upstream not in present:
            continue
        upstream_node = graph.add_node(f"discipline:{upstream}", "discipline", upstream)
        for downstream in downstream_disciplines:
            if downstream not in present or downstream == upstream:
                continue
            downstream_node = graph.add_node(f"discipline:{downstream}", "discipline", downstream)
            graph.add_edge(upstream_node, downstream_node, "constrains", "secondary", "high")


def _constraint_elements(constraint: Constraint) -> list[str]:
    elements = list(constraint.affected_elements)
    if constraint.test and constraint.test.subject.get("element_id"):
        elements.append(constraint.test.subject["element_id"])
    return elements


def _related_elements(driver: DrawingDriver, element_id: str) -> list[tuple[str, str]]:
    """Neighbours of an element: declared relations, touching geometry, schedules."""
    related: list[tuple[str, str]] = []
    try:
        element = driver.get_element(element_id)
    except DrawingAPIError:
        return related
    for other in element.get("properties", {}).get("related_elements", []):
        related.append((other, "modifies"))
    elements = getattr(driver, "elements", None)
    if elements is None:
        return related
    for candidate in elements():
        if candidate["id"] == element_id:
            continue
        if candidate.get("type") in ("dimension", "text"):
            continue  # annotation follows its host; it never constrains it
        try:
            distance = driver.calculate_distance(element_id, candidate["id"], "clear")
        except DrawingAPIError:
            continue
        if distance <= 0.5:  # touching or nearly touching
            related.append((candidate["id"], "constrains"))
    schedules = getattr(driver, "schedules", None)
    if schedules is not None:
        for schedule_id, schedule in schedules().items():
            source = schedule.get("source", {})
            if source and element_id in driver.find_element(**source):
                related.append((schedule_id, "invalidates"))
    return related


def merge_graphs(graphs: list[DependencyGraph]) -> DependencyGraph:
    """Combine one graph per source into the single graph a run reports.

    Each source's graph was built against its own driver, so an element node
    from one never collides with another's - ids are the host's own stable
    ids. Merging is just union: nodes by id, edges by value.
    """
    merged = DependencyGraph()
    for graph in graphs:
        for node_id, node in graph.nodes.items():
            merged.nodes.setdefault(node_id, node)
        for edge in graph.edges:
            if edge not in merged.edges:
                merged.edges.append(edge)
        merged.truncated = merged.truncated or graph.truncated
    return merged


def impact_set(graph: DependencyGraph, plans: list[CorrectionPlan]) -> list[str]:
    """Every element reachable from a change; all of it is re-validated."""
    impacted: list[str] = []
    for plan in plans:
        for node in graph.reachable(plan.plan_id):
            if graph.nodes[node]["kind"] == "element" and node not in impacted:
                impacted.append(node)
    return impacted
