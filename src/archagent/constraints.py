"""The constraint engine (SKILL.md 8).

Holds the full constraint ledger - statutory rules, the comments being
answered, project requirements and the implicit "do not break what is already
approved" constraints - evaluates it against a model, and resolves conflicts
by priority and by source rank.
"""

from __future__ import annotations

import re
from typing import Iterable

from . import units
from .comments import CommentAnalyzer
from .drawing.api import DrawingAPIError, DrawingDriver, MeasurementError
from .models import (
    Constraint,
    ConstraintValidation,
    MunicipalComment,
    Priority,
    Requirement,
)

#: Source ranking of SKILL.md 3.4, lower is stronger.
SOURCE_RANK = {
    "Municipal Comment": 0,
    "Zoning Plan": 1,
    "Planning Regulation": 1,
    "Project Requirement": 2,
    "Source Model": 3,
    "Previous Submission": 4,
    "Reference": 5,
    "Approved Design": 3,
}

CRITICAL_KEYWORDS = (
    "setback", "building line", "floor area", "fire", "egress", "escape",
    "accessib", "clearance", "height limit", "coverage",
)

_PRIORITY_TAG = re.compile(r"\[(?P<priority>critical|high|medium|low)\]", re.I)


class ConstraintLedger:
    """The set of constraints in force for a project."""

    def __init__(self, constraints: Iterable[Constraint] = ()):  # noqa: B006 - immutable default
        self._constraints: list[Constraint] = list(constraints)

    def __iter__(self):
        return iter(self._constraints)

    def __len__(self) -> int:
        return len(self._constraints)

    @property
    def all(self) -> list[Constraint]:
        return list(self._constraints)

    def add(self, constraint: Constraint) -> Constraint:
        if any(c.constraint_id == constraint.constraint_id for c in self._constraints):
            raise ValueError(f"duplicate constraint id: {constraint.constraint_id}")
        self._constraints.append(constraint)
        return constraint

    def get(self, constraint_id: str) -> Constraint | None:
        return next((c for c in self._constraints if c.constraint_id == constraint_id), None)

    def for_comment(self, comment_id: str) -> list[Constraint]:
        return [c for c in self._constraints if c.origin_comment_id == comment_id]

    def next_id(self, prefix: str = "P") -> str:
        used = {c.constraint_id for c in self._constraints}
        index = 1
        while f"{prefix}-{index:03d}" in used:
            index += 1
        return f"{prefix}-{index:03d}"

    # ------------------------------------------------------------------
    # evaluation
    # ------------------------------------------------------------------
    def evaluate(self, driver: DrawingDriver,
                 constraints: Iterable[Constraint] | None = None) -> list[ConstraintValidation]:
        results = []
        for constraint in (constraints if constraints is not None else self._constraints):
            results.append(evaluate_constraint(driver, constraint))
        return results


def evaluate_constraint(driver: DrawingDriver, constraint: Constraint) -> ConstraintValidation:
    """Measure a constraint on the live model; never infer from an edit log."""
    test = constraint.test
    if test is None:
        return ConstraintValidation(
            constraint_id=constraint.constraint_id, status="not_evaluated",
            priority=constraint.priority, rule=constraint.rule,
            note="constraint has no machine-testable form",
        )
    try:
        measurement = driver.measure(test.subject, test.metric, test.basis)
    except (DrawingAPIError, MeasurementError, ValueError) as error:
        return ConstraintValidation(
            constraint_id=constraint.constraint_id, status="not_evaluated",
            priority=constraint.priority, rule=constraint.rule,
            required=test.value, unit=test.unit, op=test.op,
            note=f"could not be measured: {error}",
        )
    comparison = units.compare(measurement.value, test.op, test.value, test.unit, measurement.unit)
    return ConstraintValidation(
        constraint_id=constraint.constraint_id,
        status="pass" if comparison.passes else "fail",
        priority=constraint.priority,
        rule=constraint.rule,
        measured=comparison.measured,
        required=test.value,
        unit=test.unit,
        op=test.op,
        at_limit=comparison.at_limit,
    )


# ----------------------------------------------------------------------
# construction
# ----------------------------------------------------------------------
def priority_for(rule: str, source: str, explicit: str | None = None) -> Priority:
    if explicit:
        return Priority(explicit.casefold())
    lowered = rule.casefold()
    if source in ("Zoning Plan", "Planning Regulation"):
        return Priority.CRITICAL
    if any(word in lowered for word in CRITICAL_KEYWORDS):
        return Priority.CRITICAL
    if source == "Municipal Comment":
        return Priority.HIGH
    return Priority.MEDIUM


def constraints_from_comments(comments: Iterable[MunicipalComment],
                              ledger: ConstraintLedger) -> list[Constraint]:
    """Every comment with a testable requirement becomes a constraint."""
    created = []
    for comment in comments:
        if comment.requirement is None:
            continue
        constraint = Constraint(
            constraint_id=f"MC-{comment.comment_id}",
            source="Municipal Comment",
            source_ref=comment.source_ref,
            rule=comment.normalized_requirement,
            priority=priority_for(comment.normalized_requirement, "Municipal Comment"),
            test=comment.requirement,
            origin_comment_id=comment.comment_id,
            confidence=comment.confidence.value,
        )
        created.append(ledger.add(constraint))
    return created


