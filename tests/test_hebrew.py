"""Hebrew is a first-class input and output language, not a translation layer."""

import json
from pathlib import Path

import pytest

from archagent.comments import CommentAnalyzer
from archagent.constraints import ConstraintLedger, constraints_from_document
from archagent.consult import ScriptedResponder
from archagent.lang import detect_script, get, parse_number
from archagent.lang.messages import Messages
from archagent.models import CommentStatus, Priority, Requirement
from archagent.orchestrator import Orchestrator


@pytest.fixture
def analyzer():
    return CommentAnalyzer()


@pytest.mark.parametrize("text,metric,op,value,unit", [
    ("יש להגדיל את רוחב מקום חניה P12 ל-2.50 מ'.", "width", ">=", 2.5, "m"),
    ("רוחב מקום חניה מס' 12 לא יפחת מ-2.50 מטר.", "width", ">=", 2.5, "m"),
    ("הנסיגה הצפונית תהיה לפחות 3.00 מ'.", "setback", ">=", 3.0, "m"),
    ("קו בניין צפוני לא יפחת מ-3.0 מ'.", "setback", ">=", 3.0, "m"),
    ('שטח הבנייה הכולל לא יעלה על 1,850 מ"ר.', "floor_area", "<=", 1850.0, "m2"),
    ("יש להקצות לפחות 34 מקומות חניה.", "count", ">=", 34, "count"),
    ("רוחב המעבר החופשי בשביל הגישה לא יפחת מ-5.50 מ'.", "clear_width", ">=", 5.5, "m"),
    ("יש להקטין את עומק המרפסת ל-1.20 מ'.", "length", "<=", 1.2, "m"),
    ("גובה הבניין לא יעלה על 24.0 מ'.", "height", "<=", 24.0, "m"),
    ("יש להרחיב את שביל הגישה ל-3.00 מטר.", "width", ">=", 3.0, "m"),
    ("רוחב מקום החניה לא יפחת מ-250 ס\"מ.", "width", ">=", 250, "cm"),
])
def test_hebrew_comments_become_testable_requirements(analyzer, text, metric, op, value, unit):
    comment = analyzer.analyze_comment("C-001", text, "תנועה")
    assert comment.requirement is not None, text
    assert comment.requirement.metric == metric
    assert comment.requirement.op == op
    assert comment.requirement.value == pytest.approx(value)
    assert comment.requirement.unit == unit


def test_thousands_separator_is_not_a_decimal_point():
    assert parse_number("1,850") == 1850.0
    assert parse_number("2,50") == 2.5


def test_hebrew_prefixes_do_not_hide_the_metric():
    lexicon = get("he")
    for form in ("רוחב", "הרוחב", "ברוחב", "לרוחב", "מהרוחב"):
        assert lexicon.metric_of(form) == "width", form


def test_gershayim_and_geresh_normalise():
    lexicon = get("he")
    assert lexicon.unit_of("מ״ר") == "m2"
    assert lexicon.unit_of("מ׳") == "m"


def test_hebrew_statement_demands_nothing(analyzer):
    for text in ("נרשם.", "לידיעה.", "אין הערות."):
        assert analyzer.analyze_comment("C-1", text).required_action == "none"


def test_hebrew_prose_without_a_number_is_escalated(analyzer):
    comment = analyzer.analyze_comment("C-7", "יש לשפר את חזית הבניין הפונה לרחוב.")
    assert comment.requirement is None
    assert comment.confidence.value < 0.6


def test_original_hebrew_text_is_never_translated(analyzer):
    text = "יש להגדיל את רוחב מקום חניה P12 ל-2.50 מ'."
    assert analyzer.analyze_comment("C-1", text).original_text == text


def test_hebrew_department_headings(analyzer):
    document = ("מחלקה: תנועה\n\n1. יש להגדיל את רוחב מקום חניה P12 ל-2.50 מ'.\n"
                "מחלקה: כבאות\n2. יש להרחיב את שביל הגישה ל-4.00 מ'.\n")
    comments = analyzer.analyze_document(document)
    assert [c.department for c in comments] == ["Traffic", "Fire Safety"]
    assert [c.comment_id for c in comments] == ["C-001", "C-002"]


