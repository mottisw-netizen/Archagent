"""Stage-aware workflow enforcement (UPDATE_PERMIT_ENGINE.md §5/§18)."""

from __future__ import annotations

from archagent.lifecycle import (
    LifecycleState,
    PermitStage,
    RequirementLifecycle,
    WorkflowStatus,
    blocking_requirements,
    workflow_status,
    workflow_summary,
)


def _lifecycle(**kwargs) -> RequirementLifecycle:
    defaults = dict(requirement_id="REQ-1", department="Environment")
    defaults.update(kwargs)
    return RequirementLifecycle(**defaults)


def test_not_yet_due_before_its_required_stage():
    acoustic_report = _lifecycle(required_stage=PermitStage.DESIGN_CONTROL)
    assert workflow_status(acoustic_report, PermitStage.COMMITTEE) is WorkflowStatus.NOT_YET_DUE


def test_due_once_required_stage_is_reached():
    acoustic_report = _lifecycle(required_stage=PermitStage.DESIGN_CONTROL)
    assert workflow_status(acoustic_report, PermitStage.DESIGN_CONTROL) is WorkflowStatus.DUE
    assert workflow_status(acoustic_report, PermitStage.PERMIT_ISSUANCE) is WorkflowStatus.DUE


def test_post_construction_measurement_is_not_yet_due_at_design_control():
    post_construction = _lifecycle(required_stage=PermitStage.COMPLETION)
    assert workflow_status(post_construction, PermitStage.DESIGN_CONTROL) is WorkflowStatus.NOT_YET_DUE
    assert workflow_status(post_construction, PermitStage.COMPLETION) is WorkflowStatus.DUE


def test_overdue_when_blocking_stage_has_passed():
    traffic_approval = _lifecycle(department="Traffic", blocking_stage=PermitStage.PERMIT_ISSUANCE)
    assert workflow_status(traffic_approval, PermitStage.DESIGN_CONTROL) is WorkflowStatus.NOT_APPLICABLE
    assert workflow_status(traffic_approval, PermitStage.PERMIT_ISSUANCE) is WorkflowStatus.OVERDUE


def test_settled_requirement_is_never_workflow_relevant_again():
    resolved = _lifecycle(required_stage=PermitStage.DESIGN_CONTROL, status=LifecycleState.RESOLVED)
    assert workflow_status(resolved, PermitStage.FORM_4) is WorkflowStatus.NOT_APPLICABLE


def test_workflow_summary_groups_and_blocking_requirements_lists_only_overdue():
    reqs = [
        _lifecycle(requirement_id="REQ-1", required_stage=PermitStage.COMPLETION),
        _lifecycle(requirement_id="REQ-2", blocking_stage=PermitStage.DESIGN_CONTROL),
        _lifecycle(requirement_id="REQ-3", status=LifecycleState.RESOLVED),
    ]
    summary = workflow_summary(reqs, PermitStage.DESIGN_CONTROL)
    assert summary[WorkflowStatus.NOT_YET_DUE] == ["REQ-1"]
    assert summary[WorkflowStatus.OVERDUE] == ["REQ-2"]
    assert summary[WorkflowStatus.NOT_APPLICABLE] == ["REQ-3"]

    overdue = blocking_requirements(reqs, PermitStage.DESIGN_CONTROL)
    assert [r.requirement_id for r in overdue] == ["REQ-2"]
