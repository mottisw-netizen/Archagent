"""Structured conditional requirements (spec §6/§27)."""

from __future__ import annotations

import pytest

from archagent.conditional import Condition, ConditionalRequirement, evaluate


# ----------------------------------------------------------------------
# the spec's own worked example - municipal drainage line on plot
# ----------------------------------------------------------------------
def test_drainage_line_conditional_then_and_else():
    requirement = ConditionalRequirement(
        requirement_id="REQ-1",
        condition=Condition.exists("municipal_drainage_line_on_plot"),
        then_actions=["survey_line", "show_line", {"maintain_setback": "2.0m"}],
        else_actions=["no_action"],
    )
    assert requirement.resolve({"municipal_drainage_line_on_plot": True}) == [
        "survey_line", "show_line", {"maintain_setback": "2.0m"}]
    assert requirement.resolve({"municipal_drainage_line_on_plot": False}) == ["no_action"]
    assert requirement.resolve({}) == ["no_action"]  # absent fact reads as falsy, not fabricated


def test_from_dict_parses_the_spec_yaml_shape():
    data = {
        "condition": {"type": "exists", "subject": "municipal_drainage_line_on_plot"},
        "then": ["survey_line", "show_line", {"maintain_setback": "2.0m"}],
        "else": ["no_action"],
    }
    requirement = ConditionalRequirement.from_dict(data)
    assert requirement.resolve({"municipal_drainage_line_on_plot": True})[0] == "survey_line"


# ----------------------------------------------------------------------
# other conditions named explicitly by the spec (§6/§27)
# ----------------------------------------------------------------------
def test_building_height_threshold():
    condition = Condition.compare("building_height", ">", 60)
    assert evaluate(condition, {"building_height": 65}) is True
    assert evaluate(condition, {"building_height": 40}) is False
    assert evaluate(condition, {}) is False  # no height on record -> not triggered


def test_project_type_equality():
    condition = Condition.any_of(
        Condition.compare("project_type", "==", "public"),
        Condition.compare("project_type", "==", "commercial"),
    )
    assert evaluate(condition, {"project_type": "commercial"}) is True
    assert evaluate(condition, {"project_type": "residential"}) is False


def test_tree_count_threshold():
    condition = Condition.compare("tree_count", ">", 5)
    assert evaluate(condition, {"tree_count": 8}) is True
    assert evaluate(condition, {"tree_count": 3}) is False


def test_pool_and_anchors_existence():
    assert evaluate(Condition.exists("pool_exists"), {"pool_exists": True}) is True
    assert evaluate(Condition.exists("anchors_exist"), {"anchors_exist": False}) is False


def test_combined_and_not():
    condition = Condition.all_of(
        Condition.exists("pool_exists"),
        Condition.negate(Condition.exists("safety_consultant_assigned")),
    )
    assert evaluate(condition, {"pool_exists": True, "safety_consultant_assigned": False}) is True
    assert evaluate(condition, {"pool_exists": True, "safety_consultant_assigned": True}) is False


def test_unknown_condition_type_raises():
    with pytest.raises(ValueError):
        evaluate(Condition(type="not_a_real_type"), {})


def test_not_requires_exactly_one_subcondition():
    with pytest.raises(ValueError):
        evaluate(Condition(type="not", conditions=[]), {})
