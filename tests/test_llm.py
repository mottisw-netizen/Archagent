"""Claude interprets; the drawing measures.

These tests pin the boundary: what the model says is validated before it can
touch anything, a reading it cannot justify is escalated rather than applied,
and when the model is unavailable the run still completes deterministically.
"""

from pathlib import Path

import pytest

from archagent.comments import CommentAnalyzer
from archagent.consult import ScriptedResponder
from archagent.llm import ScriptedClient
from archagent.llm.client import CachingClient, LLMError, from_env
from archagent.llm.disambiguate import ElementDisambiguator
from archagent.llm.interpret import LLMCommentInterpreter, requirements_agree
from archagent.llm.summarise import RunSummariser
from archagent.mapping import ElementMapper
from archagent.models import CommentStatus, Requirement, Resolution
from archagent.orchestrator import Orchestrator

WIDEN = "יש להגדיל את רוחב מקום חניה P12 ל-2.50 מ'."


def reading(**over):
    data = {
        "language": "he", "department": "Traffic", "kind": "measurable",
        "summary": "רוחב מקום חניה P12 יהיה לפחות 2.50 מ'",
        "requirement": {"metric": "width", "op": ">=", "value": 2.5, "unit": "m",
                        "subject_kind": "element_label", "subject_label": "P12",
                        "subject_type": "parking", "edge": "none"},
        "annotation_action": None, "ambiguities": [],
        "confidence": {"extraction": 1.0, "interpretation": 0.9}, "reasoning": "",
    }
    data.update(over)
    return data


def analyzer_for(data):
    return CommentAnalyzer(client=ScriptedClient(lambda system, user, schema: data))


# ----------------------------------------------------------------------
# validation of what the model returns
# ----------------------------------------------------------------------
@pytest.mark.parametrize("broken,expected", [
    ({"metric": "vibe"}, "unsupported metric"),
    ({"op": "≈"}, "unsupported operator"),
    ({"unit": "cubits"}, "unsupported unit"),
    ({"value": "two point five"}, "value is not a number"),
    ({"value": -3}, "value is out of range"),
    ({"metric": "setback", "edge": "none"}, "must name an edge"),
])
def test_invalid_readings_are_rejected_not_executed(broken, expected):
    data = reading()
    data["requirement"] = {**data["requirement"], **broken}
    result = LLMCommentInterpreter(
        ScriptedClient(lambda s, u, sch: data)).interpret("C-001", WIDEN)
    assert result.kind == "unclear" and result.requirement is None
    assert any(expected in item for item in result.rejected)


def test_a_requirement_without_a_subject_is_rejected():
    data = reading()
    data["requirement"] = {**data["requirement"], "subject_kind": "element_label",
                           "subject_label": None, "subject_type": None}
    result = LLMCommentInterpreter(ScriptedClient(lambda s, u, sch: data)).interpret("C", WIDEN)
    assert result.requirement is None and result.rejected


def test_confidence_is_clamped_to_the_unit_interval():
    result = LLMCommentInterpreter(ScriptedClient(
        lambda s, u, sch: reading(confidence={"extraction": 5, "interpretation": -2})
    )).interpret("C-001", WIDEN)
    assert result.extraction == 1.0 and result.interpretation == 0.0


def test_the_prompt_carries_the_drawing_inventory_but_no_dimensions(driver):
    from archagent.llm.interpret import inventory_from_driver
    client = ScriptedClient(lambda s, u, sch: reading())
    LLMCommentInterpreter(client, inventory=inventory_from_driver(driver)).interpret("C-1", WIDEN)
    _system, user = client.prompts[0]
    assert "P12 (parking)" in user
    assert "2.4" not in user and "2.40" not in user


# ----------------------------------------------------------------------
# model-first analysis with the rules as a cross-check
# ----------------------------------------------------------------------
def test_agreement_between_model_and_rules_raises_confidence():
    comment = analyzer_for(reading()).analyze_comment("C-001", WIDEN, "תנועה")
    assert comment.interpretation_source == "llm+rules"
    assert comment.confidence.value >= 0.9
    assert "confirmed by the deterministic parser" in comment.parse_notes


def test_disagreement_drops_confidence_and_records_both_readings():
    data = reading(requirement={"metric": "width", "op": ">=", "value": 2.8, "unit": "m",
                                "subject_kind": "element_label", "subject_label": "P12",
                                "subject_type": "parking", "edge": "none"})
    comment = analyzer_for(data).analyze_comment("C-001", WIDEN, "תנועה")
    assert comment.confidence.value <= 0.55        # below the consultation threshold
    assert any("disagree" in note for note in comment.parse_notes)


def test_the_model_reads_prose_the_rules_cannot():
    text = "יש להסיג את חזית הבניין הצפונית כך שתעמוד בקו הבניין הנדרש."
    data = reading(kind="measurable", summary="נסיגה צפונית של 3.00 מ'",
                   requirement={"metric": "setback", "op": ">=", "value": 3.0, "unit": "m",
                                "subject_kind": "element_type", "subject_type": "building",
                                "edge": "north"},
                   confidence={"extraction": 1.0, "interpretation": 0.72})
    comment = analyzer_for(data).analyze_comment("C-009", text, "תכנון")
    assert comment.requirement.metric == "setback"
    assert comment.summary == "נסיגה צפונית של 3.00 מ'"
    assert comment.interpretation_source == "llm"


