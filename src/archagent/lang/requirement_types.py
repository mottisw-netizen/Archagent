"""Requirement-type classification (Petah Tikva spec §3).

A municipal comment is not only a measurable dimension. The same permit
record carries at least ten different requirement classes - a geometric
dimension, a document to attach, a professional approval gate, a stage
condition for the completion certificate, and so on. This module classifies
comment text into :class:`~archagent.models.RequirementType` deterministically,
from keyword patterns, the same way the rest of the parser works: a pattern
that does not match leaves the comment unclassified rather than guessed.

Classification is independent of, and runs alongside, the existing
measurable-requirement parser in :mod:`archagent.comments` - a comment can
both carry a :class:`~archagent.models.Requirement` (so it is measurable) and
classify as ``GEOMETRIC``, while a comment with no measurable requirement can
still classify as ``DOCUMENT`` or ``APPROVAL`` from its wording alone.
"""

from __future__ import annotations

import re

from ..models import RequirementType

#: Ordered (most specific first) so an "אישור עמידה" completion certificate
#: is never mistaken for a plain document submission.
_PATTERNS: dict[str, list[tuple[RequirementType, str]]] = {
    "he": [
        (RequirementType.COMPLETION_CONDITION,
         r"תעודת\s*גמר|טופס\s*4|טופס\s*ד['\"]?|אישור\s*עמיד[הת]|מכון\s*ההתעדה|"
         r"ת[\"']י\s*\d{3,4}"),
        (RequirementType.INSPECTION,
         r"לאחר\s*ביצוע|מדיד(?:ות|ה)\s*(?:בשטח|לאחר\s*ביצוע)|ניטור\s*לאחר"),
        (RequirementType.WORKFLOW_GATE,
         r"תחילת\s*עבודות|טרם\s*תחילת\s*עבודות"),
        (RequirementType.APPROVAL,
         r"נדרש\s*אישור|אישור\s*(?:אגף|מחלק[הת]|מדור)|טרם\s*בדיק[הת]\s*(?:ה)?תכני[הת]"),
        (RequirementType.DESIGN_DECISION,
         r"לבחון|לשקול|כדאי\s*לבחון|מומלץ\s*לשקול|לבדוק\s*אפשרות"),
        (RequirementType.CALCULATION,
         r"חישוב|יש\s*לחשב"),
        (RequirementType.DOCUMENT,
         r"לצרף|להגיש|דו[\"']ח|דוח|סקר\s*(?:אסבסט|עצים)?|תכנית\s*מאושרת"),
        (RequirementType.EVIDENCE,
         r"אסמכת[הא]|הוכח[הת]|ראי[הת]"),
        (RequirementType.GEOMETRIC,
         r"שיפוע|רדיוס(?:ים)?|מפלס|לתכנן|לסמן|קו\s*(?:ה)?בניי?ן|מרחק|קו\s*תיעול"),
    ],
    "en": [
        (RequirementType.COMPLETION_CONDITION,
         r"certificate of completion|form\s*4\b|completion condition|certification body"),
        (RequirementType.INSPECTION,
         r"post-construction|after construction|field measurement"),
        (RequirementType.WORKFLOW_GATE,
         r"start of work|commencement of works"),
        (RequirementType.APPROVAL,
         r"requires? approval|approval (?:is )?required|approval of the .* "
         r"(?:department|division)|(?:prior to|before) (?:the )?(?:departmental )?review"),
        (RequirementType.DESIGN_DECISION,
         r"\breconsider\b|\bconsider changing\b|\bconsider\b"),
        (RequirementType.CALCULATION,
         r"\bcalculation\b|\bcalculate\b"),
        (RequirementType.DOCUMENT,
         r"\bsubmit\b|\battach\b|\breport\b|\bsurvey\b"),
        (RequirementType.EVIDENCE,
         r"\bevidence\b|\bproof\b"),
        (RequirementType.GEOMETRIC,
         r"\bslope\b|\bradius\b|\belevation\b|\bclearance\b"),
    ],
}


def classify(text: str, language: str, has_requirement: bool,
             action: str = "") -> RequirementType | None:
    """The requirement type of one comment, or ``None`` if nothing matches.

    ``action`` starting with ``update_`` (an existing annotation-only
    correction - SKILL.md 5.2) always wins: it is a drawing annotation, not a
    document or approval gate, however the comment happens to be phrased.
    """
    if action.startswith("update_"):
        return RequirementType.ANNOTATION
    for req_type, pattern in _PATTERNS.get(language, _PATTERNS["en"]):
        if re.search(pattern, text, re.I):
            return req_type
    if has_requirement:
        return RequirementType.GEOMETRIC
    return None
