"""Step 11 - the validation agent (SKILL.md 14).

Validation re-measures the produced model.  It never trusts the edit log, and
a comment is only ``Resolved`` when a measurement proves it.
"""

from __future__ import annotations

from . import units
from .constraints import ConstraintLedger
from .drawing.api import DrawingAPIError, DrawingDriver
from .models import (
    CommentStatus,
    CommentValidation,
    MunicipalComment,
    Priority,
    ValidationResult,
)


SKIP_OVERLAP_TYPES = ("dimension", "text", "site", "building")


def find_overlaps(driver: DrawingDriver) -> list[str]:
    """Same-type elements on the same level that overlap in plan."""
    elements = getattr(driver, "elements", None)
    if elements is None:
        return []
    index = elements()
    conflicts = []
    for i, first in enumerate(index):
        for second in index[i + 1:]:
            if first.get("type") != second.get("type"):
                continue
            if first.get("type") in SKIP_OVERLAP_TYPES:
                continue
            if first.get("level", "") != second.get("level", ""):
                continue
            try:
                overlap = driver.check_overlap(first["id"], second["id"])
            except DrawingAPIError:
                continue
            if overlap["overlaps"] and overlap["area"] > 1e-6:
                conflicts.append(f"{first['id']} overlaps {second['id']} by {overlap['area']:.3f} m²")
    return conflicts


class ValidationAgent:
    def __init__(self, driver: DrawingDriver, ledger: ConstraintLedger,
                 baseline: dict[str, str] | None = None):
        self.driver = driver
        self.ledger = ledger
        self.baseline = baseline or {}

    # ------------------------------------------------------------------
    def validate(self, version: str, comments: list[MunicipalComment],
                 applied_comment_ids: set[str] | None = None) -> ValidationResult:
        applied = applied_comment_ids or set()
        result = ValidationResult(version=version)
        result.comments = [self.validate_comment(comment, comment.comment_id in applied)
                           for comment in comments]
        result.constraints = self.ledger.evaluate(self.driver)
        result.drawing_checks = self.drawing_checks()
        result.regressions = [
            {
                "constraint_id": item.constraint_id,
                "rule": item.rule,
                "priority": item.priority.value,
                "was": "pass",
                "now": "fail",
                "measured": item.measured,
                "required": item.required,
            }
            for item in result.constraints
            if item.status == "fail" and self.baseline.get(item.constraint_id) == "pass"
        ]
        result.result = self._verdict(result)
        return result

    # ------------------------------------------------------------------
    def validate_comment(self, comment: MunicipalComment, was_applied: bool) -> CommentValidation:
        if comment.required_action == "none":
            return CommentValidation(comment.comment_id, CommentStatus.NOT_APPLICABLE,
                                     note="statement only; no action demanded")
        if comment.requirement is None:
            if was_applied:
                return CommentValidation(
                    comment.comment_id, CommentStatus.ADDRESSED_NEEDS_CONFIRMATION,
                    note="the change was made, but the demand is not machine-measurable")
            return CommentValidation(
                comment.comment_id, CommentStatus.REQUIRES_HUMAN_REVIEW,
                note="no testable requirement could be extracted from the comment")
        requirement = comment.requirement
        try:
            measurement = self.driver.measure(requirement.subject, requirement.metric,
                                              requirement.basis)
        except DrawingAPIError as error:
            return CommentValidation(comment.comment_id, CommentStatus.REQUIRES_HUMAN_REVIEW,
                                     note=f"could not be measured: {error}")
        comparison = units.compare(measurement.value, requirement.op, requirement.value,
                                   requirement.unit, measurement.unit)
        evidence = {
            "metric": requirement.metric,
            "tool": measurement.tool,
            "basis": measurement.basis,
            **comparison.to_dict(),
        }
        if comparison.passes:
            status = CommentStatus.RESOLVED
            note = "at the limit" if comparison.at_limit else ""
        elif was_applied:
            status = CommentStatus.PARTIALLY_RESOLVED
            note = "a change was applied but the requirement is still not met"
        else:
            status = CommentStatus.NOT_RESOLVED
            note = "no valid change was applied"
        return CommentValidation(comment.comment_id, status, evidence, note)

    # ------------------------------------------------------------------
    def drawing_checks(self) -> list[dict]:
        checks: list[dict] = []
        elements = getattr(self.driver, "elements", None)
        if elements is None:
            return [{"check": "drawing_checks", "status": "not_evaluated",
                     "details": ["driver does not expose an element index"]}]
        index = elements()
        ids = [element["id"] for element in index]
        duplicates = sorted({element_id for element_id in ids if ids.count(element_id) > 1})
        checks.append(self._check("duplicate_elements", duplicates))

        broken: list[str] = []
        for element in index:
            properties = element.get("properties", {})
            measures = properties.get("measures", {})
            if measures and measures.get("element_id") not in ids:
                broken.append(f"{element['id']} dimensions a missing element "
                              f"{measures.get('element_id')!r}")
            for related in properties.get("related_elements", []):
                if related not in ids:
                    broken.append(f"{element['id']} references a missing element {related!r}")
        checks.append(self._check("broken_references", broken))

        overlaps = find_overlaps(self.driver)
        checks.append(self._check("spatial_conflicts", overlaps))

        stale: list[str] = []
        schedules = getattr(self.driver, "schedules", None)
        if schedules is not None:
            for schedule_id, schedule in schedules().items():
                source = schedule.get("source", {})
                if not source:
                    continue
                expected = len(self.driver.find_element(**source))
                actual = len(schedule.get("rows", []))
                if expected != actual:
                    stale.append(f"{schedule_id}: {actual} rows for {expected} elements")
        checks.append(self._check("schedules", stale))

        unsheeted = [element["id"] for element in index
                     if element.get("type") not in ("site",) and not element.get("sheet")]
        checks.append(self._check("sheet_assignment", unsheeted, severity="info"))
        return checks

    @staticmethod
    def _check(name: str, problems: list[str], severity: str = "error") -> dict:
        return {
            "check": name,
            "status": "pass" if not problems else ("warn" if severity == "info" else "fail"),
            "details": problems,
        }

    @staticmethod
    def _verdict(result: ValidationResult) -> str:
        critical_failures = [c for c in result.constraints
                             if c.status == "fail" and c.priority is Priority.CRITICAL]
        failed_checks = [c for c in result.drawing_checks if c["status"] == "fail"]
        if critical_failures or result.regressions or failed_checks:
            return "failed"
        open_items = [c for c in result.constraints if c.status != "pass"]
        open_comments = [c for c in result.comments
                         if c.status not in (CommentStatus.RESOLVED, CommentStatus.NOT_APPLICABLE)]
        if open_items or open_comments:
            return "passed_with_open_items"
        return "passed"
