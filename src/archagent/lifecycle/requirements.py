"""Permit requirement lifecycle (Petah Tikva spec §2).

The municipality record is not a flat list of comments: it is a chronological
workflow containing initial requirements, repeated reviews, superseded
comments, approvals, and conditions for later stages. This module tracks one
:class:`RequirementLifecycle` per distinct requirement across review rounds
and reconstructs the *current* active state - it never infers that an old
``הושלם`` (completed) row still describes the latest round.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field

from ..models import MunicipalComment, RequirementType, Serialisable, new_id, now
from .stages import PermitStage
from .supersession import evolve


class LifecycleState(str, enum.Enum):
    ACTIVE = "active"
    RESOLVED = "resolved"
    SUPERSEDED = "superseded"
    WAIVED = "waived"
    NOT_APPLICABLE = "not_applicable"
    PENDING_EVIDENCE = "pending_evidence"
    PENDING_AUTHORITY = "pending_authority"
    BLOCKED = "blocked"
    REQUIRES_HUMAN_REVIEW = "requires_human_review"


#: A requirement in one of these states still needs attention; everything
#: else (RESOLVED, SUPERSEDED, WAIVED, NOT_APPLICABLE) is settled.
OPEN_STATES = (
    LifecycleState.ACTIVE, LifecycleState.PENDING_EVIDENCE,
    LifecycleState.PENDING_AUTHORITY, LifecycleState.BLOCKED,
    LifecycleState.REQUIRES_HUMAN_REVIEW,
)

#: A later-round match this close to the original text is the same comment
#: carried forward unchanged, not a sharper restatement of it.
RECURRENCE_THRESHOLD = 0.85

#: Requirement types whose default state is "waiting on something other than
#: geometry" rather than plain ACTIVE - the type itself already says so.
_DEFAULT_STATE_BY_TYPE = {
    RequirementType.DOCUMENT: LifecycleState.PENDING_EVIDENCE,
    RequirementType.EVIDENCE: LifecycleState.PENDING_EVIDENCE,
    RequirementType.INSPECTION: LifecycleState.PENDING_EVIDENCE,
    RequirementType.APPROVAL: LifecycleState.PENDING_AUTHORITY,
    RequirementType.WORKFLOW_GATE: LifecycleState.PENDING_AUTHORITY,
    RequirementType.COMPLETION_CONDITION: LifecycleState.PENDING_EVIDENCE,
}


@dataclass
class RequirementLifecycle(Serialisable):
    """SKILL.md extension - Petah Tikva spec §2."""

    requirement_id: str
    department: str
    sub_department: str = ""
    stage: PermitStage | None = None
    source_comment_id: str = ""
    first_seen_at: str = field(default_factory=now)
    last_seen_at: str = field(default_factory=now)
    source_version: str = ""
    status: LifecycleState = LifecycleState.ACTIVE
    supersedes: list[str] = field(default_factory=list)
    superseded_by: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    blocks: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    drawing_refs: list[str] = field(default_factory=list)
    responsible_party: str = ""
    required_action_type: str = ""
    resolution_state: str = ""
    required_stage: PermitStage | None = None
    blocking_stage: PermitStage | None = None
    evidence_due_stage: PermitStage | None = None

    @property
    def is_open(self) -> bool:
        return self.status in OPEN_STATES


def _initial_state(comment: MunicipalComment) -> LifecycleState:
    if comment.required_action == "none":
        return LifecycleState.NOT_APPLICABLE
    if comment.requirement_type is None and comment.requirement is None:
        return LifecycleState.REQUIRES_HUMAN_REVIEW
    return _DEFAULT_STATE_BY_TYPE.get(comment.requirement_type, LifecycleState.ACTIVE)


class LifecycleTracker:
    """Ingests review rounds in chronological order; reports the latest state.

    Call :meth:`ingest_round` once per review round, oldest first - exactly
    the order the rounds were issued in the municipal record. Each call
    matches the new round against the previous one (:mod:`.supersession`),
    supersedes any requirement the new round sharpens or replaces, and adds a
    fresh :class:`RequirementLifecycle` for anything genuinely new.
    """

    def __init__(self) -> None:
        self.requirements: dict[str, RequirementLifecycle] = {}
        self._by_comment: dict[str, str] = {}  # comment_id -> requirement_id
        self._previous_round: list[MunicipalComment] = []

    # ------------------------------------------------------------------
    def ingest_round(self, comments: list[MunicipalComment], version: str = "") -> list[RequirementLifecycle]:
        evolutions = evolve(self._previous_round, comments) if self._previous_round else [
            None for _ in comments]  # first round: everything is new
        matched_by_later: dict[str, object] = {
            e.later_comment: e for e in evolutions if e is not None}

        for comment in comments:
            evolution = matched_by_later.get(comment.comment_id)
            if evolution is not None and evolution.same_requirement:
                self._supersede(evolution, comment, version)
            else:
                self._new_requirement(comment, version)

        self._previous_round = comments
        return list(self.requirements.values())

    # ------------------------------------------------------------------
    def _new_requirement(self, comment: MunicipalComment, version: str) -> RequirementLifecycle:
        lifecycle = RequirementLifecycle(
            requirement_id=new_id("REQ"),
            department=comment.department,
            source_comment_id=comment.comment_id,
            source_version=version,
            status=_initial_state(comment),
            required_action_type=comment.required_action,
        )
        self.requirements[lifecycle.requirement_id] = lifecycle
        self._by_comment[comment.comment_id] = lifecycle.requirement_id
        return lifecycle

    def _supersede(self, evolution, comment: MunicipalComment, version: str) -> RequirementLifecycle:
        old_id = self._by_comment.get(evolution.original_comment)
        old = self.requirements.get(old_id) if old_id else None
        if old is None:
            return self._new_requirement(comment, version)
        if evolution.similarity >= RECURRENCE_THRESHOLD:
            # Near-identical text carried forward unchanged (a still-open item
            # copied into the next round): update recency only, never re-derive
            # its status from wording alone.
            old.last_seen_at = now()
            old.source_version = version or old.source_version
            self._by_comment[comment.comment_id] = old.requirement_id
            return old
        old.status = LifecycleState.SUPERSEDED
        new_lifecycle = RequirementLifecycle(
            requirement_id=new_id("REQ"),
            department=comment.department,
            source_comment_id=comment.comment_id,
            source_version=version,
            status=_initial_state(comment),
            required_action_type=comment.required_action,
            supersedes=[old.requirement_id],
        )
        old.superseded_by.append(new_lifecycle.requirement_id)
        self.requirements[new_lifecycle.requirement_id] = new_lifecycle
        self._by_comment[comment.comment_id] = new_lifecycle.requirement_id
        return new_lifecycle

    # ------------------------------------------------------------------
    def active(self) -> list[RequirementLifecycle]:
        """The reconstructed current state: every requirement still open."""
        return [r for r in self.requirements.values() if r.is_open]

    def resolve(self, requirement_id: str) -> None:
        requirement = self.requirements.get(requirement_id)
        if requirement is not None:
            requirement.status = LifecycleState.RESOLVED