def constraints_from_document(text: str, source: str, source_ref: str,
                              ledger: ConstraintLedger,
                              analyzer: CommentAnalyzer | None = None) -> list[Constraint]:
    """Parse a zoning plan / requirements document into constraints.

    Lines that cannot be turned into a testable rule are still recorded, with
    ``test=None``; they validate as ``not_evaluated`` and surface as open items
    rather than disappearing.
    """
    analyzer = analyzer or CommentAnalyzer()
    created: list[Constraint] = []
    for raw_line in text.splitlines():
        line = raw_line.strip().lstrip("-*• ")
        if not line or line.startswith("#"):
            continue
        tag = _PRIORITY_TAG.search(line)
        explicit = tag.group("priority").casefold() if tag else None
        clean = _PRIORITY_TAG.sub("", line).strip()
        if len(clean) < 8:
            continue
        requirement, _action, _notes, confidence = analyzer.parse(clean)
        if requirement is None and not re.search(r"\d", clean):
            continue
        constraint = Constraint(
            constraint_id=ledger.next_id("P"),
            source=source,
            source_ref=source_ref,
            rule=requirement.describe() if requirement else clean,
            priority=priority_for(clean, source, explicit),
            test=requirement,
            confidence=confidence,
        )
        if requirement is None:
            constraint.rule = clean
        created.append(ledger.add(constraint))
    return created


def derive_implicit_constraints(driver: DrawingDriver, ledger: ConstraintLedger) -> list[Constraint]:
    """Record what the approved design already achieves (SKILL.md 8.2).

    These are MEDIUM priority: they express "do not degrade this", and they
    lose to a municipal comment that requires the change.
    """
    created: list[Constraint] = []

    def add(rule: str, test: Requirement) -> None:
        created.append(ledger.add(Constraint(
            constraint_id=ledger.next_id("A"),
            source="Approved Design",
            rule=rule,
            priority=Priority.MEDIUM,
            test=test,
            implicit=True,
            confidence=0.9,
        )))

    try:
        parking = driver.measure({"selector": {"type": "parking"}}, "count")
        if parking.value:
            add(f"parking count must not fall below the approved {int(parking.value)}",
                Requirement(subject={"selector": {"type": "parking"}}, metric="count",
                            op=">=", value=parking.value, unit="count"))
    except DrawingAPIError:
        pass

    for element in getattr(driver, "elements", list)():
        props = element.get("properties", {})
        if not props.get("approved"):
            continue
        for parameter in ("width", "length"):
            try:
                measurement = driver.measure({"element_id": element["id"]}, parameter)
            except DrawingAPIError:
                continue
            add(f"{element.get('label', element['id'])} {parameter} must not fall below "
                f"the approved {units.format_value(measurement.value)}",
                Requirement(subject={"element_id": element["id"], "label": element.get("label", "")},
                            metric=parameter, op=">=", value=round(measurement.value, 3)))
    return created


# ----------------------------------------------------------------------
# conflicts
# ----------------------------------------------------------------------
def _subject_key(requirement: Requirement) -> tuple:
    subject = requirement.subject
    key = subject.get("element_id") or tuple(sorted((subject.get("selector") or {}).items()))
    return (key, subject.get("edge", ""), requirement.metric)


def find_conflicts(ledger: ConstraintLedger) -> list[dict]:
    """Constraints that cannot all hold at once, with their resolution."""
    by_subject: dict[tuple, list[Constraint]] = {}
    for constraint in ledger:
        if constraint.test is None:
            continue
        by_subject.setdefault(_subject_key(constraint.test), []).append(constraint)

    conflicts = []
    for group in by_subject.values():
        for i, first in enumerate(group):
            for second in group[i + 1:]:
                if _incompatible(first.test, second.test):
                    conflicts.append(resolve_conflict(first, second))
    return conflicts


def _incompatible(a: Requirement, b: Requirement) -> bool:
    a_value = units.convert(a.value, a.unit, b.unit) if a.unit != b.unit else a.value
    lower_a = a.op in (">=", ">")
    lower_b = b.op in (">=", ">")
    if lower_a and not lower_b:
        return a_value > b.value + units.EPS
    if lower_b and not lower_a:
        return b.value > a_value + units.EPS
    if a.op == "==" and b.op == "==":
        return abs(a_value - b.value) > units.EPS
    if a.op == "==" and not lower_b:
        return a_value > b.value + units.EPS
    if b.op == "==" and not lower_a:
        return b.value > a_value + units.EPS
    return False


def resolve_conflict(first: Constraint, second: Constraint) -> dict:
    """Apply SKILL.md 8.3 - priority, then source rank, then escalate."""
    conflict = {
        "constraints": [first.constraint_id, second.constraint_id],
        "rules": [first.rule, second.rule],
        "resolution": "",
        "winner": "",
        "loser": "",
        "requires_human": False,
    }
    if first.priority is not second.priority:
        winner, loser = ((first, second) if first.priority.outranks(second.priority)
                         else (second, first))
        conflict.update(resolution="higher priority wins", winner=winner.constraint_id,
                        loser=loser.constraint_id)
        return conflict
    rank_first = SOURCE_RANK.get(first.source, 9)
    rank_second = SOURCE_RANK.get(second.source, 9)
    if rank_first != rank_second:
        winner, loser = ((first, second) if rank_first < rank_second else (second, first))
        conflict.update(resolution="stronger source wins (SKILL.md 3.4)",
                        winner=winner.constraint_id, loser=loser.constraint_id)
        return conflict
    conflict.update(resolution="equal priority and source: human decision required",
                    requires_human=True)
    return conflict
