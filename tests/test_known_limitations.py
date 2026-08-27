"""Known, disclosed limitations of the deterministic (rules-only) parser.

These are not desired behaviour - they are here so a real limitation stays
visible and tracked instead of silently rediscovered later. If the LLM
interpreter is attached (archagent.llm), it cross-checks the rule parser and
this kind of misread lowers confidence or is flagged as a disagreement
(SKILL.md §20.4); in rules-only mode there is no second reading to catch it.
"""

from __future__ import annotations

from archagent.comments import CommentAnalyzer


def test_percent_slope_can_be_misparsed_as_an_area_threshold():
    """Found while building the Petah Tikva regression corpus (spec §26,
    ">=1% paved area slope").

    The Hebrew word for "area" (`שטח`) is also the generic noun for "surface/
    ground" used in phrases like `השטח המרוצף` ("the paved area/surface").
    When a sentence mentions `שטח` as part of such a phrase *and* separately
    contains a percent bound elsewhere ("לא יפחת מ-1%"), the deterministic
    bound parser can match the wrong metric/value pair: it reads `שטח` as the
    `area` metric and attaches the percent's bare number to it, producing
    "area >= 1.00 m" - nonsense that has nothing to do with a 1% slope. The
    unit is silently dropped too, since `%` is not in HEBREW.unit_pattern at
    all.
    """
    comment = CommentAnalyzer().analyze_comment(
        "C-X", "יש לוודא כי שיפוע השטח המרוצף לא יפחת מ-1%.", department="Drainage")
    assert comment.requirement is not None
    assert comment.requirement.metric == "area"  # wrong: this is a slope comment
    assert comment.requirement.value == 1.0       # wrong: the "%" was dropped

    # Phrasing that avoids the word "שטח" is read correctly as unparseable
    # (percent slope has no supported unit) rather than misparsed:
    clean = CommentAnalyzer().analyze_comment(
        "C-X", "יש לוודא כי שיפוע הריצוף לא יפחת מ-1%.", department="Drainage")
    assert clean.requirement is None
