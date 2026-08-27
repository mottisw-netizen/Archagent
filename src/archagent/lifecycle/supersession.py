"""Review-round comparison (Petah Tikva spec §23).

A permit record contains repeated review rounds - "fix drainage" becomes
"provide drainage chamber dimensions" becomes "show chamber on development
plan" - an increasingly specific sequence describing *one* requirement, not
four unrelated tasks. This module matches a later round's comments against an
earlier round's by department and text similarity, deterministically: there
is no model call here, only token overlap, so the match is always explainable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..lang import clean
from ..models import MunicipalComment, Serialisable

#: Below this, two comments are treated as unrelated rather than a weak match.
DEFAULT_THRESHOLD = 0.22

_TRIGRAM_SIZE = 3


def _trigrams(text: str) -> set[str]:
    """Character trigrams of the comment, whitespace-collapsed.

    Hebrew review comments repeat one requirement across rounds with the same
    root words wearing different prefixes ("מערכת הניקוז" / "במערכת הניקוז") -
    a word-level match would treat those as different tokens. Character
    n-grams are indifferent to that inflection without needing a morphological
    analyzer, at the cost of being a cruder, purely lexical similarity - which
    is exactly the deterministic, explainable trade-off the rest of the rule
    parser makes elsewhere.
    """
    collapsed = "".join(clean(text).casefold().split())
    if len(collapsed) < _TRIGRAM_SIZE:
        return {collapsed} if collapsed else set()
    return {collapsed[i:i + _TRIGRAM_SIZE] for i in range(len(collapsed) - _TRIGRAM_SIZE + 1)}


def similarity(a: MunicipalComment, b: MunicipalComment) -> float:
    """Dice coefficient over character trigrams, 0.0 (unrelated) to 1.0."""
    grams_a, grams_b = _trigrams(a.original_text), _trigrams(b.original_text)
    if not grams_a or not grams_b:
        return 0.0
    overlap = len(grams_a & grams_b)
    return 2 * overlap / (len(grams_a) + len(grams_b))


@dataclass
class CommentEvolution(Serialisable):
    """One later-round comment matched back to an earlier one."""

    original_comment: str
    later_comment: str
    similarity: float
    same_requirement: bool
    changed_value: bool = False
    changed_scope: bool = False
    resolved_in_version: str = ""
    new_requirement: bool = False
    notes: list[str] = field(default_factory=list)


def _numbers(text: str) -> set[str]:
    return set(re.findall(r"\d+(?:[.,]\d+)?", text))


def evolve(previous: list[MunicipalComment], current: list[MunicipalComment],
           threshold: float = DEFAULT_THRESHOLD) -> list[CommentEvolution]:
    """Match each comment of the current round against the previous round.

    Matching is greedy and one-to-one: each previous comment can be claimed by
    at most one current comment, its best match, so long as the match clears
    ``threshold`` and the two share a department. A current comment that
    matches nothing is a genuinely new requirement (``new_requirement=True``),
    never silently attached to an unrelated earlier row.
    """
    claimed: set[str] = set()
    evolutions: list[CommentEvolution] = []
    for later in current:
        best: MunicipalComment | None = None
        best_score = 0.0
        for earlier in previous:
            if earlier.comment_id in claimed:
                continue
            if earlier.department != later.department:
                continue
            score = similarity(earlier, later)
            if score > best_score:
                best, best_score = earlier, score
        if best is None or best_score < threshold:
            evolutions.append(CommentEvolution(
                original_comment="", later_comment=later.comment_id,
                similarity=0.0, same_requirement=False, new_requirement=True))
            continue
        claimed.add(best.comment_id)
        changed_value = _numbers(best.original_text) != _numbers(later.original_text)
        changed_scope = (best.normalized_requirement or best.required_action) != (
            later.normalized_requirement or later.required_action)
        notes = []
        if changed_value:
            notes.append("the required value changed between review rounds")
        if changed_scope and not changed_value:
            notes.append("the requirement was narrowed or re-scoped, not merely re-measured")
        evolutions.append(CommentEvolution(
            original_comment=best.comment_id, later_comment=later.comment_id,
            similarity=round(best_score, 3), same_requirement=True,
            changed_value=changed_value, changed_scope=changed_scope, notes=notes))
    return evolutions
