"""Multi-disciplinary planning alternatives (spec §25/§45).

Minimal-change planning has to become multi-disciplinary: a municipal
drainage line's required setback can be solved by moving an architectural
wall, diverting the drainage line, or redesigning the drainage solution - and
the planner must not silently pick one just because it can compute the
geometry for it. This module is a comparison structure, not a decision: it
never sets a "winner" on its own (``recommended_option_id`` defaults empty),
because the record's own architectural conclusion is explicit - the agent
must not automatically modify architecture when another discipline may own
the constraint.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import Serialisable


@dataclass
class PlanningAlternative(Serialisable):
    option_id: str
    description: str
    impacted_disciplines: list[str] = field(default_factory=list)
    consultant_ownership: str = ""
    requires_authority_approval: bool = False
    risk: str = "medium"  # low | medium | high
    cost_proxy: str = ""


@dataclass
class MultiDisciplinaryPlan(Serialisable):
    requirement_id: str
    situation: str
    alternatives: list[PlanningAlternative] = field(default_factory=list)
    #: Left blank on purpose - see module docstring. A consultant or the
    #: consultation flow sets this, never the planner by itself.
    recommended_option_id: str = ""

    def option(self, option_id: str) -> PlanningAlternative | None:
        return next((item for item in self.alternatives if item.option_id == option_id), None)


def drainage_setback_alternatives(requirement_id: str, setback_distance: float,
                                  required: float = 2.0) -> MultiDisciplinaryPlan:
    """The spec's own worked example: a municipal drainage line closer than
    the required separation forces a choice, not an automatic architectural
    change (§14, §25, §45)."""
    deficit = max(0.0, required - setback_distance)
    return MultiDisciplinaryPlan(
        requirement_id=requirement_id,
        situation=(f"the municipal drainage line is {setback_distance:.2f} m from the "
                  f"basement wall; {required:.2f} m separation is required"),
        alternatives=[
            PlanningAlternative(
                option_id="A", description=f"move the basement wall {deficit:.2f} m",
                impacted_disciplines=["architecture", "structure", "parking"],
                consultant_ownership="architect", requires_authority_approval=False,
                risk="medium"),
            PlanningAlternative(
                option_id="B", description="submit a drainage diversion plan",
                impacted_disciplines=["civil"], consultant_ownership="roads/drainage consultant",
                requires_authority_approval=True, risk="medium"),
            PlanningAlternative(
                option_id="C", description="redesign the drainage solution in place",
                impacted_disciplines=["civil"], consultant_ownership="roads/drainage consultant",
                requires_authority_approval=True, risk="high"),
        ],
    )
