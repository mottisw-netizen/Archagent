"""Step 10 - execution (SKILL.md 11).

Each plan is a transaction: every action applies, or the model is rolled back
to the snapshot taken before the plan started.  Mutations are only possible
inside :meth:`DrawingDriver.authorised`, so an action that does not cite an
approved plan cannot reach the model at all.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .audit import AuditLog
from .drawing.api import DrawingAPIError, DrawingDriver
from .models import Action, ChangeRecord, CorrectionPlan


class PreconditionFailed(DrawingAPIError):
    pass


@dataclass
class ExecutionResult:
    plan_id: str
    ok: bool
    changes: list[ChangeRecord] = field(default_factory=list)
    error: str = ""
    rolled_back: bool = False

    def to_dict(self) -> dict:
        return {
            "plan_id": self.plan_id,
            "ok": self.ok,
            "changes": [c.to_dict() for c in self.changes],
            "error": self.error,
            "rolled_back": self.rolled_back,
        }


def check_preconditions(driver: DrawingDriver, plan: CorrectionPlan) -> list[str]:
    """Re-check every precondition against the live model (SKILL.md 9.1)."""
    failures = []
    for precondition in plan.preconditions:
        try:
            measurement = driver.measure({"element_id": precondition.element}, precondition.property)
        except DrawingAPIError as error:
            failures.append(f"{precondition.element}.{precondition.property}: {error}")
            continue
        expected = precondition.expected
        if expected is None:
            continue
        if abs(float(measurement.value) - float(expected)) > 1e-6:
            failures.append(
                f"{precondition.element}.{precondition.property} is {measurement.value:.3f}, "
                f"expected {float(expected):.3f}"
            )
    return failures


def apply_action(driver: DrawingDriver, action: Action) -> ChangeRecord:
    """Translate one plan action into a drawing-API call."""
    kind = action.action
    if kind in ("resize", "set_dimension"):
        return driver.resize_element(action.element, action.parameter,
                                     float(action.to_value if action.to_value is not None else action.value),
                                     anchor=action.anchor)
    if kind == "move":
        return driver.move_element(action.element, float(action.distance or 0.0), action.direction)
    if kind == "rotate":
        return driver.rotate_element(action.element, float(action.value or 0.0))
    if kind == "delete":
        return driver.delete_element(action.element)
    if kind == "create":
        return driver.create_element(action.parameter or "generic", action.value or {}, {"id": action.element})
    if kind == "update_text":
        return driver.update_text(action.element, action.text or str(action.to_value or ""))
    if kind == "update_dimension":
        value = None if action.to_value is None else float(action.to_value)
        return driver.update_dimension(action.element, value, recompute=value is None)
    if kind == "update_schedule":
        return driver.update_schedule(action.element, recompute=True)
    raise DrawingAPIError(f"unsupported action: {kind!r}")


def apply_plan(driver: DrawingDriver, plan: CorrectionPlan,
               comment_id: str = "") -> list[ChangeRecord]:
    """Apply every action of *plan*; the caller owns the transaction."""
    changes: list[ChangeRecord] = []
    with driver.authorised(plan.plan_id):
        for action in plan.plan:
            record = apply_action(driver, action)
            record.plan_id = plan.plan_id
            record.comment_id = comment_id or (plan.comment_ids[0] if plan.comment_ids else "")
            changes.append(record)
    return changes


class ExecutionAgent:
    """The only component that writes to the model (SKILL.md 2.1)."""

    def __init__(self, driver: DrawingDriver, audit: AuditLog | None = None):
        self.driver = driver
        self.audit = audit or AuditLog.null()

    def execute(self, plan: CorrectionPlan) -> ExecutionResult:
        snapshot = self.driver.snapshot()
        failures = check_preconditions(self.driver, plan)
        if failures:
            self.audit.write("execution_agent", "precondition_failed", plan_id=plan.plan_id,
                             result="aborted", details=failures)
            return ExecutionResult(plan.plan_id, False, error="; ".join(failures))
        try:
            changes = apply_plan(self.driver, plan)
        except DrawingAPIError as error:
            self.driver.restore(snapshot)
            self.audit.write("execution_agent", "api_error", plan_id=plan.plan_id,
                             result="rolled_back", details=str(error))
            return ExecutionResult(plan.plan_id, False, error=str(error), rolled_back=True)
        for change in changes:
            self.audit.write("execution_agent", "api_call", plan_id=plan.plan_id,
                             tool=change.tool, result="ok",
                             before=change.before, after=change.after,
                             params={"element_id": change.element_id, "property": change.property})
        return ExecutionResult(plan.plan_id, True, changes=changes)
