"""Hebrew directional/relative-spatial/conditional vocabulary (spec §17/§26).

Recognition only - deliberately *not* wired into the deterministic setback
parser in :mod:`archagent.comments`, whose ``Requirement.subject["edge"]``
value flows straight into :mod:`archagent.drawing.geometry`, which only knows
the four cardinal directions. Feeding it "northwest" would not fail
gracefully; it would raise deep inside measurement. So this module gives the
Petah Tikva record's compound-direction, relative-spatial and conditional
vocabulary a real, tested home as a *classifier* a caller can use - to flag
that a comment mentions "north-west", or "from the drive edge", or that it
reads as conditional and might be worth modelling as a
:class:`archagent.conditional.ConditionalRequirement` - without claiming the
existing geometry engine can act on an intercardinal direction it cannot
measure.
"""

from __future__ import annotations

import re

#: compound/intercardinal directions - not fed into Requirement construction;
#: see module docstring.
INTERCARDINAL_DIRECTIONS: dict[str, str] = {
    r"צפון[\s\-]?מזרח(?:ית?)?": "northeast",
    r"צפון[\s\-]?מערב(?:ית?)?": "northwest",
    r"דרום[\s\-]?מזרח(?:ית?)?": "southeast",
    r"דרום[\s\-]?מערב(?:ית?)?": "southwest",
}

#: relative spatial expressions (spec §26), each mapped to a short canonical
#: relation name a caller can key logic off without re-matching Hebrew text.
RELATIVE_SPATIAL: dict[str, str] = {
    r"מעל": "above",
    r"מתחת": "below",
    r"בצמוד|(?<![א-ת])צמוד": "adjacent",
    r"לפני": "before",
    r"אחרי": "after",
    r"מטר\s*פנימה": "one_meter_inward",
    r"מכיוון": "from_direction",
    r"לכיוון": "toward",
    r"מחוץ\s*למגרש": "outside_plot",
    r"בתוך\s*תחום\s*המגרש": "inside_plot",
    r"משפת\s*הנסיעה": "from_drive_edge",
    r"מקו\s*התיעול": "from_drainage_line",
}

#: conditional-language markers (spec §26/§27) - a comment matching one of
#: these is a candidate for a structured archagent.conditional.Condition
#: rather than a flat requirement; extracting the condition itself from the
#: prose is not done here (see SKILL.md §25.6).
CONDITIONAL_MARKERS = (
    r"במיד[הת]\s*ונדרש",
    r"במיד[הת]\s*ו",
    r"במקר[הת]\s*של",
    r"כאשר",
    r"(?<![א-ת])אם(?![א-ת])",
)


def intercardinal_direction_of(text: str) -> str | None:
    for pattern, canonical in INTERCARDINAL_DIRECTIONS.items():
        if re.search(pattern, text):
            return canonical
    return None


def spatial_relations_in(text: str) -> list[str]:
    """Every relative-spatial relation named in ``text``, canonical names,
    in the order :data:`RELATIVE_SPATIAL` lists them."""
    return [canonical for pattern, canonical in RELATIVE_SPATIAL.items()
           if re.search(pattern, text)]


def looks_conditional(text: str) -> bool:
    return any(re.search(pattern, text) for pattern in CONDITIONAL_MARKERS)
