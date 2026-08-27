"""Tracking professional approvals across a whole project (spec §8, §28).

Builds on :class:`archagent.evidence.model.ProfessionalApproval` (one
requirement's approval record) with a project-wide index, so a report can
answer "which requirements are geometrically done but still waiting on a
professional" without re-deriving it from the requirement list each time.
"""

from __future__ import annotations

from ..evidence.model import ProfessionalApproval, ProfessionalApprovalStatus
from .roles import Professional


class ApprovalTracker:
    def __init__(self) -> None:
        self.approvals: dict[str, ProfessionalApproval] = {}

    def require(self, requirement_id: str, professional_owner: str,
               required_license: str = "", required_signature: bool = True
               ) -> ProfessionalApproval:
        approval = ProfessionalApproval(
            requirement_id=requirement_id, professional_owner=professional_owner,
            required_license=required_license, required_signature=required_signature)
        self.approvals[requirement_id] = approval
        return approval

    def record(self, requirement_id: str, professional: Professional,
              document_ref: str = "") -> ProfessionalApproval:
        approval = self.approvals.get(requirement_id)
        if approval is None:
            raise KeyError(f"no approval was required for {requirement_id!r}")
        if approval.required_license and professional.role != approval.required_license:
            approval.approval_status = ProfessionalApprovalStatus.REJECTED
            approval.notes = (f"{professional.name} holds role {professional.role!r}, "
                              f"not the required {approval.required_license!r}")
        elif approval.required_signature and not professional.license_valid:
            approval.approval_status = ProfessionalApprovalStatus.REJECTED
            approval.notes = f"{professional.name}'s license is not valid"
        else:
            approval.approval_status = ProfessionalApprovalStatus.PRESENT
            approval.document_ref = document_ref
        return approval

    def outstanding(self) -> list[ProfessionalApproval]:
        return [approval for approval in self.approvals.values() if not approval.satisfied]
