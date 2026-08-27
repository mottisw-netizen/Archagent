"""Permit lifecycle / supersession engine (Petah Tikva spec §2, §18, §23)."""

from __future__ import annotations

from archagent.comments import CommentAnalyzer
from archagent.lifecycle import LifecycleState, LifecycleTracker, PermitStage
from archagent.lifecycle.supersession import evolve, similarity


def _comment(comment_id: str, text: str, department: str = "Drainage"):
    return CommentAnalyzer().analyze_comment(comment_id, text, department=department)


# ----------------------------------------------------------------------
# stages
# ----------------------------------------------------------------------
def test_stage_ordering():
    assert PermitStage.DESIGN_CONTROL.before(PermitStage.COMPLETION)
    assert PermitStage.FORM_4.after(PermitStage.START_OF_WORK)
    assert PermitStage.COMPLETION.at_or_after(PermitStage.COMPLETION)


# ----------------------------------------------------------------------
# similarity / evolution
# ----------------------------------------------------------------------
def test_similarity_same_topic_scores_high():
    a = _comment("C-1", "יש לתקן את מערכת הניקוז באזור החניה")
    b = _comment("C-2", "יש לספק מידות לשוחת ההשהיה של מערכת הניקוז")
    assert similarity(a, b) > 0.2


def test_evolve_matches_by_department_and_text():
    previous = [_comment("C-1", "יש לתקן את מערכת הניקוז", department="Drainage")]
    current = [_comment("C-2", "יש לתקן את מערכת הניקוז באזור החניה", department="Drainage"),
               _comment("C-3", "יש לצרף דוח אקוסטי", department="Environment")]
    evolutions = evolve(previous, current)
    by_later = {e.later_comment: e for e in evolutions}
    assert by_later["C-2"].same_requirement
    assert by_later["C-2"].original_comment == "C-1"
    assert not by_later["C-3"].same_requirement
    assert by_later["C-3"].new_requirement


# ----------------------------------------------------------------------
# the review-round sequence of spec §23
# ----------------------------------------------------------------------
def test_review_round_sequence_is_one_requirement_not_four():
    tracker = LifecycleTracker()
    round1 = [_comment("C-101", "יש לתקן את מערכת הניקוז באזור החניה")]
    tracker.ingest_round(round1, version="v1")
    assert len(tracker.requirements) == 1

    round2 = [_comment("C-201", "יש לספק מידות לשוחת ההשהיה של מערכת הניקוז")]
    tracker.ingest_round(round2, version="v2")
    assert len(tracker.requirements) == 2

    round3 = [_comment("C-301", "יש להראות את שוחת ההשהיה של מערכת הניקוז בתכנית הפיתוח")]
    tracker.ingest_round(round3, version="v3")

    round4 = [_comment("C-401",
                       "יש להסיר את תעלת הניקוז ולהשתמש בשיפוע של לפחות 1% במערכת הניקוז")]
    active = tracker.ingest_round(round4, version="v4")

    # Four rounds, one lineage: exactly one requirement is still open.
    still_open = [r for r in active if r.is_open]
    assert len(still_open) == 1
    latest = still_open[0]
    assert latest.source_version == "v4"

    # The chain traces back three supersessions to the first round.
    chain = [latest]
    while chain[-1].supersedes:
        parent_id = chain[-1].supersedes[0]
        chain.append(tracker.requirements[parent_id])
    assert len(chain) == 4
    assert all(r.status == LifecycleState.SUPERSEDED for r in chain[1:])


def test_unrelated_department_never_reopens_a_resolved_requirement():
    tracker = LifecycleTracker()
    round1 = [_comment("C-1", "יש לתקן את מערכת הניקוז", department="Drainage")]
    tracker.ingest_round(round1, version="v1")
    [requirement_id] = list(tracker.requirements)
    tracker.resolve(requirement_id)
    assert tracker.requirements[requirement_id].status == LifecycleState.RESOLVED

    round2 = [_comment("C-2", "יש לצרף דוח אקוסטי", department="Environment")]
    tracker.ingest_round(round2, version="v2")

    # An unrelated later round must never flip a resolved requirement back open.
    assert tracker.requirements[requirement_id].status == LifecycleState.RESOLVED
    assert requirement_id not in {r.requirement_id for r in tracker.active()}


def test_default_state_by_requirement_type():
    tracker = LifecycleTracker()
    approval = _comment("C-1", "נדרש אישור אגף התנועה טרם בדיקת התכנית באגף", department="Traffic")
    document = _comment("C-2", "יש לצרף דוח הידרולוג", department="Drainage")
    tracker.ingest_round([approval, document], version="v1")
    states = {r.department: r.status for r in tracker.requirements.values()}
    assert states["Traffic"] == LifecycleState.PENDING_AUTHORITY
    assert states["Drainage"] == LifecycleState.PENDING_EVIDENCE
