"""Architecture semantic model - envelope objects + landscape validators (spec §5)."""

from __future__ import annotations

from archagent.architecture import (
    Balcony,
    Facade,
    FacadePanel,
    Pergola,
    Railing,
    Screen,
    validate_area_ratio,
    validate_distance_to_plot_boundary,
    validate_site_level_difference,
    validate_soil_depth,
)


def test_envelope_objects_carry_material_and_location():
    facade = Facade(facade_id="F-1", orientation="street-facing", elevation_sheet="A-301")
    panel = FacadePanel(panel_id="P-1", facade_id="F-1", material="plaster", color="dark grey")
    balcony = Balcony(balcony_id="B-1", railing_id="R-1")
    railing = Railing(railing_id="R-1", height=1.05, material="steel")
    pergola = Pergola(pergola_id="PG-1", slat_spacing=0.10)
    screen = Screen(screen_id="S-1", slat_spacing=0.05)
    assert panel.facade_id == facade.facade_id
    assert balcony.railing_id == railing.railing_id
    assert pergola.slat_spacing != screen.slat_spacing


# ----------------------------------------------------------------------
# spec §5.3's own worked numbers
# ----------------------------------------------------------------------
def test_common_landscaping_30_percent_of_plot_area():
    plot_area = 1000.0
    built_area = 200.0
    denominator = plot_area - built_area
    assert validate_area_ratio(240.0, denominator, 0.30, "common landscaping") == []
    issues = validate_area_ratio(200.0, denominator, 0.30, "common landscaping")
    assert "25.0%" in issues[0]
    assert "30.0%" in issues[0]


def test_permeable_area_15_percent_of_plot():
    assert validate_area_ratio(150.0, 1000.0, 0.15, "permeable area") == []
    assert validate_area_ratio(100.0, 1000.0, 0.15, "permeable area") != []


def test_zero_denominator_never_divides_by_zero():
    issues = validate_area_ratio(10.0, 0.0, 0.30, "landscaping")
    assert "zero or negative" in issues[0]


def test_planting_soil_depth_1_5m():
    assert validate_soil_depth(1.6, 1.5) == []
    assert validate_soil_depth(1.2, 1.5) != []


def test_distance_to_plot_boundary():
    assert validate_distance_to_plot_boundary(3.0, 2.0) == []
    assert validate_distance_to_plot_boundary(1.0, 2.0) != []


def test_site_level_difference_both_bounds():
    assert validate_site_level_difference(0.5, maximum=1.0, minimum=0.1) == []
    assert validate_site_level_difference(1.5, maximum=1.0) != []
    assert validate_site_level_difference(0.05, minimum=0.1) != []
