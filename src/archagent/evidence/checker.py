"""The professional/document completeness checker (spec §28).

Answers the nine questions of §28 from whatever :class:`~.model.Evidence` the
project actually supplied - never by assuming a document exists, is signed,
or is approved because a requirement says it must be. A requirement with no
matching evidence comes back ``MISSING``, not "probably fine".
"""

from __future__ import annotations

from .model import Evidence, EvidenceCheckResult, EvidenceStatus


class PermitEvidenceChecker:
    def __init__(self, evidence_index: list[Evidence] | None = None):
        self.evidence_index = list(evidence_index or [])

    def add(self, evidence: Evidence) -> None:
        self.evidence_index.append(evidence)

    def for_type(self, evidence_type: str) -> list[Evidence]:
        return [item for item in self.evidence_index if item.type == evidence_type]

    # ------------------------------------------------------------------
    def check(self, evidence_type: str, *, project_id: str = "", expected_role: str = "",
              affected_element: str = "", expected_revision: str = "",
              require_signature: bool = False,
              require_authority_approval: bool = False) -> EvidenceCheckResult:
        candidates = self.for_type(evidence_type)
        if not candidates:
            return EvidenceCheckResult(
                evidence_type=evidence_type, status=EvidenceStatus.MISSING, present=False,
                notes=[f"no evidence of type {evidence_type!r} was supplied for this project"])

        # The most recent by date, when dated; otherwise the first supplied -
        # never a merge across candidates, which would fabricate one document
        # out of several real ones.
        evidence = sorted(candidates, key=lambda item: item.date or "", reverse=True)[0]

        correct_revision = not expected_revision or evidence.revision == expected_revision
        role_correct = not expected_role or evidence.professional_role == expected_role
        refers_to_project = not project_id or evidence.project_id == project_id
        covers_element = not affected_element or affected_element in evidence.covered_elements
        current = evidence.current_revision
        authority_approval_present = evidence.approval_status == "approved"

        notes = []
        if not correct_revision:
            notes.append(f"revision {evidence.revision!r} does not match the "
                         f"expected {expected_revision!r}")
        if not role_correct:
            notes.append(f"prepared by {evidence.professional_role!r}, "
                         f"expected {expected_role!r}")
        if not refers_to_project:
            notes.append("the document does not identify this project")
        if not covers_element:
            notes.append(f"the document's covered scope does not name {affected_element!r}")
        if not current:
            notes.append("the document is not the current revision")
        if require_signature and not evidence.signed:
            notes.append("the document is not signed")
        if require_authority_approval and not authority_approval_present:
            notes.append(f"authority approval status is {evidence.approval_status!r}, "
                         "not approved")

        required_checks = [correct_revision, role_correct, refers_to_project,
                           covers_element, current]
        if require_signature:
            required_checks.append(evidence.signed)
        if require_authority_approval:
            required_checks.append(authority_approval_present)

        status = EvidenceStatus.SATISFIED if all(required_checks) else EvidenceStatus.INCOMPLETE
        return EvidenceCheckResult(
            evidence_type=evidence_type, status=status, present=True,
            correct_revision=correct_revision, signed=evidence.signed,
            professional_role_correct=role_correct, current=current,
            refers_to_project=refers_to_project, covers_element=covers_element,
            authority_approval_present=authority_approval_present,
            evidence_id=evidence.evidence_id, notes=notes)
