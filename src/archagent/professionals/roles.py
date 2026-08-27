"""Professional roles and ownership (spec §8, §28, §42).

A geometric correction can be perfectly measurable and still not be the
agent's to finish: the record is explicit that a traffic-engineer-prepared
plan is a different thing from an AI-generated geometric proposal (§8).
:class:`Professional` names who is actually responsible; the well-known role
names below are the ones the Petah Tikva evidence-requirements profile uses,
kept here as constants so the whole codebase spells them the same way.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Well-known professional roles referenced by the Petah Tikva authority
#: profile's evidence_requirements.yaml - not an exhaustive or authoritative
#: list of licensed professions, just the ones this codebase needs a name for.
TRAFFIC_ENGINEER = "traffic_engineer"
HYDROLOGIST = "hydrologist"
ACOUSTIC_CONSULTANT = "acoustic_consultant"
STRUCTURAL_ENGINEER = "structural_engineer"
LANDSCAPE_ARCHITECT = "landscape_architect"
CERTIFIED_ASBESTOS_SURVEYOR = "certified_asbestos_surveyor"
ENVIRONMENTAL_CONSULTANT = "environmental_consultant"
RADIATION_CONSULTANT = "radiation_consultant"

KNOWN_ROLES = (
    TRAFFIC_ENGINEER, HYDROLOGIST, ACOUSTIC_CONSULTANT, STRUCTURAL_ENGINEER,
    LANDSCAPE_ARCHITECT, CERTIFIED_ASBESTOS_SURVEYOR, ENVIRONMENTAL_CONSULTANT,
    RADIATION_CONSULTANT,
)


@dataclass
class Professional:
    """One named professional and their standing - never assumed valid."""

    name: str
    role: str
    license_number: str = ""
    license_valid: bool = False
