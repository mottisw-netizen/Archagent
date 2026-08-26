"""Step 5 - Mapping a comment to drawing elements (SKILL.md 7.1).

Every mapping records the evidence it used.  When several candidates survive
and nothing in the comment separates them, the mapping is ``ambiguous`` and the
run consults or escalates - it never picks the first candidate.
"""

from __future__ import annotations

from .drawing.api import DrawingAPIError, DrawingDriver
from .models import Candidate, ElementMapping, MunicipalComment, Requirement, Resolution

#: Metrics whose subject is legitimately a set of elements.
SET_METRICS = {"count", "floor_area", "area"}


class ElementMapper:
    def __init__(self, driver: DrawingDriver):
        self.driver = driver

    def map_comment(self, comment: MunicipalComment) -> ElementMapping:
        mapping = ElementMapping(comment_id=comment.comment_id)
        requirement = comment.requirement
        if requirement is None:
            mapping.notes = "comment carries no testable requirement"
            return mapping
        candidates = self._candidates(requirement)
        mapping.candidates = candidates
        if not candidates:
            mapping.resolution = Resolution.NOT_FOUND
            mapping.notes = "no element in the model matches the comment"
            return mapping
        if requirement.metric in SET_METRICS and requirement.subject.get("selector") is not None:
            mapping.selected = [c.element_id for c in candidates]
            mapping.resolution = Resolution.UNIQUE
        elif len(candidates) == 1:
            mapping.selected = [candidates[0].element_id]
            mapping.resolution = (
                Resolution.UNIQUE if candidates[0].confidence >= 0.9
                else Resolution.SELECTED_BY_DISCRIMINATOR
            )
        else:
            mapping.resolution = Resolution.AMBIGUOUS
            mapping.notes = (
                f"{len(candidates)} elements match and the comment names no discriminator"
            )
        mapping.before = self._before_values(requirement, mapping.selected)
        return mapping

    # ------------------------------------------------------------------
    def _candidates(self, requirement: Requirement) -> list[Candidate]:
        subject = requirement.subject
        if subject.get("element_id"):
            try:
                element = self.driver.get_element(subject["element_id"])
            except DrawingAPIError:
                return []
            return [Candidate(element["id"], [f"element_id:{element['id']}"], 0.99)]

        selector = dict(subject.get("selector") or {})
        if not selector:
            return []
        found = self.driver.find_element(**selector)
        basis = [f"{k}:{v}" for k, v in selector.items()]
        if not found and "label" in selector:
            found = self.driver.find_element(label_contains=selector["label"])
            basis.append("label_contains")
        confidence = self._confidence_for(selector, len(found))
        return [Candidate(element_id, list(basis), confidence) for element_id in found]

    @staticmethod
    def _confidence_for(selector: dict, hits: int) -> float:
        if hits == 0:
            return 0.0
        if "label" in selector:
            return 0.97 if hits == 1 else 0.6
        if "type" in selector and hits == 1:
            return 0.85
        return 0.7 if hits == 1 else 0.5

    def _before_values(self, requirement: Requirement, selected: list[str]) -> dict:
        if not selected:
            return {}
        subject = dict(requirement.subject)
        if requirement.metric in SET_METRICS:
            pass
        else:
            subject = {"element_id": selected[0]}
            if requirement.subject.get("edge"):
                subject["edge"] = requirement.subject["edge"]
            for key in ("against", "ignore", "ignore_types"):
                if requirement.subject.get(key):
                    subject[key] = requirement.subject[key]
        try:
            measurement = self.driver.measure(subject, requirement.metric, requirement.basis)
        except DrawingAPIError as error:
            return {"error": str(error)}
        return measurement.to_dict()


def identification_confidence(mapping: ElementMapping) -> float:
    if mapping.resolution is Resolution.NOT_FOUND:
        return 0.2
    if mapping.resolution is Resolution.AMBIGUOUS:
        return 0.5
    return max((c.confidence for c in mapping.candidates if c.element_id in mapping.selected),
               default=0.5)
