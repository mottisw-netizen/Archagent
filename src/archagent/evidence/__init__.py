"""Evidence, professional approval, and stricter resolution semantics.

Petah Tikva spec §15, §21, §28, §38: a requirement can be satisfied by
geometry, by a document, by a professional's sign-off, or by more than one of
those at once - and it is only ``FULLY_RESOLVED`` when everything it actually
needs is in place.
"""

from .checker import PermitEvidenceChecker
from .graph import EvidenceGraph
from .model import (
    Evidence,
    EvidenceCheckResult,
    EvidenceStatus,
    ProfessionalApproval,
    ProfessionalApprovalStatus,
    ResolutionResult,
    ResolutionState,
    resolve,
)

__all__ = [
    "Evidence", "EvidenceCheckResult", "EvidenceGraph", "EvidenceStatus",
    "PermitEvidenceChecker", "ProfessionalApproval", "ProfessionalApprovalStatus",
    "ResolutionResult", "ResolutionState", "resolve",
]
