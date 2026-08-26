"""Step 8 - simulation and pre-validation (SKILL.md 9.1).

A plan is applied to an isolated sandbox copy of the model and the *whole*
constraint ledger is re-measured there.  Nothing reaches the real model until
this passes: a plan that breaks a CRITICAL constraint in simulation is never
executed.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .constraints import ConstraintLedger
from .drawing.api import DrawingAPIError, DrawingDriver
from .execute import apply_plan, check_preconditions
from .models import ChangeRecord, ConstraintValidation, CorrectionPlan, Priority
from .validate import find_overlaps


@dataclass
class SimulationResult:
    plan_id: str
    ok: bool
    changes: list[ChangeRecord] = field(default_factory=list)
    results: list[ConstraintValidation] = field(default_factory=list)
    violations: list[ConstraintValidation] = field(default_factory=list)
    regressions: list[dict] = field(default_factory=list)
    critical_violations: list[ConstraintValidation] = field(default_factory=list)
    pre_existing_violations: list[ConstraintValidation] = field(default_factory=list)
    spatial_conflicts: list[str] = field(default_factory=list)
    error: str = ""
    sandbox: DrawingDriver | None = None

    @property
    def safe(self) -> bool:
        return (self.ok and not self.critical_violations and not self.regressions
                and not self.spatial_conflicts)

    def to_dict(self) -> dict:
        return {
            "plan_id": self.plan_id,
            "ok": self.ok,
            "safe": self.safe,
            "changes": [c.to_dict() for c in self.changes],
            "violations": [v.to_dict() for v in self.violations],
            "pre_existing_violations": [v.to_dict() for v in self.pre_existing_violations],
            "critical_violations": [v.to_dict() for v in self.critical_violations],
            "regressions": self.regressions,
            "spatial_conflicts": self.spatial_conflicts,
            "error": self.error,
        }


def baseline_status(driver: DrawingDriver, ledger: ConstraintLedger) -> dict[str, str]:
    """Constraint statuses before any change - the reference for regressions."""
    return {result.constraint_id: result.status for result in ledger.evaluate(driver)}


def baseline_overlaps(driver: DrawingDriver) -> set[str]:
    """Overlaps that already exist, so only *new* ones count against a plan."""
    return set(find_overlaps(driver))


def simulate(driver: DrawingDriver, plan: CorrectionPlan, ledger: ConstraintLedger,
             baseline: dict[str, str] | None = None) -> SimulationResult:
    sandbox = driver.sandbox()
    failures = check_preconditions(sandbox, plan)
    if failures:
        return SimulationResult(plan.plan_id, False, error="; ".join(failures), sandbox=sandbox)
    try:
        changes = apply_plan(sandbox, plan)
    except DrawingAPIError as error:
        return SimulationResult(plan.plan_id, False, error=str(error), sandbox=sandbox)

    existing_overlaps = set(find_overlaps(driver))
    new_overlaps = [item for item in find_overlaps(sandbox) if item not in existing_overlaps]
    results = ledger.evaluate(sandbox)
    failures = [r for r in results if r.status == "fail"]
    # A constraint that was already failing before the change is not this plan's
    # doing: it is reported, but it never blocks the plan (SKILL.md 9.1, 14.2).
    pre_existing = [r for r in failures if baseline and baseline.get(r.constraint_id) == "fail"]
    violations = [r for r in failures if r not in pre_existing]
    critical = [r for r in violations if r.priority is Priority.CRITICAL]
    regressions = []
    if baseline:
        for result in results:
            if result.status == "fail" and baseline.get(result.constraint_id) == "pass":
                regressions.append({
                    "constraint_id": result.constraint_id,
                    "rule": result.rule,
                    "priority": result.priority.value,
                    "was": "pass",
                    "now": "fail",
                    "measured": result.measured,
                    "required": result.required,
                })
    return SimulationResult(
        plan_id=plan.plan_id, ok=True, changes=changes, results=results,
        violations=violations, regressions=regressions, critical_violations=critical,
        pre_existing_violations=pre_existing, spatial_conflicts=new_overlaps, sandbox=sandbox,
    )
