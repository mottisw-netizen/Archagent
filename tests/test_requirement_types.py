"""Requirement-type classification (Petah Tikva spec §3) - deterministic path."""

from __future__ import annotations

from archagent.comments import CommentAnalyzer
from archagent.models import RequirementType


def _classify(text: str) -> RequirementType | None:
    comment = CommentAnalyzer().analyze_comment("C-001", text, department="Architecture")
    return comment.requirement_type


def test_geometric_examples():
    assert _classify("יש לתכנן שיפוע המדרכה לכיוון הכביש") is RequirementType.GEOMETRIC
    assert _classify(
        "יש לסמן עמודים וקירות במרחק של 0.5 מ' לפחות משפת הנסיעה"
    ) is RequirementType.GEOMETRIC


def test_document_examples():
    assert _classify("יש לצרף דוח הידרולוג") is RequirementType.DOCUMENT
    assert _classify("יש להגיש סקר אסבסט") is RequirementType.DOCUMENT


def test_approval_examples():
    assert _classify("נדרש אישור אגף התנועה טרם בדיקת התכנית באגף") is RequirementType.APPROVAL
    assert _classify("נדרש אישור אדריכלות טרם בדיקת התכנית באגף") is RequirementType.APPROVAL


def test_workflow_gate_example():
    assert _classify('איכה"ס - דרישות לאישור תחילת עבודות') is RequirementType.WORKFLOW_GATE


def test_completion_condition_example():
    assert _classify(
        'תנאי לתעודת גמר הגשת דו"ח אקוסטי עם מדידות לאחר ביצוע'
    ) is RequirementType.COMPLETION_CONDITION


def test_design_decision_example():
    assert _classify("יש לבחון שינוי גוונים כהים בחיפוי החזיתות") is RequirementType.DESIGN_DECISION


def test_annotation_still_wins_over_wording():
    """An update_schedule/update_dimension/update_text action is always ANNOTATION."""
    comment = CommentAnalyzer().analyze_comment("C-001", "יש לעדכן את טבלת החניה",
                                                department="Parking")
    assert comment.required_action == "update_schedule"
    assert comment.requirement_type is RequirementType.ANNOTATION


def test_english_examples():
    assert _classify("Increase the parking width to at least 2.50 m") is RequirementType.GEOMETRIC
    assert _classify("Please submit a hydrologic report") is RequirementType.DOCUMENT
    assert _classify("Traffic engineer approval is required before departmental review"
                     ) is RequirementType.APPROVAL


def test_plain_statement_has_no_requirement_type():
    comment = CommentAnalyzer().analyze_comment("C-001", "נרשם", department="Planning")
    assert comment.required_action == "none"
    assert comment.requirement_type is None
