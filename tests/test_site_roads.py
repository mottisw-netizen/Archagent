"""Typed road/curb/pipe objects (spec §9-10, §13)."""

from __future__ import annotations

from archagent.site import (
    Curb,
    Pipe,
    Sidewalk,
    pipe_slope,
    validate_curb_height,
    validate_sidewalk_slope,
)


def test_dropped_curb_vs_mountable_curb_distinguished_by_kind():
    dropped = Curb(curb_id="C-1", kind="dropped", height=0.02)
    mountable = Curb(curb_id="C-2", kind="mountable", height=0.08)
    assert dropped.kind != mountable.kind


def test_curb_height_bounds():
    curb = Curb(curb_id="C-1", height=0.05)
    assert validate_curb_height(curb, minimum=0.10) != []
    assert validate_curb_height(curb, maximum=0.03) != []
    assert validate_curb_height(curb, minimum=0.01, maximum=0.10) == []


def test_curb_with_no_height_is_not_checked():
    curb = Curb(curb_id="C-1")
    assert validate_curb_height(curb, minimum=0.1, maximum=0.2) == []


def test_sidewalk_slope_at_least_1_percent():
    compliant = Sidewalk(sidewalk_id="SW-1", slope=0.015)
    assert validate_sidewalk_slope(compliant, minimum=0.01) == []
    too_flat = Sidewalk(sidewalk_id="SW-2", slope=0.005)
    assert validate_sidewalk_slope(too_flat, minimum=0.01) != []


def test_pipe_slope_derived_from_invert_levels_and_length():
    pipe = Pipe(pipe_id="P-1", from_node="CB-1", to_node="CH-1",
               upstream_invert_level=99.0, downstream_invert_level=98.0, length=20.0)
    assert pipe_slope(pipe) == 0.05


def test_pipe_slope_none_when_data_missing():
    pipe = Pipe(pipe_id="P-1", from_node="CB-1", to_node="CH-1")
    assert pipe_slope(pipe) is None
