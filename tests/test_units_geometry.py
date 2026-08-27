import pytest

from archagent import units
from archagent.drawing import geometry as geo


def test_rounding_never_flatters_a_requirement():
    assert units.round_conservative(2.4996, ">=") == 2.49
    assert units.round_conservative(1850.001, "<=") == 1850.01


def test_float_noise_does_not_shave_a_compliant_value():
    noisy = 13.2 - 7.2  # 5.999999999999999
    assert units.round_conservative(noisy, ">=") == 6.0


def test_tolerance_reports_the_limit_without_turning_a_fail_into_a_pass():
    comparison = units.compare(2.4996, ">=", 2.5)
    assert comparison.at_limit and not comparison.passes
    assert "at the limit" in comparison.describe()


def test_exact_value_passes_and_is_flagged_at_the_limit():
    comparison = units.compare(2.5, ">=", 2.5)
    assert comparison.passes and comparison.at_limit


def test_units_convert_and_refuse_incompatible_dimensions():
    assert units.convert(250, "cm", "m") == pytest.approx(2.5)
    with pytest.raises(units.UnitError):
        units.convert(10, "m2", "m")


def test_compare_rejects_an_unknown_operator():
    with pytest.raises(ValueError):
        units.compare(1.0, "~=", 1.0)


def test_setback_is_measured_to_the_plot_line():
    plot = geo.Box(0, 0, 40, 30)
    element = geo.Box(5, 20, 20, 7.4)
    assert geo.setback(element, plot, "north") == pytest.approx(2.6)
    assert geo.setback(element, plot, "south") == pytest.approx(20.0)


def test_overlap_and_clear_gap():
    a = geo.Box(0, 0, 2, 2)
    assert geo.overlap(a, geo.Box(1, 1, 2, 2)) == pytest.approx(1.0)
    assert geo.overlap(a, geo.Box(2, 0, 2, 2)) == 0.0  # touching is not overlapping
    assert geo.clear_gap(a, geo.Box(3, 0, 1, 1)) == pytest.approx(1.0)


def test_resize_anchor_decides_which_edge_moves():
    box = geo.Box(8.5, 2.0, 2.4, 5.0)
    assert box.resized(w=2.5, anchor="south_west").x == pytest.approx(8.5)
    assert box.resized(w=2.5, anchor="north_east").x_max == pytest.approx(10.9)
    assert box.resized(w=2.5, anchor="centre").centre[0] == pytest.approx(box.centre[0])


def test_polygon_geometry_falls_back_to_its_bounding_box():
    box = geo.box_from_dict({"kind": "polygon", "points": [[0, 0], [4, 0], [4, 3], [0, 3]]})
    assert (box.w, box.h) == (4, 3)
    assert geo.polygon_area([(0, 0), (4, 0), (4, 3), (0, 3)]) == pytest.approx(12.0)
