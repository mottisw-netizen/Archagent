import json

import pytest

from archagent.comments import CommentAnalyzer
from archagent.constraints import (
    ConstraintLedger,
    constraints_from_comments,
    constraints_from_document,
    derive_implicit_constraints,
)
from archagent.consult import ConsultationAgent, ScriptedResponder, apply_decision
from archagent.execute import ExecutionAgent, check_preconditions
from archagent.mapping import ElementMapper
from archagent.models import (
    Action,
    CommentStatus,
    CorrectionPlan,
    Precondition,
    VersionManifest,
)
from archagent.planner import Planner
from archagent.simulate import baseline_status, simulate
from archagent.validate import ValidationAgent
from archagent.versioning import VersionError, VersionStore, verify_original


@pytest.fixture
def setup(driver):
    analyzer = CommentAnalyzer()
    ledger = ConstraintLedger()
    constraints_from_document(
        "- Northern setback must be at least 3.0 m [critical]\n"
        "- Southern setback must be at least 4.0 m [critical]\n"
        "- Total floor area must not exceed 1850 m2 [critical]\n",
        "Zoning Plan", "zoning.md", ledger)
    return driver, analyzer, ledger


def _plan_for(driver, analyzer, ledger, text, comment_id="C-001"):
    comment = analyzer.analyze_comment(comment_id, text, "Traffic")
    constraints_from_comments([comment], ledger)
    derive_implicit_constraints(driver, ledger)
    mapping = ElementMapper(driver).map_comment(comment)
    planner = Planner(driver, ledger, baseline_status(driver, ledger))
    return comment, mapping, planner.plan_for(comment, mapping)


def test_planner_avoids_the_anchor_that_creates_an_overlap(setup):
    driver, analyzer, ledger = setup
    _c, _m, proposal = _plan_for(driver, analyzer, ledger,
                                 "Increase parking space P12 width to 2.50 m.")
    assert proposal.plan is not None
    # P13 touches P12 on the east, so the east edge is the one that must stay put.
    assert proposal.plan.plan[0].anchor == "north_east"
    assert proposal.simulation.safe


def test_planner_adds_the_dependent_dimension_and_schedule_updates(setup):
    driver, analyzer, ledger = setup
    _c, _m, proposal = _plan_for(driver, analyzer, ledger,
                                 "Increase parking space P12 width to 2.50 m.")
    actions = {action.action for action in proposal.plan.plan}
    assert {"resize", "update_dimension", "update_schedule"} <= actions


def test_planner_reports_an_already_compliant_comment_without_changing_anything(setup):
    driver, analyzer, ledger = setup
    _c, _m, proposal = _plan_for(driver, analyzer, ledger,
                                 "The drive aisle clear width shall be no less than 5.50 m.")
    assert proposal.plan.status == "already_compliant"
    assert proposal.plan.plan == []


def test_planner_escalates_a_program_change_with_a_proposal(setup):
    driver, analyzer, ledger = setup
    _c, _m, proposal = _plan_for(driver, analyzer, ledger, "Provide at least 34 parking spaces.")
    assert proposal.plan is None
    assert "design decision" in " ".join(proposal.reasons)
    assert "currently measures" in proposal.proposal_text


def test_planner_refuses_an_ambiguous_comment(setup):
    driver, analyzer, ledger = setup
    _c, _m, proposal = _plan_for(driver, analyzer, ledger,
                                 "Increase the parking space width to 2.50 m.")
    assert proposal.plan is None
    assert "discriminator" in " ".join(proposal.reasons)


def test_footprint_changes_trigger_consultation(setup):
    driver, analyzer, ledger = setup
    _c, _m, proposal = _plan_for(driver, analyzer, ledger,
                                 "The northern setback must be at least 3.0 m.", "C-005")
    assert proposal.plan.requires_consultation
    assert any("footprint" in reason for reason in proposal.plan.consultation_reasons)


