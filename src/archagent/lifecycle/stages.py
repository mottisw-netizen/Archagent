"""Permit stages (Petah Tikva spec §18): construction stage vs permit stage.

Every requirement is due at a stage, blocks a stage, or has its evidence due
by a stage - a post-construction acoustic measurement and its design-time
acoustic report are the same discipline but very different due dates. Mixing
them up produces exactly the two failure modes the spec warns against:
demanding evidence too early, or declaring the permit complete too early.
"""

from __future__ import annotations

import enum


class PermitStage(str, enum.Enum):
    PRE_APPLICATION = "pre_application"
    DESIGN_REVIEW = "design_review"
    COMMITTEE = "committee"
    DESIGN_CONTROL = "design_control"
    PERMIT_ISSUANCE = "permit_issuance"
    START_OF_WORK = "start_of_work"
    CONSTRUCTION = "construction"
    COMPLETION = "completion"
    FORM_4 = "form_4"

    @property
    def rank(self) -> int:
        return STAGE_ORDER.index(self)

    def before(self, other: "PermitStage") -> bool:
        return self.rank < other.rank

    def after(self, other: "PermitStage") -> bool:
        return self.rank > other.rank

    def at_or_after(self, other: "PermitStage") -> bool:
        return self.rank >= other.rank


STAGE_ORDER = [
    PermitStage.PRE_APPLICATION,
    PermitStage.DESIGN_REVIEW,
    PermitStage.COMMITTEE,
    PermitStage.DESIGN_CONTROL,
    PermitStage.PERMIT_ISSUANCE,
    PermitStage.START_OF_WORK,
    PermitStage.CONSTRUCTION,
    PermitStage.COMPLETION,
    PermitStage.FORM_4,
]
