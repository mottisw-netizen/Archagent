"""Submission readiness gate (spec §24/§47)."""

from __future__ import annotations

from archagent.readiness import SubmissionReadiness, assess_submission_readiness


def test_ready_when_nothing_outstanding():
    result = assess_submission_readiness(validation_result="passed")
    assert result.state is SubmissionReadiness.READY_FOR_PROFESSIONAL_REVIEW
    assert result.describe() == "ready for professional review"


def test_parking_geometry_resolved_but_traffic_approval_pending_is_not_ready():
    """The spec's own worked example (§8/§38): geometry corrected, professional
    deliverable still required -> not ready, never silently marked done."""
    result = assess_submission_readiness(
        validation_result="passed_with_open_items",
        pending_professional_approvals=["traffic engineer approval (REQ-1)"])
    assert result.state is SubmissionReadiness.NOT_READY
    assert "traffic engineer approval" in result.describe()


def test_missing_evidence_and_open_gates_are_not_ready():
    result = assess_submission_readiness(
        missing_evidence=["hydrologic_report"], open_authority_gates=["traffic department"])
    assert result.state is SubmissionReadiness.NOT_READY
    assert "hydrologic_report" in result.describe()
    assert "traffic department" in result.describe()


def test_failed_validation_blocks_outright():
    result = assess_submission_readiness(validation_result="failed")
    assert result.state is SubmissionReadiness.BLOCKED


def test_dropped_active_requirement_blocks_even_with_passed_validation():
    result = assess_submission_readiness(
        validation_result="passed", dropped_active_requirements=["REQ-7"])
    assert result.state is SubmissionReadiness.BLOCKED
    assert "REQ-7" in result.describe()


def test_blocked_wins_over_not_ready_when_both_apply():
    result = assess_submission_readiness(
        validation_result="failed", missing_evidence=["acoustic_report"])
    assert result.state is SubmissionReadiness.BLOCKED
