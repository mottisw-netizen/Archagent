"""Site topology / elevation graph / drainage validation (Petah Tikva spec §9-14)."""

from __future__ import annotations

import pytest

from archagent.evidence import Evidence, PermitEvidenceChecker
from archagent.site import (
    DrainageNetwork,
    DrainageNode,
    ElevationGraph,
    ElevationPoint,
    SiteElement,
    SiteTopology,
    chamber_volume,
    validate_capacity_evidence,
    validate_coverage,
    validate_elevation_consistency,
    validate_flow_direction,
    validate_municipal_line_setback,
)


# ----------------------------------------------------------------------
# topology relations (spec §10)
# ----------------------------------------------------------------------
def test_site_relations_match_spec_examples():
    topo = SiteTopology()
    topo.add(SiteElement("SW-1", "sidewalk"))
    topo.add(SiteElement("ROAD-1", "road"))
    topo.add(SiteElement("MD-1", "municipal_drain"))
    topo.add(SiteElement("PLOT-1", "plot_boundary"))
    topo.relate("SW-1", "drains_to", "ROAD-1")
    topo.relate("MD-1", "crosses", "PLOT-1")
    assert topo.related("SW-1", "drains_to")[0].object == "ROAD-1"
    assert topo.of_kind("municipal_drain")[0].element_id == "MD-1"
    with pytest.raises(ValueError):
        topo.relate("SW-1", "not_a_relation", "ROAD-1")


# ----------------------------------------------------------------------
# elevation graph / slope (spec §11)
# ----------------------------------------------------------------------
def test_elevation_chain_slope_matches_road_to_basement_ramp():
    graph = ElevationGraph()
    graph.add(ElevationPoint("road_level", x=0, y=0, z=100.0, source="survey"))
    graph.add(ElevationPoint("curb_level", x=1, y=0, z=99.85, source="survey"))
    graph.add(ElevationPoint("sidewalk_level", x=2.5, y=0, z=99.9, source="survey"))
    graph.add(ElevationPoint("plot_entry_level", x=4, y=0, z=99.7, source="survey"))
    graph.add(ElevationPoint("basement_ramp_top", x=4, y=0, z=99.7, source="drawing"))
    graph.add(ElevationPoint("basement_ramp_bottom", x=14, y=0, z=96.7, source="drawing"))

    slopes = graph.chain_slopes()
    assert len(slopes) == 5
    ramp = graph.slope("basement_ramp_top", "basement_ramp_bottom")
    assert ramp.slope == pytest.approx(-0.3)
    assert "survey" in graph.slope("road_level", "curb_level").basis


# ----------------------------------------------------------------------
# drainage network validation (spec §12)
# ----------------------------------------------------------------------
def _built_network() -> DrainageNetwork:
    network = DrainageNetwork()
    network.add_node(DrainageNode("CB-1", "catch_basin", invert_level=99.0,
                                  drainage_area_ids=["landscape-1"]))
    network.add_node(DrainageNode("CH-1", "detention_chamber", invert_level=98.0))
    network.add_node(DrainageNode("OUT-1", "drainage_outlet", invert_level=97.0))
    network.add_edge("CB-1", "CH-1")
    network.add_edge("CH-1", "OUT-1", kind="overflows_to")
    return network


def test_coverage_flags_an_area_with_no_drainage_solution():
    network = _built_network()
    issues = validate_coverage(network, ["landscape-1", "paved-area-2"])
    assert issues == ["paved-area-2 has no drainage solution"]


def test_flow_direction_requires_a_path_to_an_outlet():
    network = _built_network()
    assert validate_flow_direction(network) == []
    network.add_node(DrainageNode("CB-2", "catch_basin"))  # isolated, no edges
    issues = validate_flow_direction(network)
    assert "CB-2 has no valid downstream path to an outlet" in issues


def test_elevation_consistency_rejects_uphill_flow():
    network = _built_network()
    assert validate_elevation_consistency(network) == []
    network.nodes["CH-1"].invert_level = 99.5  # now higher than CB-1's downstream target
    network.add_edge("CH-1", "CB-1")  # CH-1 (99.5) "flowing" to CB-1 (99.0) is fine (downhill)
    network.nodes["OUT-1"].invert_level = 100.0  # but CH-1 -> OUT-1 is now uphill
    issues = validate_elevation_consistency(network)
    assert any("cannot flow uphill" in issue for issue in issues)


def test_capacity_evidence_never_invented_without_hydrologic_report():
    checker = PermitEvidenceChecker()
    issues = validate_capacity_evidence(checker, ["CH-1"], project_id="P-1")
    assert "CH-1: hydrologic report evidence is missing, not satisfied" in issues

    checker.add(Evidence(type="hydrologic_report", project_id="P-1",
                         covered_elements=["CH-1"], approval_status="approved"))
    issues = validate_capacity_evidence(checker, ["CH-1"], project_id="P-1")
    assert issues == []


def test_chamber_volume_rectangular_and_cylindrical():
    rectangular = DrainageNode("CH-1", "detention_chamber", length=3.0, width=2.0, depth=1.5)
    assert chamber_volume(rectangular) == 9.0

    cylindrical = DrainageNode("CH-2", "settling_chamber", shape="cylindrical",
                               diameter=2.0, depth=2.0)
    import math
    assert chamber_volume(cylindrical) == math.pi * 1.0 * 1.0 * 2.0


def test_chamber_volume_none_when_dimensions_missing():
    node = DrainageNode("CH-3", "detention_chamber", length=3.0)  # no width/depth
    assert chamber_volume(node) is None


def test_municipal_drainage_line_2m_conditional_setback():
    assert validate_municipal_line_setback(1.2) != []
    assert validate_municipal_line_setback(2.5) == []
    # The conditional escape hatch: a diversion solution waives the setback.
    assert validate_municipal_line_setback(1.2, diversion_submitted=True) == []
