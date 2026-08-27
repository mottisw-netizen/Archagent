"""English lexicon."""

from __future__ import annotations

from .base import Lexicon

AT_LEAST = r"(?:at least|no less than|not less than|minimum(?: of)?|min\.?|>=)"
AT_MOST = r"(?:at most|no more than|not exceed|not more than|maximum(?: of)?|max\.?|<=)"

ENGLISH = Lexicon(
    code="en",
    name="English",
    departments={
        "planning": "Planning", "architecture": "Architecture", "licensing": "Licensing",
        "traffic": "Traffic", "transportation": "Traffic", "roads": "Traffic",
        "parking": "Parking", "accessibility": "Accessibility",
        "fire safety": "Fire Safety", "fire": "Fire Safety",
        "sanitation": "Sanitation", "water": "Water", "drainage": "Drainage",
        "landscaping": "Landscaping", "environment": "Environment",
        "infrastructure": "Infrastructure", "engineering": "Engineering",
    },
    metrics={
        r"clear width": "clear_width",
        r"floor area": "floor_area",
        r"built area": "floor_area",
        r"width": "width",
        r"length": "length",
        r"depth": "length",
        r"height": "height",
        r"area": "area",
        r"setback": "setback",
        r"building line": "setback",
        r"clearance": "clear_distance",
        r"distance": "clear_distance",
    },
    elements={
        r"parking spaces?": "parking", r"parking bays?": "parking", r"parking": "parking",
        r"driveway": "driveway", r"drive aisle": "driveway", r"aisle": "driveway",
        r"building": "building", r"balcony": "balcony", r"room": "room",
        r"corridor": "corridor", r"ramp": "ramp", r"window": "window",
        r"wall": "wall", r"road": "road", r"sidewalk": "sidewalk",
    },
    directions={
        r"northern": "north", r"north": "north", r"southern": "south", r"south": "south",
        r"eastern": "east", r"east": "east", r"western": "west", r"west": "west",
    },
    at_least=AT_LEAST,
    at_most=AT_MOST,
    increase_verbs=r"(?:increase|widen|enlarge|extend|raise)",
    decrease_verbs=r"(?:reduce|narrow|decrease|shorten)",
    set_verbs=r"(?:change|adjust|set|correct)",
    to_marker=r"(?:to|=)",
    unit_pattern=r"\s*(?P<unit>m²|m2|sqm|meters?|metres?|cm|mm|m)?\b",
    units={r"m²": "m2", r"m2": "m2", r"sqm": "m2", r"cm": "cm", r"mm": "mm",
           r"meters?": "m", r"metres?": "m", r"m": "m"},
    statements=(r"noted", r"no comment", r"for information", r"acknowledged"),
    annotations={
        r"schedules?": "update_schedule", r"tables?": "update_schedule",
        r"dimensions?": "update_dimension",
        r"labels?": "update_text", r"titles?": "update_text",
        r"texts?": "update_text", r"notes?": "update_text",
    },
    annotation_verbs=r"(?:add|update|correct|revise|fix|amend|complete)",
    count_nouns=(
        (r"accessible parking spaces?", {"type": "parking", "category": "accessible"}),
        (r"bicycle spaces?", {"type": "bicycle_parking"}),
        (r"parking spaces?", {"type": "parking"}),
        (r"parking bays?", {"type": "parking"}),
    ),
    department_line=r"^\s*(?:department|discipline|section)\s*[:\-]\s*(?P<name>.+?)\s*$",
    comment_id_patterns=(
        r"^\s*(?:(?P<full>[A-Z]{1,3}-\d{1,4})|(?P<num>\d{1,3}))\s*[.):\-]\s*(?P<body>.+)$",
        r"^\s*comment\s*(?P<num>\d{1,3})\s*[.):\-]\s*(?P<body>.+)$",
    ),
    label_patterns=(r"\b(?P<label>[A-Z]{1,3}[-_ ]?\d{1,3})\b",),
    implied_metrics=(
        (r"widen", "width", ">="),
        (r"narrow", "width", "<="),
        (r"lengthen|extend", "length", ">="),
        (r"shorten", "length", "<="),
        (r"raise|heighten", "height", ">="),
        (r"lower", "height", "<="),
    ),
    setback_order="direction_first",
)