def test_an_unreachable_model_falls_back_to_the_rules():
    class Down:
        model = "claude-opus-5"

        def complete_json(self, *args, **kwargs):
            raise LLMError("no credentials")

    analyzer = CommentAnalyzer(client=Down())
    comment = analyzer.analyze_comment("C-001", WIDEN, "תנועה")
    assert comment.requirement.value == pytest.approx(2.5)
    assert comment.interpretation_source == "rules"
    assert comment.confidence.value <= 0.75
    assert analyzer.failures


def test_a_statement_is_recognised_by_the_model():
    comment = analyzer_for(reading(kind="statement", requirement=None,
                                   summary="נרשם")).analyze_comment("C-008", "נרשם.")
    assert comment.required_action == "none"


def test_requirements_agree_compares_subject_and_value():
    first = Requirement({"selector": {"label": "P12"}}, "width", ">=", 2.5)
    assert requirements_agree(first, Requirement({"selector": {"label": "p12"}},
                                                 "width", ">=", 2.5))
    assert not requirements_agree(first, Requirement({"selector": {"label": "P13"}},
                                                     "width", ">=", 2.5))


# ----------------------------------------------------------------------
# disambiguation
# ----------------------------------------------------------------------
def test_the_model_can_break_a_tie_the_rules_cannot(driver):
    choice = {"selected": "parking_p13", "confidence": 0.88,
              "reasoning": "ההערה מתייחסת לחניית המבקרים"}
    mapper = ElementMapper(driver, disambiguator=ElementDisambiguator(
        ScriptedClient(lambda s, u, sch: choice)))
    comment = CommentAnalyzer().analyze_comment(
        "C-003", "יש להגדיל את רוחב חניית המבקרים ל-2.50 מ'.", "תנועה")
    mapping = mapper.map_comment(comment)
    assert mapping.resolution is Resolution.SELECTED_BY_DISCRIMINATOR
    assert mapping.selected == ["parking_p13"]
    assert "המבקרים" in mapping.notes


def test_an_element_that_was_never_offered_is_refused(driver):
    mapper = ElementMapper(driver, disambiguator=ElementDisambiguator(
        ScriptedClient(lambda s, u, sch: {"selected": "the_moon", "confidence": 1.0,
                                          "reasoning": ""})))
    comment = CommentAnalyzer().analyze_comment(
        "C-003", "יש להגדיל את רוחב מקום החניה ל-2.50 מ'.", "תנועה")
    mapping = mapper.map_comment(comment)
    assert mapping.resolution is Resolution.AMBIGUOUS
    assert "not offered" in mapping.notes


def test_the_model_may_decline_to_choose(driver):
    mapper = ElementMapper(driver, disambiguator=ElementDisambiguator(
        ScriptedClient(lambda s, u, sch: {"selected": None, "confidence": 0.2,
                                          "reasoning": "אין מזהה מבחין"})))
    comment = CommentAnalyzer().analyze_comment(
        "C-003", "יש להגדיל את רוחב מקום החניה ל-2.50 מ'.", "תנועה")
    mapping = mapper.map_comment(comment)
    assert mapping.resolution is Resolution.AMBIGUOUS
    assert mapping.selected == []


def test_a_model_choice_never_scores_as_certain(driver):
    mapper = ElementMapper(driver, disambiguator=ElementDisambiguator(
        ScriptedClient(lambda s, u, sch: {"selected": "parking_p13", "confidence": 1.0,
                                          "reasoning": "x"})))
    comment = CommentAnalyzer().analyze_comment(
        "C-003", "יש להגדיל את רוחב מקום החניה ל-2.50 מ'.", "תנועה")
    mapping = mapper.map_comment(comment)
    chosen = next(c for c in mapping.candidates if c.element_id == "parking_p13")
    assert chosen.confidence <= 0.9


# ----------------------------------------------------------------------
# summary, cache, credentials
# ----------------------------------------------------------------------
def test_the_summary_is_optional_and_never_blocks_a_run():
    class Down:
        model = "x"

        def complete_json(self, *args, **kwargs):
            raise LLMError("rate limited")

    assert RunSummariser(Down()).summarise("Hebrew", "facts") == ("", [])


def test_the_cache_makes_a_re_run_free(tmp_path):
    inner = ScriptedClient(lambda s, u, sch: reading())
    client = CachingClient(inner, tmp_path / "cache")
    client.complete_json("system", "user", {"type": "object"})
    client.complete_json("system", "user", {"type": "object"})
    assert inner.calls == 1 and client.hits == 1 and client.misses == 1


def test_from_env_returns_nothing_without_credentials(monkeypatch, tmp_path):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.setattr(Path, "exists", lambda self: False)
    assert from_env() is None