def test_hebrew_comment_numbering_forms(analyzer):
    document = "הערה 4: יש להגדיל את רוחב מקום חניה P12 ל-2.50 מ'.\n"
    assert analyzer.analyze_document(document)[0].comment_id == "C-004"


def test_hebrew_priority_tag_in_a_zoning_document():
    ledger = ConstraintLedger()
    created = constraints_from_document(
        "- קו בניין צפוני לא יפחת מ-3.00 מ' [קריטי]\n", "Zoning Plan", "tabaa.md", ledger)
    assert created[0].priority is Priority.CRITICAL
    assert created[0].test.metric == "setback"


def test_script_detection_ignores_latin_marks():
    assert detect_script("יש להגדיל את רוחב מקום חניה P12") == "he"
    assert detect_script("Increase parking space P12") == "en"


def test_requirement_renders_in_hebrew():
    m = Messages("he")
    requirement = Requirement({"element_id": "building", "label": "building", "edge": "north"},
                              "setback", ">=", 3.0)
    rendered = requirement.describe_in(m)
    assert "נסיגה צפונית" in rendered and "3.00 מ'" in rendered


def test_hebrew_run_produces_a_hebrew_report(project_he):
    result = Orchestrator(project_he, responder=ScriptedResponder({"C-005": "approve"})).run()
    assert result.language == "he"
    report = Path(result.files["correction_report"]).read_text(encoding="utf-8")
    assert "# דוח תיקון הערות רישוי" in report
    assert 'dir="rtl"' in report
    assert "## פריטים פתוחים" in report
    assert "בעל הרישיון האחראי" in report          # the sign-off
    assert "## Summary" not in report and "Open items" not in report
    statuses = {item.comment_id: item.status for item in result.validation.comments}
    assert statuses["C-001"] is CommentStatus.RESOLVED
    assert statuses["C-005"] is CommentStatus.RESOLVED
    assert statuses["C-008"] is CommentStatus.NOT_APPLICABLE


def test_hebrew_run_edits_the_model_the_same_way(project_he):
    result = Orchestrator(project_he, responder=ScriptedResponder({"C-005": "approve"})).run()
    model = json.loads((project_he / "versions" / result.version /
                        f"project_{result.version}.json").read_text(encoding="utf-8"))
    p12 = next(e for e in model["elements"] if e["id"] == "parking_p12")
    assert p12["geometry"]["w"] == pytest.approx(2.5)
    assert p12["geometry"]["x"] == pytest.approx(8.4)   # widened away from P13
    building = next(e for e in model["elements"] if e["id"] == "building")
    assert building["geometry"]["y"] == pytest.approx(19.6)


def test_hebrew_comparison_page_is_right_to_left(project_he):
    result = Orchestrator(project_he, responder=ScriptedResponder({"C-005": "approve"})).run()
    html = Path(result.files["comparison"]).read_text(encoding="utf-8")
    assert 'dir="rtl"' in html and 'lang="he"' in html
    assert "לפני / אחרי" in html


def test_hebrew_consultation_question_is_in_hebrew(project_he):
    result = Orchestrator(project_he, responder=ScriptedResponder({"C-005": "approve"})).run()
    transcript = Path(result.files["consultation"]).read_text(encoding="utf-8")
    assert "הערת הרישוי" in transcript and "התיקון המוצע" in transcript
    assert "קו בניין צפוני" in transcript


def test_language_can_be_forced(project_he):
    result = Orchestrator(project_he, language="en",
                          responder=ScriptedResponder({"C-005": "approve"})).run()
    report = Path(result.files["correction_report"]).read_text(encoding="utf-8")
    assert "# Municipal Correction Report" in report
    # the comments themselves stay in their own language
    assert "קו בניין צפוני" in report
