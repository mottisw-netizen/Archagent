"""Hebrew directional/relative-spatial/conditional vocabulary (spec §17/§26)."""

from __future__ import annotations

from archagent.lang.spatial import (
    intercardinal_direction_of,
    looks_conditional,
    spatial_relations_in,
)


def test_intercardinal_directions_both_spellings():
    assert intercardinal_direction_of("קו הבניין הצפון-מערבי") == "northwest"
    assert intercardinal_direction_of("בפינה הדרום מזרחית של המגרש") == "southeast"
    assert intercardinal_direction_of("קו בניין צפוני") is None  # plain cardinal, not compound


def test_relative_spatial_phrases_from_the_spec_list():
    assert spatial_relations_in("יש לשמור מרחק משפת הנסיעה") == ["from_drive_edge"]
    assert spatial_relations_in("מרחק 2 מ' מקו התיעול העירוני") == ["from_drainage_line"]
    assert "outside_plot" in spatial_relations_in("האלמנט ממוקם מחוץ למגרש")
    assert "inside_plot" in spatial_relations_in("הפיתוח כולו בתוך תחום המגרש")
    assert "adjacent" in spatial_relations_in("קיר בצמוד לגבול המגרש")


def test_no_relations_found_returns_empty_list():
    assert spatial_relations_in("יש לתקן את גובה החלון") == []


def test_conditional_markers_detected():
    assert looks_conditional("במידה ונדרש, יש לצרף דוח נוסף") is True
    assert looks_conditional("במידה וקיים קו ניקוז עירוני על המגרש") is True
    assert looks_conditional("כאשר קיימת בריכה יש למנות יועץ בטיחות") is True
    assert looks_conditional("במקרה של חריגה יש לתקן") is True
    assert looks_conditional("אם גובה המבנה עולה על 60 מ' נדרש אישור רת\"א") is True


def test_conditional_markers_do_not_false_positive_on_unrelated_words():
    assert looks_conditional("האם ידוע מספר החניות?") is False  # "האם" (whether), not "אם"
    assert looks_conditional("יש להגדיל את רוחב מקום החניה ל-2.50 מ'") is False