# ----------------------------------------------------------------------
# the whole pipeline, model in the loop
# ----------------------------------------------------------------------
class FakeClaude:
    """Answers all three kinds of request the pipeline makes."""

    model = "claude-opus-5-fake"

    def __init__(self):
        self.calls = 0
        self.usage = {"input_tokens": 10, "output_tokens": 5}
        self.seen: list[str] = []

    def complete_json(self, system, user, schema, effort=None):
        from archagent.llm.client import LLMResponse
        self.calls += 1
        if "which element" in system:
            self.seen.append("disambiguate")
            return LLMResponse({"selected": None, "confidence": 0.3,
                                "reasoning": "ההערה אינה מזהה חניה מסוימת"})
        if "opening paragraph" in system:
            self.seen.append("summary")
            return LLMResponse({"summary": "בוצעו תיקונים בהתאם להערות הוועדה.",
                                "attention": ["להחליט על תוספת מקומות חניה"]})
        self.seen.append("interpret")
        return LLMResponse(self._interpret(user))

    @staticmethod
    def _interpret(prompt: str) -> dict:
        # Only the comment decides the answer - the inventory is context.
        user = prompt.split("<comment>", 1)[-1].split("</comment>", 1)[0]
        if "P12" in user and "טבלת" not in user:
            return reading()
        if "טבלת" in user:
            return reading(kind="annotation", requirement=None,
                           annotation_action="update_schedule",
                           summary="לעדכן את טבלת החניות")
        if "קו בניין" in user:
            return reading(department="Planning", summary="נסיגה צפונית של 3.00 מ'",
                           requirement={"metric": "setback", "op": ">=", "value": 3.0,
                                        "unit": "m", "subject_kind": "element_type",
                                        "subject_type": "building", "edge": "north"},
                           confidence={"extraction": 1.0, "interpretation": 0.93})
        if "מקומות חניה" in user:
            return reading(department="Planning", summary="נדרשים 34 מקומות חניה",
                           requirement={"metric": "count", "op": ">=", "value": 34,
                                        "unit": "count", "subject_kind": "element_type",
                                        "subject_type": "parking", "edge": "none"})
        if "המעבר החופשי" in user:
            return reading(summary="רוחב נטו 5.50 מ'",
                           requirement={"metric": "clear_width", "op": ">=", "value": 5.5,
                                        "unit": "m", "subject_kind": "element_type",
                                        "subject_type": "driveway", "edge": "none"})
        if "נרשם" in user:
            return reading(kind="statement", requirement=None, summary="נרשם")
        if "רוחב מקום החניה" in user:
            return reading(summary="רוחב מקום חניה 2.50 מ'",
                           requirement={"metric": "width", "op": ">=", "value": 2.5,
                                        "unit": "m", "subject_kind": "element_type",
                                        "subject_type": "parking", "edge": "none"},
                           ambiguities=["ההערה אינה מציינת באיזו חניה מדובר"])
        return reading(kind="unclear", requirement=None,
                       summary="לא ניתן לחלץ דרישה נמדדת",
                       confidence={"extraction": 1.0, "interpretation": 0.3})


def test_a_full_hebrew_run_with_the_model_in_the_loop(project_he):
    claude = FakeClaude()
    result = Orchestrator(project_he, llm=claude,
                          responder=ScriptedResponder({"C-005": "approve"})).run()
    assert {"interpret", "disambiguate", "summary"} <= set(claude.seen)
    statuses = {item.comment_id: item.status for item in result.validation.comments}
    assert statuses["C-001"] is CommentStatus.RESOLVED
    assert statuses["C-005"] is CommentStatus.RESOLVED
    assert statuses["C-003"] is CommentStatus.REQUIRES_HUMAN_REVIEW   # model declined too
    assert result.llm["model"] == "claude-opus-5-fake" and result.llm["calls"] > 0

    report = Path(result.files["correction_report"]).read_text(encoding="utf-8")
    assert "בוצעו תיקונים בהתאם להערות הוועדה." in report      # the model's paragraph
    assert "דורש את החלטתך" in report
    assert "רוחב מקום חניה P12 יהיה לפחות 2.50 מ'" in report   # the model's reading


def test_the_run_still_completes_when_the_model_is_down(project_he):
    class Down:
        model = "claude-opus-5"
        calls = 0
        usage: dict = {}

        def complete_json(self, *args, **kwargs):
            raise LLMError("connection refused")

    # With no model the rules carry the run, but at a lower confidence - so the
    # corrections that would have been automatic now come through consultation.
    result = Orchestrator(project_he, llm=Down(), responder=ScriptedResponder(
        {"C-001": "approve", "C-005": "approve"})).run()
    statuses = {item.comment_id: item.status for item in result.validation.comments}
    assert statuses["C-001"] is CommentStatus.RESOLVED
    assert result.llm["failures"]
    report = Path(result.files["correction_report"]).read_text(encoding="utf-8")
    assert "# דוח תיקון הערות רישוי" in report
