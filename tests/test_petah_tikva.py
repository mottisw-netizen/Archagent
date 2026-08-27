"""Petah Tikva regression corpus (spec §40) and end-to-end fixture (spec §52).

The corpus files live in ``tests/fixtures/petah_tikva/`` and are read here
rather than hand-duplicated into this file, so the fixture data stays the
single source of truth for what a correct reading of each comment is.
"""

from __future__ import annotations

import json
from pathlib import Path

from archagent.comments import CommentAnalyzer
from archagent.consult import ScriptedResponder
from archagent.evidence import PermitEvidenceChecker
from archagent.lifecycle import LifecycleTracker
from archagent.models import CommentStatus
from archagent.orchestrator import Orchestrator

FIXTURES = Path(__file__).parent / "fixtures" / "petah_tikva"


def _read_jsonl(name: str) -> list[dict]:
    path = FIXTURES / name
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _analyzed_comments() -> dict[str, object]:
    analyzer = CommentAnalyzer()
    comments = {}
    for row in _read_jsonl("comments_he.jsonl"):
        comments[row["comment_id"]] = analyzer.analyze_comment(
            row["comment_id"], row["text"], department=row["department"])
    return comments


# ----------------------------------------------------------------------
# requirement-type classification corpus
# ----------------------------------------------------------------------
def test_requirement_type_classification_matches_expected():
    comments = _analyzed_comments()
    for expected in _read_jsonl("requirements_expected.jsonl"):
        comment = comments[expected["comment_id"]]
        actual_type = comment.requirement_type.value if comment.requirement_type else None
        assert actual_type == expected["requirement_type"], expected["comment_id"]
        assert (comment.requirement is not None) == expected["has_requirement"], expected["comment_id"]
        assert comment.required_action == expected["required_action"], expected["comment_id"]


# ----------------------------------------------------------------------
# discipline routing corpus
# ----------------------------------------------------------------------
def test_discipline_routing_matches_expected():
    comments = _analyzed_comments()
    for expected in _read_jsonl("routing_expected.jsonl"):
        comment = comments[expected["comment_id"]]
        assert comment.affected_discipline == expected["discipline"], expected["comment_id"]


# ----------------------------------------------------------------------
# evidence corpus - checked against the bundled Petah Tikva authority profile
# ----------------------------------------------------------------------
def test_evidence_requirements_match_the_authority_profile():
    try:
        from archagent.authority import petah_tikva
        authority = petah_tikva.load()
    except ImportError:
        import pytest
        pytest.skip("PyYAML is not installed (archagent[authority])")
    for expected in _read_jsonl("evidence_expected.jsonl"):
        entry = authority.evidence_for(expected["evidence_type"])
        assert entry is not None, expected["evidence_type"]
        assert entry["required_stage"] == expected["required_stage"]
        assert entry["professional_role"] == expected["professional_role"]


def test_evidence_checker_never_fabricates_the_expected_documents():
    checker = PermitEvidenceChecker()
    for expected in _read_jsonl("evidence_expected.jsonl"):
        result = checker.check(expected["evidence_type"], project_id="P-1")
        assert result.present is False
        assert result.status.value == "missing"


# ----------------------------------------------------------------------
# lifecycle / supersession corpus (the review-round sequence of spec §23)
# ----------------------------------------------------------------------
def test_lifecycle_sequence_matches_expected_final_state():
    rows = _read_jsonl("lifecycle_expected.jsonl")
    rounds = [row for row in rows if "round" in row]
    expected = next(row["expected"] for row in rows if "expected" in row)

    analyzer = CommentAnalyzer()
    tracker = LifecycleTracker()
    active = []
    for round_data in sorted(rounds, key=lambda r: r["round"]):
        comments = [analyzer.analyze_comment(c["comment_id"], c["text"], department=c["department"])
                   for c in round_data["comments"]]
        active = tracker.ingest_round(comments, version=round_data["version"])

    assert len(tracker.requirements) == expected["total_requirements"]
    still_open = [r for r in active if r.is_open]
    assert len(still_open) == expected["still_open"]
    # At least one open lineage was carried all the way to the final round -
    # each lineage's own supersession chain is already proven end-to-end by
    # tests/test_lifecycle.py; here the corpus only checks the aggregate.
    assert expected["final_source_version"] in {r.source_version for r in still_open}


# ----------------------------------------------------------------------
# end-to-end fixture (spec §52's closing instruction)
# ----------------------------------------------------------------------
def test_petah_tikva_project_runs_end_to_end(project_petah_tikva):
    """Runs the full pipeline on a realistic Petah Tikva permit package.

    This exercises the existing deterministic pipeline (ingest, comment
    analysis incl. requirement-type classification, mapping, planning,
    simulation, validation, reporting) against multi-discipline Hebrew
    comments - not a live Revit/Civil 3D session, which this sandbox cannot
    provide. Geometry the JSON model actually contains (the P-1 parking
    width) is corrected and validated; document/approval/workflow-gate
    comments that need evidence this run was never given correctly surface
    as open items rather than being silently marked resolved.
    """
    result = Orchestrator(
        project_petah_tikva, mode="consultation",
        responder=ScriptedResponder({"C-001": "approve"}),
    ).run()

    assert result.report
    assert result.version

    statuses = {item.comment_id: item.status for item in result.validation.comments}
    assert statuses["C-001"] is CommentStatus.RESOLVED  # P-1 widened to 2.50 m

    # Document/approval-type comments must never be fabricated as resolved.
    for comment_id in ("C-007", "C-008", "C-010", "C-011", "C-013"):
        assert statuses[comment_id] is not CommentStatus.RESOLVED

    open_refs = {item["ref"] for item in result.context.open_items}
    assert "C-010" in open_refs  # hydrologic report - no evidence was supplied
    assert "C-008" in open_refs  # traffic department approval gate

    # Cross-discipline dependency: civil (drainage) comments constrain
    # architecture/traffic in the merged dependency graph (spec §14).
    node_kinds = {node["kind"] for node in result.graph["nodes"]}
    assert "discipline" in node_kinds
