"""Direct manual editing (move/resize/delete) outside the comment pipeline."""

from __future__ import annotations

import pytest

from archagent.manual_edit import ManualEditError, apply_manual_edit, load_driver_for_edit


def test_first_edit_loads_the_original_source(project):
    driver, base_version, versions = load_driver_for_edit(project)
    assert base_version == "original"
    assert versions.versions() == []
    assert driver.get_element("parking_p12") is not None


def test_move_creates_a_new_immutable_version(project):
    driver, base_version, versions = load_driver_for_edit(project)
    before = driver.get_element("parking_p12")["geometry"]["x"]

    result = apply_manual_edit(versions, driver, base_version, "move",
                               "parking_p12", distance=1.0, direction="east")

    assert result.version == "v1"
    assert result.parent_version == "original"
    assert result.change.element_id == "parking_p12"
    moved = next(e for e in result.model["elements"] if e["id"] == "parking_p12")
    assert moved["geometry"]["x"] == pytest.approx(before + 1.0)

    # The version is really saved - a second edit picks up from v1.
    assert versions.versions() == ["v1"]


def test_second_edit_chains_onto_the_first(project):
    driver, base_version, versions = load_driver_for_edit(project)
    apply_manual_edit(versions, driver, base_version, "move",
                      "parking_p12", distance=1.0, direction="east")

    driver2, base_version2, versions2 = load_driver_for_edit(project)
    assert base_version2 == "v1"
    result2 = apply_manual_edit(versions2, driver2, base_version2, "delete", "parking_p13")
    assert result2.version == "v2"
    assert result2.parent_version == "v1"
    assert all(e["id"] != "parking_p13" for e in result2.model["elements"])


def test_editing_an_earlier_version_forks_rather_than_overwrites(project):
    driver, base_version, versions = load_driver_for_edit(project)
    apply_manual_edit(versions, driver, base_version, "move",
                      "parking_p12", distance=1.0, direction="east")

    # Go back to "original" deliberately and edit from there again.
    driver_again, _, versions_again = load_driver_for_edit(project, base_version="original")
    result = apply_manual_edit(versions_again, driver_again, "original", "delete", "parking_p11")
    assert result.version == "v2"          # next in the sequence, not v1 again
    assert result.parent_version == "original"


def test_unknown_action_is_rejected(project):
    driver, base_version, versions = load_driver_for_edit(project)
    with pytest.raises(ManualEditError):
        apply_manual_edit(versions, driver, base_version, "teleport", "parking_p12")


def test_missing_element_raises_manual_edit_error(project):
    driver, base_version, versions = load_driver_for_edit(project)
    with pytest.raises(ManualEditError):
        apply_manual_edit(versions, driver, base_version, "delete", "does-not-exist")


def test_unknown_base_version_is_rejected(project):
    with pytest.raises(ManualEditError):
        load_driver_for_edit(project, base_version="v99")
