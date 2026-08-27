"""Permit lifecycle intelligence (Petah Tikva spec §2, §18, §23, §24).

A municipal record is a chronological workflow, not a flat list of comments:
requirements get repeated across review rounds, sharpened, superseded, or
resolved, and old rows marked complete must never be read as describing the
current state. This package reconstructs the latest active requirement set
from a sequence of review rounds.
"""

from .requirements import LifecycleState, LifecycleTracker, RequirementLifecycle
from .stages import PermitStage
from .supersession import CommentEvolution, evolve, similarity

__all__ = [
    "CommentEvolution", "LifecycleState", "LifecycleTracker", "PermitStage",
    "RequirementLifecycle", "evolve", "similarity",
]
