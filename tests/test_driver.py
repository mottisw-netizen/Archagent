import pytest

from archagent.drawing.api import (
    AmbiguousElement,
    ElementNotFound,
    NotAuthorised,
    UnsupportedOperation,
)
from archagent.drawing.json_model import JSONModelDriver


def test_mutation_without_an_approved_plan_is_refused(small_model):
    driver = JSONModelDriver(small_model)
    with pytest.raises(NotAuthorised):
        driver.resize_element("a", "width", 2.5)


def test_every_mutation_reports_before_and_after(small_model):
    driver = JSONModelDriver(small_model)
    with driver.authorised("PLAN-1"):
        record = driver.resize_element("a", "width", 2.5)
    assert (record.before, record.after) == (2.4, 2.5)
    assert record.plan_id == "PLAN-1"
    assert record.tool == "resize_element"


def test_authorisation_does_not_leak_outside_the_block(small_model):
    driver = JSONModelDriver(small_model)
    with driver.authorised("PLAN-1"):
        driver.resize_element("a", "width", 2.5)
    with pytest.raises(NotAuthorised):
        driver.resize_element("a", "width", 2.6)


def test_missing_element_and_ambiguous_subject_are_errors_not_guesses(small_model):
    driver = JSONModelDriver(small_model)
    with pytest.raises(ElementNotFound):
        driver.get_element("nope")
    with pytest.raises(AmbiguousElement):
        driver.measure({"selector": {"type": "parking"}}, "width")


def test_sandbox_is_isolated(small_model):
    driver = JSONModelDriver(small_model)
    sandbox = driver.sandbox()
    with sandbox.authorised("PLAN-1"):
        sandbox.resize_element("a", "width", 3.0)
    assert driver.measure({"element_id": "a"}, "width").value == 2.4


def test_snapshot_and_restore_undo_a_change(small_model):
    driver = JSONModelDriver(small_model)
    snapshot = driver.snapshot()
    with driver.authorised("PLAN-1"):
        driver.move_element("a", 1.0, "north")
    driver.restore(snapshot)
    assert driver.get_element_geometry("a")["bbox"]["y"] == 0


def test_schedule_recompute_reads_the_model(small_model):
    driver = JSONModelDriver(small_model)
    with driver.authorised("PLAN-1"):
        driver.resize_element("a", "width", 2.5)
        record = driver.update_schedule("table")
    assert record.after == [{"Mark": "A1", "Width": 2.5}, {"Mark": "B1", "Width": 2.4}]
    assert record.kind == "schedule"


def test_clear_width_subtracts_intrusions(small_model):
    small_model["elements"].append({
        "id": "aisle", "type": "driveway", "label": "aisle", "level": "L0",
        "geometry": {"kind": "rect", "x": 0, "y": 5.0, "w": 10.0, "h": 6.0},
        "properties": {"width_axis": "x"},
    })
    driver = JSONModelDriver(small_model)
    assert driver.measure({"element_id": "aisle"}, "clear_width").value == pytest.approx(10.0)
    small_model["elements"].append({
        "id": "bin", "type": "store", "label": "bin", "level": "L0",
        "geometry": {"kind": "rect", "x": 3.0, "y": 6.0, "w": 1.0, "h": 1.0},
        "properties": {},
    })
    driver = JSONModelDriver(small_model)
    assert driver.measure({"element_id": "aisle"}, "clear_width").value == pytest.approx(6.0)


def test_setback_needs_an_edge_and_a_plot(small_model):
    driver = JSONModelDriver(small_model)
    with pytest.raises(Exception):
        driver.measure({"element_id": "a"}, "setback")
    assert driver.measure({"element_id": "a", "edge": "north"}, "setback").value == pytest.approx(15.0)


def test_unsupported_metric_is_rejected(small_model):
    driver = JSONModelDriver(small_model)
    with pytest.raises(UnsupportedOperation):
        driver.measure({"element_id": "a"}, "carbon_footprint")


def test_count_and_floor_area(small_model):
    small_model["elements"][0]["properties"]["counts_as_floor_area"] = True
    small_model["elements"][0]["properties"]["floor_area_factor"] = 2
    driver = JSONModelDriver(small_model)
    assert driver.measure({"selector": {"type": "parking"}}, "count").value == 2
    assert driver.measure({"selector": {"counts_as_floor_area": True}},
                          "floor_area").value == pytest.approx(24.0)


def test_save_as_writes_a_loadable_model(small_model, tmp_path):
    driver = JSONModelDriver(small_model)
    path = driver.save_as(tmp_path / "out" / "model.json")
    assert JSONModelDriver.load(path).measure({"element_id": "a"}, "width").value == 2.4