def test_alternatives_are_offered_and_already_simulated(setup):
    driver, analyzer, ledger = setup
    _c, _m, proposal = _plan_for(driver, analyzer, ledger,
                                 "The northern setback must be at least 3.0 m.", "C-005")
    assert proposal.plan.alternatives
    assert all(result.safe for _plan, result in proposal.alternative_plans)


def test_a_pre_existing_failure_is_not_blamed_on_the_plan(setup):
    driver, analyzer, ledger = setup
    # The northern setback already fails; a parking correction must not inherit it.
    _c, _m, proposal = _plan_for(driver, analyzer, ledger,
                                 "Increase parking space P12 width to 2.50 m.")
    assert proposal.simulation.pre_existing_violations
    assert proposal.simulation.safe


def test_simulation_flags_a_new_overlap(setup):
    driver, analyzer, ledger = setup
    plan = CorrectionPlan(plan_id="PLAN-X", comment_ids=["C-X"],
                          plan=[Action(action="resize", element="parking_p12",
                                       parameter="width", to_value=3.0, anchor="south_west")])
    result = simulate(driver, plan, ledger, baseline_status(driver, ledger))
    assert result.spatial_conflicts and not result.safe


def test_simulation_never_touches_the_real_model(setup):
    driver, analyzer, ledger = setup
    plan = CorrectionPlan(plan_id="PLAN-X", comment_ids=["C-X"],
                          plan=[Action(action="resize", element="parking_p12",
                                       parameter="width", to_value=3.0)])
    simulate(driver, plan, ledger)
    assert driver.measure({"element_id": "parking_p12"}, "width").value == 2.4


def test_simulation_detects_a_regression(setup):
    driver, analyzer, ledger = setup
    baseline = baseline_status(driver, ledger)
    plan = CorrectionPlan(plan_id="PLAN-Y", comment_ids=["C-Y"],
                          plan=[Action(action="move", element="building",
                                       distance=17.0, direction="south")])
    result = simulate(driver, plan, ledger, baseline)
    # the southern setback passed before the move and fails after it
    assert [r["constraint_id"] for r in result.regressions]
    assert not result.safe


def test_execution_aborts_on_a_failed_precondition(driver):
    plan = CorrectionPlan(plan_id="PLAN-P", comment_ids=["C-1"],
                          preconditions=[Precondition("parking_p12", "width", 9.9)],
                          plan=[Action(action="resize", element="parking_p12",
                                       parameter="width", to_value=2.5)])
    assert check_preconditions(driver, plan)
    result = ExecutionAgent(driver).execute(plan)
    assert not result.ok and driver.measure({"element_id": "parking_p12"}, "width").value == 2.4


def test_a_failing_action_rolls_the_whole_plan_back(driver):
    plan = CorrectionPlan(plan_id="PLAN-R", comment_ids=["C-1"], plan=[
        Action(action="resize", element="parking_p12", parameter="width", to_value=2.5),
        Action(action="resize", element="ghost", parameter="width", to_value=2.5),
    ])
    result = ExecutionAgent(driver).execute(plan)
    assert not result.ok and result.rolled_back
    assert driver.measure({"element_id": "parking_p12"}, "width").value == 2.4


def test_execution_writes_an_audit_trail(driver, tmp_path):
    from archagent.audit import AuditLog
    audit = AuditLog(tmp_path / "audit.jsonl")
    plan = CorrectionPlan(plan_id="PLAN-A", comment_ids=["C-1"],
                          plan=[Action(action="resize", element="parking_p12",
                                       parameter="width", to_value=2.5)])
    ExecutionAgent(driver, audit).execute(plan)
    lines = [json.loads(line) for line in (tmp_path / "audit.jsonl").read_text().splitlines()]
    assert lines[0]["event"] == "api_call" and lines[0]["after"] == 2.5


