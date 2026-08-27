"""Cross-discipline dependency graph extension (Petah Tikva spec §14)."""

from __future__ import annotations

from archagent.graph import DependencyGraph, add_discipline_dependencies, build_graph
from archagent.models import MunicipalComment


def _comment(comment_id: str, discipline: str) -> MunicipalComment:
    return MunicipalComment(comment_id=comment_id, department="X", original_text="x",
                            affected_discipline=discipline)


def test_civil_constrains_architecture_landscape_traffic_and_structure():
    graph = DependencyGraph()
    comments = [_comment("C-1", "civil"), _comment("C-2", "architecture"),
               _comment("C-3", "landscape"), _comment("C-4", "traffic"),
               _comment("C-5", "structure")]
    add_discipline_dependencies(graph, comments)
    edges = {(e["from"], e["to"], e["relation"]) for e in graph.edges}
    assert ("discipline:civil", "discipline:architecture", "constrains") in edges
    assert ("discipline:civil", "discipline:landscape", "constrains") in edges
    assert ("discipline:civil", "discipline:traffic", "constrains") in edges
    assert ("discipline:civil", "discipline:structure", "constrains") in edges
    # Still only the classic architecture -> traffic direction elsewhere;
    # nothing here reverses it.
    assert ("discipline:architecture", "discipline:civil", "constrains") not in edges


def test_no_civil_discipline_present_adds_no_discipline_nodes():
    graph = DependencyGraph()
    comments = [_comment("C-1", "architecture"), _comment("C-2", "traffic")]
    add_discipline_dependencies(graph, comments)
    assert not any(node["kind"] == "discipline" for node in graph.nodes.values())


def test_build_graph_still_works_with_no_comments_argument():
    # build_graph's new `comments` parameter is optional and backward compatible.
    graph = build_graph([], [], _StubDriver())
    assert isinstance(graph, DependencyGraph)
    assert not any(node["kind"] == "discipline" for node in graph.nodes.values())


class _StubDriver:
    def elements(self):
        return []
