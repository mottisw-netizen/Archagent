"""Step 7 - correction plan generation (SKILL.md 9).

The planner turns one comment into an explicit, simulated, approvable plan.
It follows the escalation order of 9.1 - annotation, then a single-element
geometry change, then a local multi-element change - and it never returns a
plan that breaks a CRITICAL constraint in simulation; it escalates instead.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from . import units
from .constraints import ConstraintLedger
from .drawing.api import DrawingAPIError, DrawingDriver
from .drawing.geometry import DIRECTIONS
from .mapping import identification_confidence
from .models import (
    Action,
    CorrectionPlan,
    ElementMapping,
    ExpectedEffect,
    MunicipalComment,
    Precondition,
    Requirement,
    Resolution,
)
from .simulate import SimulationResult, simulate

OPPOSITE = {"north": "south", "south": "north", "east": "west", "west": "east"}

#: Metrics the planner can change on its own.  Everything else is a design
#: decision and is escalated with a proposal (SKILL.md 21).
PLANNABLE_METRICS = {"width", "length", "height", "setback", "clear_width"}

STRUCTURAL_TYPES = {"wall", "column", "beam", "slab", "core", "foundation"}
PROGRAM_METRICS = {"floor_area", "count", "area"}

_QUOTED = re.compile(r"[\"“”'‘’](?P<text>[^\"“”'‘’]{2,120})[\"“”'‘’]")


@dataclass
class PlanProposal:
    """A plan and everything the orchestrator needs to decide what to do."""

    plan: CorrectionPlan | None
    simulation: SimulationResult | None = None
    reasons: list[str] = None  # type: ignore[assignment]
    proposal_text: str = ""
    #: Alternative plans, already simulated, in the order they were offered.
    alternative_plans: list[tuple[CorrectionPlan, SimulationResult]] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.reasons is None:
            self.reasons = []
        if self.alternative_plans is None:
            self.alternative_plans = []


class Planner:
    def __init__(self, driver: DrawingDriver, ledger: ConstraintLedger,
                 baseline: dict[str, str] | None = None, threshold: float = 0.85):
        self.driver = driver
        self.ledger = ledger
        self.baseline = baseline or {}
        self.threshold = threshold
        self._counter = 0

    # ------------------------------------------------------------------
    def plan_for(self, comment: MunicipalComment, mapping: ElementMapping) -> PlanProposal:
        if comment.required_action == "none":
            return PlanProposal(None, reasons=["comment demands no action"])
        if comment.requirement is None:
            if comment.required_action in ("update_schedule", "update_dimension", "update_text"):
                return self._annotation_plan(comment, mapping)
            return PlanProposal(None, reasons=["no testable requirement could be extracted"])

        requirement = comment.requirement
        if mapping.resolution is Resolution.NOT_FOUND:
            return PlanProposal(None, reasons=[
                f"no element in the model matches {requirement.describe()}"])
        if mapping.resolution is Resolution.AMBIGUOUS:
            return PlanProposal(None, reasons=[mapping.notes or "ambiguous element match"])

        if requirement.metric in PROGRAM_METRICS:
            return PlanProposal(None, reasons=[
                f"{requirement.metric} is a program-level change; it is a design decision, "
                "not a minimal correction"],
                proposal_text=self._program_proposal(comment, mapping, requirement))
        if requirement.metric not in PLANNABLE_METRICS:
            return PlanProposal(None, reasons=[f"no planning strategy for metric {requirement.metric!r}"])

        element_id = mapping.selected[0]
        try:
            current = self.driver.measure(self._subject(requirement, element_id),
                                          requirement.metric, requirement.basis)
        except DrawingAPIError as error:
            return PlanProposal(None, reasons=[f"current value could not be measured: {error}"])

        comparison = units.compare(current.value, requirement.op, requirement.value,
                                   requirement.unit, current.unit)
        if comparison.passes:
            plan = self._empty_plan(comment, element_id, requirement, current)
            return PlanProposal(plan, None, ["already compliant; no change required"])

        variants = self._variants(comment, mapping, requirement, element_id, current.value)
        if not variants:
            return PlanProposal(None, reasons=[
                f"no minimal change was found that satisfies {requirement.describe()}"])

        scored = []
        for plan in variants:
            result = simulate(self.driver, plan, self.ledger, self.baseline)
            scored.append((self._score(result), plan, result))
        scored.sort(key=lambda item: item[0])

        best_score, best_plan, best_result = scored[0]
        safe_variants = [item for item in scored if item[2].safe]
        for _score, plan, result in scored:
            plan.notes.append(f"simulation: {'safe' if result.safe else 'unsafe'}")
        if not safe_variants:
            reasons = ["every candidate change breaks a constraint or creates a conflict"]
            reasons += [f"spatial conflict: {item}" for item in best_result.spatial_conflicts]
            for violation in best_result.critical_violations or best_result.violations:
                reasons.append(
                    f"{violation.constraint_id} ({violation.priority.value}): {violation.rule} -> "
                    f"measured {units.format_value(violation.measured or 0.0, violation.unit, violation.op)}")
            return PlanProposal(None, best_result, reasons,
                                self._blocked_proposal(comment, best_plan, best_result))

        _score, plan, result = safe_variants[0]
        plan.alternatives = [
            {"strategy": other.strategy, "actions": [a.describe() for a in other.plan],
             "safe": other_result.safe}
            for _s, other, other_result in safe_variants[1:]
        ]
        self._finalise(plan, comment, mapping, result, requirement)
        return PlanProposal(plan, result, [],
                            alternative_plans=[(other, other_result)
                                               for _s, other, other_result in safe_variants[1:]])

    # ------------------------------------------------------------------
    # plan construction
    # ------------------------------------------------------------------
    def _next_id(self, comment: MunicipalComment, suffix: str = "") -> str:
        self._counter += 1
        base = f"PLAN-{comment.comment_id}"
        return f"{base}-{suffix}" if suffix else base

    @staticmethod
    def _subject(requirement: Requirement, element_id: str) -> dict:
        subject = {"element_id": element_id}
        for key in ("edge", "against", "ignore", "ignore_types"):
            if requirement.subject.get(key):
                subject[key] = requirement.subject[key]
        return subject

    def _empty_plan(self, comment: MunicipalComment, element_id: str,
                    requirement: Requirement, current) -> CorrectionPlan:
        return CorrectionPlan(
            plan_id=self._next_id(comment, "noop"),
            comment_ids=[comment.comment_id],
            strategy=f"No change required: {requirement.describe()} already holds "
                     f"({current.formatted(requirement.op)})",
            status="already_compliant",
            deterministic=True,
            confidence=comment.confidence.with_(solution=0.98, verification=0.98),
        )

    def _variants(self, comment: MunicipalComment, mapping: ElementMapping,
                  requirement: Requirement, element_id: str, current: float) -> list[CorrectionPlan]:
        metric = requirement.metric
        target = units.convert(requirement.value, requirement.unit, "m")
        if metric in ("width", "length", "height"):
            return self._resize_variants(comment, element_id, metric, current, target, requirement)
        if metric == "setback":
            return self._setback_variants(comment, element_id, current, target, requirement)
        if metric == "clear_width":
            return self._clear_width_variants(comment, element_id, current, target, requirement)
        return []

    def _resize_variants(self, comment: MunicipalComment, element_id: str, parameter: str,
                         current: float, target: float, requirement: Requirement) -> list[CorrectionPlan]:
        element = self.driver.get_element(element_id)
        declared = element.get("properties", {}).get("anchor", "south_west")
        anchors = list(dict.fromkeys([declared, "south_west", "north_east", "centre"]))
        variants = []
        for anchor in anchors:
            action = Action(action="resize", element=element_id, parameter=parameter,
                            from_value=round(current, 3), to_value=round(target, 3), anchor=anchor)
            plan = CorrectionPlan(
                plan_id=self._next_id(comment, f"resize-{anchor}"),
                comment_ids=[comment.comment_id],
                strategy=f"Set {element.get('label', element_id)} {parameter} to "
                         f"{units.format_value(target)} (holding the {anchor.replace('_', ' ')} edge)",
                preconditions=[Precondition(element_id, parameter, round(current, 3))],
                plan=[action] + self._dependent_actions([element_id]),
                deterministic=False,
                rollback="restore the parent version",
            )
            variants.append(plan)
        return variants

    def _setback_variants(self, comment: MunicipalComment, element_id: str, current: float,
                          target: float, requirement: Requirement) -> list[CorrectionPlan]:
        edge = requirement.subject.get("edge", "north")
        if edge not in DIRECTIONS:
            return []
        delta = round(target - current, 4)
        if delta <= 0:
            return []
        element = self.driver.get_element(element_id)
        label = element.get("label", element_id)
        move = CorrectionPlan(
            plan_id=self._next_id(comment, "move"),
            comment_ids=[comment.comment_id],
            strategy=f"Move {label} {units.format_value(delta)} {OPPOSITE[edge]} to reach a "
                     f"{units.format_value(target)} {edge} setback",
            plan=[Action(action="move", element=element_id, distance=delta,
                         direction=OPPOSITE[edge])] + self._dependent_actions([element_id]),
            rollback="restore the parent version",
        )
        parameter = "length" if edge in ("north", "south") else "width"
        try:
            extent = self.driver.measure({"element_id": element_id}, parameter).value
        except DrawingAPIError:
            return [move]
        shrink = CorrectionPlan(
            plan_id=self._next_id(comment, "shrink"),
            comment_ids=[comment.comment_id],
            strategy=f"Pull the {edge} face of {label} back by {units.format_value(delta)} "
                     f"({parameter} {units.format_value(extent)} -> {units.format_value(extent - delta)})",
            preconditions=[Precondition(element_id, parameter, round(extent, 3))],
            plan=[Action(action="resize", element=element_id, parameter=parameter,
                         from_value=round(extent, 3), to_value=round(extent - delta, 3),
                         anchor=OPPOSITE[edge] + "_west" if edge in ("north", "south") else "south_" + OPPOSITE[edge])
                  ] + self._dependent_actions([element_id]),
            rollback="restore the parent version",
        )
        return [move, shrink]

    def _clear_width_variants(self, comment: MunicipalComment, element_id: str, current: float,
                              target: float, requirement: Requirement) -> list[CorrectionPlan]:
        measurement = self.driver.measure({"element_id": element_id}, "clear_width")
        if measurement.details.get("intrusions"):
            return []  # something is standing in it: that is a layout decision
        return self._resize_variants(comment, element_id, "width", current, target, requirement)

    def _annotation_plan(self, comment: MunicipalComment, mapping: ElementMapping) -> PlanProposal:
        action_kind = comment.required_action
        actions: list[Action] = []
        if action_kind == "update_schedule":
            for schedule_id in self._schedules_named(comment.original_text):
                actions.append(Action(action="update_schedule", element=schedule_id))
        elif action_kind == "update_dimension":
            for dimension_id in self._dimensions_for(mapping.selected):
                actions.append(Action(action="update_dimension", element=dimension_id))
        elif action_kind == "update_text":
            quoted = _QUOTED.search(comment.original_text)
            if not quoted or not mapping.selected:
                return PlanProposal(None, reasons=[
                    "the comment asks for a text change but does not state the replacement text"])
            actions.append(Action(action="update_text", element=mapping.selected[0],
                                  text=quoted.group("text")))
        if not actions:
            return PlanProposal(None, reasons=[
                f"nothing in the model matches the requested {action_kind.replace('update_', '')} change"])
        plan = CorrectionPlan(
            plan_id=self._next_id(comment, "annotate"),
            comment_ids=[comment.comment_id],
            strategy=f"{action_kind.replace('_', ' ')} ({len(actions)} item(s))",
            plan=actions,
            deterministic=True,
            confidence=comment.confidence.with_(solution=0.95, verification=0.9),
            rollback="restore the parent version",
        )
        result = simulate(self.driver, plan, self.ledger, self.baseline)
        if not result.ok:
            return PlanProposal(None, result, [f"simulation failed: {result.error}"])
        if not result.safe:
            return PlanProposal(None, result, ["annotation change breaks a constraint in simulation"])
        plan.expected_effects = self._effects(result)
        return PlanProposal(plan, result, [])

    # ------------------------------------------------------------------
    # dependent work
    # ------------------------------------------------------------------
    def _dependent_actions(self, element_ids: list[str]) -> list[Action]:
        """Dimensions and schedules that must follow a geometry change."""
        actions: list[Action] = []
        for dimension_id in self._dimensions_for(element_ids):
            actions.append(Action(action="update_dimension", element=dimension_id))
        schedules = getattr(self.driver, "schedules", None)
        if schedules is None:
            return actions
        for schedule_id, schedule in schedules().items():
            source = schedule.get("source", {})
            if not source:
                continue
            members = self.driver.find_element(**source)
            if any(element_id in members for element_id in element_ids):
                actions.append(Action(action="update_schedule", element=schedule_id))
        return actions

    def _dimensions_for(self, element_ids: list[str]) -> list[str]:
        elements = getattr(self.driver, "elements", None)
        if elements is None:
            return []
        found = []
        for element in elements():
            if element.get("type") != "dimension":
                continue
            measures = element.get("properties", {}).get("measures", {})
            if measures.get("element_id") in element_ids:
                found.append(element["id"])
        return found

    def _schedules_named(self, text: str) -> list[str]:
        schedules = getattr(self.driver, "schedules", None)
        if schedules is None:
            return []
        available = schedules()
        lowered = text.casefold()
        named = [sid for sid, schedule in available.items()
                 if any(word and word.casefold() in lowered
                        for word in (sid.replace("_", " "), schedule.get("title", "")))]
        return named or list(available)

    # ------------------------------------------------------------------
    # scoring and finalisation
    # ------------------------------------------------------------------
    def _score(self, result: SimulationResult) -> tuple:
        if not result.ok:
            return (9, 9, 9, 9.0)
        return (
            len(result.critical_violations),
            len(result.spatial_conflicts),
            len(result.regressions),
            len(result.violations),
            self._disturbance(result),
        )

    @staticmethod
    def _disturbance(result: SimulationResult) -> float:
        """How far the change pushes every other measured value."""
        return round(sum(abs(r.measured - r.required) for r in result.results
                         if r.measured is not None and r.required is not None), 3)

    def _effects(self, result: SimulationResult) -> list[ExpectedEffect]:
        effects = []
        for after in result.results:
            if after.measured is None:
                continue
            constraint = self.ledger.get(after.constraint_id)
            if constraint is None or constraint.test is None:
                continue
            try:
                before = self.driver.measure(constraint.test.subject, constraint.test.metric,
                                             constraint.test.basis).value
            except DrawingAPIError:
                continue
            if abs(before - after.measured) <= 1e-6:
                continue
            subject = constraint.test.subject
            edge = subject.get("edge")
            effects.append(ExpectedEffect(
                element=subject.get("element_id") or subject.get("label") or "project",
                property=f"{constraint.test.metric} ({edge})" if edge else constraint.test.metric,
                from_value=round(before, 3),
                to_value=round(after.measured, 3),
                constraint_id=after.constraint_id,
                still_compliant=after.status != "fail",
            ))
        return effects

    def _finalise(self, plan: CorrectionPlan, comment: MunicipalComment, mapping: ElementMapping,
                  result: SimulationResult, requirement: Requirement) -> None:
        plan.expected_effects = self._effects(result)
        plan.risk = self._risk(plan, result)
        solution = 0.95 if result.safe and not result.violations else 0.8
        verification = 0.97 if requirement.metric in PLANNABLE_METRICS else 0.6
        plan.confidence = comment.confidence.with_(
            identification=identification_confidence(mapping),
            solution=solution,
            verification=verification,
        )
        plan.consultation_reasons = self.consultation_reasons(plan, comment, mapping, result)
        plan.requires_consultation = bool(plan.consultation_reasons)
        plan.deterministic = (
            not plan.requires_consultation
            and plan.confidence.value >= 0.95
            and all(a.action in ("update_text", "update_dimension", "update_schedule")
                    for a in plan.plan)
        )

    @staticmethod
    def _risk(plan: CorrectionPlan, result: SimulationResult) -> str:
        if result.critical_violations or result.regressions:
            return "high"
        if result.violations or len(plan.plan) > 3:
            return "medium"
        return "low"

    def consultation_reasons(self, plan: CorrectionPlan, comment: MunicipalComment,
                             mapping: ElementMapping, result: SimulationResult) -> list[str]:
        """The triggers of SKILL.md 4.1, evaluated against a simulated plan."""
        reasons: list[str] = []
        if mapping.resolution is Resolution.AMBIGUOUS:
            reasons.append("the comment does not identify a single element")
        if plan.confidence.value < self.threshold:
            reasons.append(
                f"confidence {plan.confidence.value:.2f} is below the {self.threshold:.2f} threshold "
                f"(limited by {plan.confidence.limiting_component})")
        if result.spatial_conflicts:
            reasons.append("the correction creates a spatial conflict: "
                           + "; ".join(result.spatial_conflicts))
        if result.violations:
            reasons.append("the correction leaves another constraint unmet: "
                           + ", ".join(v.constraint_id for v in result.violations))
        for effect in plan.expected_effects:
            constraint = self.ledger.get(effect.constraint_id)
            metric = constraint.test.metric if constraint and constraint.test else ""
            if metric in PROGRAM_METRICS:
                reasons.append(f"the correction changes {metric} "
                               f"({effect.from_value} -> {effect.to_value})")
        for action in plan.plan:
            try:
                element = self.driver.get_element(action.element)
            except DrawingAPIError:
                continue
            properties = element.get("properties", {})
            if element.get("type") in STRUCTURAL_TYPES or properties.get("structural"):
                reasons.append(f"{action.element} is a structural element")
            if element.get("type") == "building":
                reasons.append("the correction changes the building footprint")
            consultant = properties.get("consultant")
            if consultant and consultant != "architecture":
                reasons.append(f"{action.element} belongs to another consultant ({consultant})")
        if len(plan.alternatives) >= 1:
            reasons.append("more than one valid solution exists")
        return list(dict.fromkeys(reasons))

    def _program_proposal(self, comment: MunicipalComment, mapping: ElementMapping,
                          requirement: Requirement) -> str:
        try:
            current = self.driver.measure(requirement.subject, requirement.metric, requirement.basis)
        except DrawingAPIError:
            return ""
        return (f"{requirement.describe()}; the model currently measures "
                f"{current.formatted(requirement.op)}. Closing the gap changes the project program, "
                "which is a design decision for the architect.")

    @staticmethod
    def _blocked_proposal(comment: MunicipalComment, plan: CorrectionPlan,
                          result: SimulationResult) -> str:
        blockers = ", ".join(f"{v.constraint_id} ({v.rule})"
                             for v in (result.critical_violations or result.violations))
        return (f"The minimal change ({plan.strategy}) would break {blockers}. "
                "Either the blocking constraint is relaxed by the authority, or the design "
                "changes more widely than this comment allows.")