def test_validation_requires_evidence_for_resolved(driver, setup):
    _driver, analyzer, ledger = setup
    comment = analyzer.analyze_comment("C-001", "Increase parking space P12 width to 2.50 m.")
    constraints_from_comments([comment], ledger)
    agent = ValidationAgent(driver, ledger)
    item = agent.validate_comment(comment, was_applied=False)
    assert item.status is CommentStatus.NOT_RESOLVED
    with driver.authorised("PLAN-1"):
        driver.resize_element("parking_p12", "width", 2.5, anchor="north_east")
    item = agent.validate_comment(comment, was_applied=True)
    assert item.status is CommentStatus.RESOLVED and item.evidence["measured"] == 2.5


def test_unmeasurable_demands_are_never_marked_resolved(driver, setup):
    _driver, analyzer, ledger = setup
    comment = analyzer.analyze_comment("C-002", "Update the parking schedule accordingly.")
    item = ValidationAgent(driver, ledger).validate_comment(comment, was_applied=True)
    assert item.status is CommentStatus.ADDRESSED_NEEDS_CONFIRMATION


def test_validation_fails_on_a_regression(driver, setup):
    _driver, analyzer, ledger = setup
    baseline = {result.constraint_id: "pass" for result in ledger.evaluate(driver)}
    with driver.authorised("PLAN-1"):
        driver.move_element("building", 17.0, "south")
    result = ValidationAgent(driver, ledger, baseline).validate("v2", [])
    assert result.result == "failed" and result.regressions


def test_drawing_checks_catch_broken_references_and_overlaps(driver, setup):
    _driver, analyzer, ledger = setup
    with driver.authorised("PLAN-1"):
        driver.resize_element("parking_p12", "width", 3.0, anchor="south_west")
    checks = {check["check"]: check for check in ValidationAgent(driver, ledger).drawing_checks()}
    assert checks["spatial_conflicts"]["status"] == "fail"


def test_consultation_records_the_decision_and_the_transcript(setup):
    driver, analyzer, ledger = setup
    comment, mapping, proposal = _plan_for(
        driver, analyzer, ledger, "The northern setback must be at least 3.0 m.", "C-005")
    agent = ConsultationAgent(ScriptedResponder({"C-005": "alternative:B"}))
    decision = agent.consult(comment, proposal.plan, mapping, proposal.simulation)
    outcome, _plan = apply_decision(decision, proposal.plan)
    assert outcome == "alternative"
    assert agent.transcript and "The municipal comment" in agent.transcript[0]["question"]


def test_unscripted_comments_are_deferred_never_auto_approved(setup):
    driver, analyzer, ledger = setup
    comment, mapping, proposal = _plan_for(
        driver, analyzer, ledger, "The northern setback must be at least 3.0 m.", "C-005")
    agent = ConsultationAgent(ScriptedResponder({}))
    decision = agent.consult(comment, proposal.plan, mapping, proposal.simulation)
    assert apply_decision(decision, proposal.plan)[0] == "question"


def test_versions_are_immutable(driver, tmp_path):
    store = VersionStore(tmp_path / "versions")
    manifest = VersionManifest(version="v1", parent_version="original")
    record = store.create(driver, manifest)
    assert record.model_path.exists()
    with pytest.raises(VersionError):
        store.create(driver, VersionManifest(version="v1", parent_version="original"))


def test_version_numbering_and_manifest_round_trip(driver, tmp_path):
    store = VersionStore(tmp_path / "versions")
    store.create(driver, VersionManifest(version=store.next_version(), parent_version="original"))
    assert store.next_version() == "v2"
    store.create(driver, VersionManifest(version="v2", parent_version="v1"))
    assert store.load_manifest("v2").parent_version == "v1"
    assert store.rollback_to("v1").exists()


def test_original_checksum_verification(project):
    from archagent.models import sha256_file
    source = project / "source" / "project.json"
    digest = sha256_file(source)
    assert verify_original(source, digest)
    source.write_text(source.read_text() + "\n", encoding="utf-8")
    assert not verify_original(source, digest)
