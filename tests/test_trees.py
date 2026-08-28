"""Tree / forestry model (spec §11, §30)."""

from __future__ import annotations

from archagent.site import Tree, requires_felling_license, validate_preservation_radius


def test_a_thick_trunk_meets_the_mature_tree_diameter_threshold():
    tree = Tree(tree_id="T-1", trunk_diameter=0.12)
    assert requires_felling_license(tree) is True


def test_a_thin_trunk_does_not():
    tree = Tree(tree_id="T-2", trunk_diameter=0.08)
    assert requires_felling_license(tree) is False


def test_the_residential_plot_threshold_is_stricter():
    tree = Tree(tree_id="T-3", trunk_diameter=0.15)
    assert requires_felling_license(tree, plot_use="other") is True
    assert requires_felling_license(tree, plot_use="residential") is False


def test_an_unmeasured_trunk_is_unknown_not_guessed_false():
    tree = Tree(tree_id="T-4")
    assert requires_felling_license(tree) is None


def test_preserved_tree_flags_nearby_work():
    tree = Tree(tree_id="T-1", species="oak", preservation_status="preserve",
               preservation_radius=5.0, x=0.0, y=0.0)
    issues = validate_preservation_radius(tree, {"DIG-1": (2.0, 0.0), "DIG-2": (10.0, 0.0)})
    assert issues == ["DIG-1 is 2.00 m from tree T-1, inside its 5.00 m preservation radius"]


def test_unassessed_tree_is_never_enforced():
    tree = Tree(tree_id="T-2", preservation_radius=5.0)  # status defaults to "unassessed"
    assert validate_preservation_radius(tree, {"DIG-1": (0.5, 0.5)}) == []


def test_removal_approved_tree_is_not_enforced():
    tree = Tree(tree_id="T-3", preservation_status="removal_approved", preservation_radius=5.0)
    assert validate_preservation_radius(tree, {"DIG-1": (0.0, 0.0)}) == []
