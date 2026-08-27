"""External infrastructure requirements (spec §31).

The record names electricity, lighting, communication cabinets, utility
poles, power-line relocation/burial, telecom cabinets, NTA, RMI, the airport
authority, the Ministry of Defense - a long, open-ended list of external
asset owners. Rather than a bespoke class per utility, this is one generic
record: a new owner or asset type is new data, not a new class.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import Serialisable


@dataclass
class ExternalInfrastructureRequirement(Serialisable):
    requirement_id: str
    asset_type: str = ""   # e.g. power_line, telecom_cabinet, utility_pole, streetlight
    location: str = ""
    owner: str = ""        # e.g. Israel Electric Corporation, Bezeq, NTA, RMI
    action: str = ""       # e.g. relocate, bury, protect, connect, remove
    approval: str = ""     # the owner/authority's own approval status - never fabricated
    relocation: bool = False
    burial: bool = False
    payment: str = ""      # who bears the cost, or its payment status
    evidence: list[str] = field(default_factory=list)  # Evidence.evidence_id references


def needs_owner_approval(requirement: ExternalInfrastructureRequirement) -> bool:
    """A relocation or burial is never purely geometric - the asset's owner
    has to sign off on it, regardless of how confidently the geometry fits."""
    return requirement.relocation or requirement.burial
