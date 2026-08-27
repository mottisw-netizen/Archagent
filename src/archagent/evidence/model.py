"""Evidence and professional-approval schemas (Petah Tikva spec §15, §21, §38).

Not every requirement is closed by a drawing measurement. A hydrologic
report, an acoustic consultant's sign-off, a traffic-engineer approval - each
is evidence of a different kind, and a requirement that needs several kinds
at once is only :class:`ResolutionState`'s ``FULLY_RESOLVED`` when every kind
it actually needs is satisfied. Nothing here ever marks a document present,
signed, or approved unless the caller supplied data saying so (SKILL.md's
"the model interprets, the drawing measures" extends here to: the checker
reports, it never invents).
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field

from ..models import Serialisable, new_id


@dataclass
class Evidence(Serialisable):
    """One document/measurement offered in support of a requirement (§15)."""

    type: str
    evidence_id: str = field(default_factory=lambda: new_id("EV"))
    document: str = ""
    revision: str = ""
    date: str = ""
    prepared_by: str = ""
    professional_role: str = ""
    project_id: str = ""
    project_scope: str = ""
    covered_elements: list[str] = field(default_factory=list)
    measurements: list[dict] = field(default_factory=list)
    conclusions: list[str] = field(default_factory=list)
    #: pending | approved | rejected - never inferred, only ever what was supplied
    approval_status: str = "pending"
    authority: str = ""
    signed: bool = False
    current_revision: bool = True
    validity: str = ""
    required_stage: str = ""


class EvidenceStatus(str, enum.Enum):
    MISSING = "missing"
    INCOMPLETE = "incomplete"
    SATISFIED = "satisfied"


@dataclass
class EvidenceCheckResult(Serialisable):
    """Answers to the completeness questions of spec §28."""

    evidence_type: str
    status: EvidenceStatus
    present: bool = False
    correct_revision: bool | None = None
    signed: bool | None = None
    professional_role_correct: bool | None = None
    current: bool | None = None
    refers_to_project: bool | None = None
    covers_element: bool | None = None
    authority_approval_present: bool | None = None
    evidence_id: str = ""
    notes: list[str] = field(default_factory=list)


class ProfessionalApprovalStatus(str, enum.Enum):
    PENDING = "pending"
    PRESENT = "present"
    REJECTED = "rejected"
    NOT_REQUIRED = "not_required"


@dataclass
class ProfessionalApproval(Serialisable):
    """Ownership/sign-off tracking for one requirement (spec §8, §28)."""

    requirement_id: str
    professional_owner: str = ""
    required_license: str = ""
    required_signature: bool = True
    approval_status: ProfessionalApprovalStatus = ProfessionalApprovalStatus.PENDING
    document_ref: str = ""
    notes: str = ""

    @property
    def satisfied(self) -> bool:
        return self.approval_status in (
            ProfessionalApprovalStatus.PRESENT, ProfessionalApprovalStatus.NOT_REQUIRED)


class ResolutionState(str, enum.Enum):
    """Stricter resolution semantics (spec §38) - never "resolved" too early."""

    NOT_RESOLVED = "not_resolved"
    GEOMETRY_RESOLVED = "geometry_resolved"
    EVIDENCE_RESOLVED = "evidence_resolved"
    APPROVAL_RESOLVED = "approval_resolved"
    WORKFLOW_RESOLVED = "workflow_resolved"
    FULLY_RESOLVED = "fully_resolved"


_DIMENSIONS = ("geometry", "evidence", "approval", "workflow")
_STATE_BY_DIMENSION = {
    "geometry": ResolutionState.GEOMETRY_RESOLVED,
    "evidence": ResolutionState.EVIDENCE_RESOLVED,
    "approval": ResolutionState.APPROVAL_RESOLVED,
    "workflow": ResolutionState.WORKFLOW_RESOLVED,
}
_SATISFIED_PHRASE = {
    "geometry": "geometry corrected", "evidence": "evidence provided",
    "approval": "professional approval obtained", "workflow": "workflow gate cleared",
}
_PENDING_PHRASE = {
    "geometry": "geometry not yet corrected", "evidence": "evidence still required",
    "approval": "professional deliverable still required",
    "workflow": "workflow gate still blocking",
}


@dataclass
class ResolutionResult(Serialisable):
    state: ResolutionState
    satisfied: list[str] = field(default_factory=list)
    pending: list[str] = field(default_factory=list)

    def describe(self) -> str:
        if self.state is ResolutionState.NOT_RESOLVED and not self.satisfied and not self.pending:
            return "not resolved: no requirement dimensions apply"
        parts = [_SATISFIED_PHRASE[dim] for dim in self.satisfied]
        parts += [_PENDING_PHRASE[dim] for dim in self.pending]
        return "; ".join(parts) if parts else "not resolved"


def resolve(*, needs_geometry: bool = False, needs_evidence: bool = False,
            needs_approval: bool = False, needs_workflow: bool = False,
            geometry_ok: bool | None = None, evidence_ok: bool | None = None,
            approval_ok: bool | None = None, workflow_ok: bool | None = None) -> ResolutionResult:
    """A comment needing both geometry and approval is FULLY_RESOLVED only
    when both are satisfied (spec §38) - never earlier."""
    needed = {
        "geometry": (needs_geometry, geometry_ok), "evidence": (needs_evidence, evidence_ok),
        "approval": (needs_approval, approval_ok), "workflow": (needs_workflow, workflow_ok),
    }
    applicable = {name: bool(ok) for name, (needs, ok) in needed.items() if needs}
    if not applicable:
        return ResolutionResult(state=ResolutionState.NOT_RESOLVED)
    satisfied = [name for name in _DIMENSIONS if applicable.get(name)]
    pending = [name for name in _DIMENSIONS if name in applicable and not applicable[name]]
    if not pending:
        return ResolutionResult(state=ResolutionState.FULLY_RESOLVED, satisfied=satisfied)
    if not satisfied:
        return ResolutionResult(state=ResolutionState.NOT_RESOLVED, pending=pending)
    highest = max(satisfied, key=_DIMENSIONS.index)
    return ResolutionResult(state=_STATE_BY_DIMENSION[highest], satisfied=satisfied, pending=pending)
