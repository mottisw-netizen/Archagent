"""Submission readiness gate (spec §24/§47).

A deterministic final gate over everything else this layer computes -
validation, evidence, professional approvals, cross-discipline revalidation -
collapsed into one of three states. It is explicitly **not** a legal-authority
claim: see :data:`DISCLAIMER`, which any caller displaying
``READY_FOR_PROFESSIONAL_REVIEW`` should show alongside it.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field

from .models import Serialisable

DISCLAIMER = (
    "READY_FOR_PROFESSIONAL_REVIEW means the modelled requirements, evidence "
    "and approvals this run knows about are all in place. It is not a legal "
    "authority approval and does not mean the municipality has approved "
    "anything - the output remains a proposal for the responsible licensed "
    "professional to review."
)


class SubmissionReadiness(str, enum.Enum):
    READY_FOR_PROFESSIONAL_REVIEW = "ready_for_professional_review"
    NOT_READY = "not_ready"
    BLOCKED = "blocked"


@dataclass
class ReadinessAssessment(Serialisable):
    state: SubmissionReadiness
    reasons: list[str] = field(default_factory=list)

    def describe(self) -> str:
        if self.state is SubmissionReadiness.READY_FOR_PROFESSIONAL_REVIEW:
            return "ready for professional review"
        return "; ".join(self.reasons) or self.state.value


def assess_submission_readiness(
    *, validation_result: str = "passed",
    dropped_active_requirements: list[str] = (),
    open_authority_gates: list[str] = (),
    missing_evidence: list[str] = (),
    pending_professional_approvals: list[str] = (),
    unrevalidated_cross_discipline_impacts: list[str] = (),
) -> ReadinessAssessment:
    """BLOCKED beats NOT_READY: a hard validation failure or a silently
    dropped active requirement blocks submission outright. Anything else
    outstanding (an open gate, missing evidence, a pending sign-off, an
    unrevalidated cross-discipline impact) just means not ready yet."""
    blocking = []
    if validation_result == "failed":
        blocking.append("constraint validation failed (a critical requirement, a "
                        "regression, or a drawing check did not pass)")
    if dropped_active_requirements:
        blocking.append(f"{len(dropped_active_requirements)} active requirement(s) were "
                        "silently dropped: " + ", ".join(dropped_active_requirements))
    if blocking:
        return ReadinessAssessment(state=SubmissionReadiness.BLOCKED, reasons=blocking)

    outstanding = []
    if open_authority_gates:
        outstanding.append(f"{len(open_authority_gates)} authority gate(s) still open: "
                           + ", ".join(open_authority_gates))
    if missing_evidence:
        outstanding.append(f"{len(missing_evidence)} required evidence item(s) missing: "
                           + ", ".join(missing_evidence))
    if pending_professional_approvals:
        outstanding.append(f"{len(pending_professional_approvals)} professional approval(s) "
                           "pending: " + ", ".join(pending_professional_approvals))
    if unrevalidated_cross_discipline_impacts:
        outstanding.append(f"{len(unrevalidated_cross_discipline_impacts)} cross-discipline "
                           "impact(s) not yet revalidated: "
                           + ", ".join(unrevalidated_cross_discipline_impacts))
    if outstanding:
        return ReadinessAssessment(state=SubmissionReadiness.NOT_READY, reasons=outstanding)
    return ReadinessAssessment(state=SubmissionReadiness.READY_FOR_PROFESSIONAL_REVIEW)
