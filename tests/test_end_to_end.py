import json
from pathlib import Path

from archagent.cli import main
from archagent.consult import ScriptedResponder
from archagent.models import CommentStatus, sha256_file
from archagent.orchestrator import Orchestrator


def _run(project, mode="consultation", answers=None, **kwargs):
    responder = ScriptedResponder(answers) if answers is not None else None
    return Orchestrator(project, mode=mode, responder=responder, **kwargs).run()


def test_consultation_run_applies_the_approved_changes(project):
    result = _run(project, answers={"C-005": "approve"})
    statuses = {item.comment_id: item.status for item in result.validation.comments}
    assert statuses["C-001"] is CommentStatus.RESOLVED          # P12 widened
    assert statuses["C-004"] is CommentStatus.RESOLVED          # already compliant
    assert statuses["C-005"] is CommentStatus.RESOLVED          # setback, after approval
    assert statuses["C-003"] is CommentStatus.REQUIRES_HUMAN_REVIEW  # ambiguous
    assert statuses["C-008"] is CommentStatus.NOT_APPLICABLE    # "Noted."
    assert result.changes and result.version == "v2"


def test_every_change_traces_to_a_comment_and_a_plan(project):
    result = _run(project, answers={"C-005": "approve"})
    assert all(change.comment_id and change.plan_id for change in result.changes)


def test_the_original_source_file_is_never_touched(project):
    source = project / "source" / "project.json"
    before = sha256_file(source)
    _run(project, answers={"C-005": "approve"})
    assert sha256_file(source) == before
    assert (project / "versions" / "project_original.json").exists()


def test_versions_are_written_with_manifest_and_audit_log(project):
    result = _run(project, answers={"C-005": "approve"})
    version_dir = project / "versions" / result.version
    manifest = json.loads((version_dir / "version.json").read_text())
    assert manifest["parent_version"] == "v1"
    assert manifest["validation_result"] == result.validation.result
    assert manifest["changes"] and (version_dir / "audit.jsonl").exists()
    assert (version_dir / f"project_{result.version}.json").exists()


def test_unanswered_consultation_defers_instead_of_applying(project):
    result = _run(project, answers={})
    statuses = {item.comment_id: item.status for item in result.validation.comments}
    assert statuses["C-005"] is not CommentStatus.RESOLVED
    refs = [item["ref"] for item in result.context.open_items]
    assert "C-005" in refs


def test_autonomous_mode_refuses_a_footprint_change(project):
    result = _run(project, mode="autonomous")
    reasons = {item["ref"]: item["why"] for item in result.context.open_items}
    assert "footprint" in reasons["C-005"]
    # ... and the run is honest about being incomplete
    assert result.validation.result == "failed"
    assert not result.complete


def test_autonomous_mode_still_applies_the_safe_corrections(project):
    result = _run(project, mode="autonomous")
    statuses = {item.comment_id: item.status for item in result.validation.comments}
    assert statuses["C-001"] is CommentStatus.RESOLVED


def test_artefacts_are_generated(project):
    result = _run(project, answers={"C-005": "approve"})
    for name in ("comparison", "change_map", "highlighted", "validation_report",
                 "dependency_graph", "correction_report", "project_context",
                 "before_model", "after_model"):
        assert Path(result.files[name]).exists(), name
    change_map = json.loads(Path(result.files["change_map"]).read_text())
    assert any(entry["comments"] for entry in change_map["entries"])
    html = Path(result.files["comparison"]).read_text()
    assert "slider" in html and "parking_p12" in html


def test_before_and_after_models_are_the_raw_data_a_viewer_draws_from(project):
    """Not a picture of the model - the model, for a client that wants to
    pan/zoom/click rather than look at a fixed SVG."""
    result = _run(project, answers={"C-005": "approve"})
    before = json.loads(Path(result.files["before_model"]).read_text())
    after = json.loads(Path(result.files["after_model"]).read_text())
    before_p12 = next(e for e in before["elements"] if e["id"] == "parking_p12")
    after_p12 = next(e for e in after["elements"] if e["id"] == "parking_p12")
    assert before_p12["geometry"]["w"] == 2.4
    assert after_p12["geometry"]["w"] == 2.5
    svg = Path(result.files["highlighted"]).read_text()
    assert svg.startswith("<svg") and "C-001" in svg  # colour plus a text tag


def test_report_names_open_items_and_carries_the_sign_off(project):
    result = _run(project, answers={"C-005": "approve"})
    report = Path(result.files["correction_report"]).read_text()
    assert "## Open items" in report and "## Definition of done" in report
    assert "licensed professional" in report
    assert "| C-006 |" in report


def test_markup_only_run_without_an_editable_model(tmp_path):
    project = tmp_path / "pdf_only"
    (project / "municipal_comments").mkdir(parents=True)
    (project / "municipal_comments" / "comments.md").write_text(
        "Department: Traffic\n\nC-001: Increase parking space P12 width to 2.50 m.\n",
        encoding="utf-8")
    result = Orchestrator(project).run()
    assert result.context.execution_mode == "markup_only"
    assert result.changes == []
    report = Path(result.files["correction_report"]).read_text()
    assert "Markup only" in report


def test_run_is_resumable_from_the_persisted_context(project):
    result = _run(project, answers={"C-005": "approve"})
    context = json.loads(Path(result.files["project_context"]).read_text())
    assert context["run_id"] == result.context.run_id
    assert len(context["municipal_comments"]) == 8
    assert context["municipal_comments"][0]["confidence"]["band"]


def test_a_second_run_builds_on_the_previous_version(project):
    first = _run(project, answers={"C-005": "approve"})
    second = _run(project, answers={})
    assert second.parent_version == first.version
    assert second.version == "v3"


def test_cli_run_and_comments_and_validate(project, answers_file, capsys):
    assert main(["comments", str(project)]) == 0
    assert "C-001" in capsys.readouterr().out

    exit_code = main(["run", str(project), "--answers", str(answers_file)])
    assert exit_code == 0
    assert "validation" in capsys.readouterr().out

    model = project / "versions" / "v2" / "project_v2.json"
    constraints = project / "constraints" / "zoning_plan.md"
    assert main(["validate", str(model), str(constraints)]) == 0
    output = capsys.readouterr().out
    assert "ok" in output and "setback" in output


def test_cli_validate_reports_failures_with_a_non_zero_exit(project, capsys):
    model = project / "source" / "project.json"
    constraints = project / "constraints" / "zoning_plan.md"
    assert main(["validate", str(model), str(constraints)]) == 1
    assert "FAIL" in capsys.readouterr().out
