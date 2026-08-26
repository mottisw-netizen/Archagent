import pytest

from archagent.comments import CommentAnalyzer
from archagent.constraints import (
    ConstraintLedger,
    constraints_from_comments,
    constraints_from_document,
    derive_implicit_constraints,
    evaluate_constraint,
    find_conflicts,
)
from archagent.mapping import ElementMapper
from archagent.models import Constraint, MunicipalComment, Priority, Requirement, Resolution


@pytest.fixture
def analyzer():
    return CommentAnalyzer()


@pytest.mark.parametrize("text,metric,op,value", [
    ("Increase parking space P12 width to 2.50 m.", "width", ">=", 2.5),
    ("The northern setback must be at least 3.0 m.", "setback", ">=", 3.0),
    ("Provide at least 34 parking spaces.", "count", ">=", 34),
    ("Total floor area must not exceed 1850 m2.", "floor_area", "<=", 1850),
    ("Driveway clear width shall be no less than 5.50 m.", "clear_width", ">=", 5.5),
    ("Reduce the balcony depth to 1.20 m.", "length", "<=", 1.2),
])
def test_requirements_are_extracted_as_testable_rules(analyzer, text, metric, op, value):
    comment = analyzer.analyze_comment("C-001", text)
    assert comment.requirement is not None
    assert (comment.requirement.metric, comment.requirement.op) == (metric, op)
    assert comment.requirement.value == pytest.approx(value)


def test_unparsed_prose_is_flagged_not_guessed(analyzer):
    comment = analyzer.analyze_comment("C-009", "Improve the facade composition.")
    assert comment.requirement is None
    assert comment.confidence.value < 0.6
    assert comment.parse_notes


def test_statement_comments_demand_no_action(analyzer):
    assert analyzer.analyze_comment("C-010", "Noted.").required_action == "none"


def test_original_text_is_preserved_verbatim(analyzer):
    text = "  Increase parking space P12 width to 2.50 m.  "
    assert analyzer.analyze_comment("C-001", text).original_text == text


def test_non_latin_comments_keep_their_language(analyzer):
    comment = analyzer.analyze_comment("C-011", "יש להגדיל את הרוחב")
    assert comment.language == "he"
    assert comment.original_text == "יש להגדיל את הרוחב"


def test_documents_are_split_by_department(analyzer):
    text = "Department: Traffic\n\nC-001: Increase parking space P12 width to 2.50 m.\n" \
           "Department: Fire Safety\nC-002: Provide at least 12 parking spaces.\n"
    comments = analyzer.analyze_document(text)
    assert [c.department for c in comments] == ["Traffic", "Fire Safety"]


def test_llm_hook_is_only_consulted_for_prose_the_parser_missed():
    calls = []

    def llm(text):
        calls.append(text)
        return {"subject": {"element_id": "x"}, "metric": "width", "op": ">=", "value": 1.0}

    analyzer = CommentAnalyzer(llm=llm)
    analyzer.analyze_comment("C-001", "Increase parking space P12 width to 2.50 m.")
    assert not calls
    comment = analyzer.analyze_comment("C-002", "Make the thing bigger somehow.")
    assert calls and comment.requirement.metric == "width"
    assert comment.confidence.value <= 0.7


def test_zoning_lines_become_critical_constraints():
    ledger = ConstraintLedger()
    created = constraints_from_document(
        "- Northern setback must be at least 3.0 m\n", "Zoning Plan", "z.md", ledger)
    assert created[0].priority is Priority.CRITICAL


def test_priority_tag_overrides_the_default():
    ledger = ConstraintLedger()
    created = constraints_from_document(
        "- Provide at least 4 parking spaces [low]\n", "Project Requirement", "r.md", ledger)
    assert created[0].priority is Priority.LOW


def test_comment_constraints_keep_the_comment_id():
    ledger = ConstraintLedger()
    analyzer = CommentAnalyzer()
    comment = analyzer.analyze_comment("C-001", "Increase parking space P12 width to 2.50 m.")
    created = constraints_from_comments([comment], ledger)
    assert created[0].constraint_id == "MC-C-001"
    assert created[0].origin_comment_id == "C-001"


def test_conflicting_constraints_resolve_by_priority():
    ledger = ConstraintLedger()
    ledger.add(Constraint("A", "Municipal Comment", "width >= 2.5", Priority.HIGH,
                          Requirement({"element_id": "p"}, "width", ">=", 2.5)))
    ledger.add(Constraint("B", "Approved Design", "width <= 2.4", Priority.MEDIUM,
                          Requirement({"element_id": "p"}, "width", "<=", 2.4)))
    conflict = find_conflicts(ledger)[0]
    assert conflict["winner"] == "A" and not conflict["requires_human"]


def test_equal_priority_conflicts_go_to_a_human():
    ledger = ConstraintLedger()
    ledger.add(Constraint("A", "Municipal Comment", "width >= 2.5", Priority.HIGH,
                          Requirement({"element_id": "p"}, "width", ">=", 2.5)))
    ledger.add(Constraint("B", "Municipal Comment", "width <= 2.4", Priority.HIGH,
                          Requirement({"element_id": "p"}, "width", "<=", 2.4)))
    assert find_conflicts(ledger)[0]["requires_human"]


def test_a_constraint_that_cannot_be_measured_is_not_evaluated(driver):
    constraint = Constraint("X", "Zoning Plan", "missing", Priority.CRITICAL,
                            Requirement({"element_id": "ghost"}, "width", ">=", 1.0))
    result = evaluate_constraint(driver, constraint)
    assert result.status == "not_evaluated" and "could not be measured" in result.note


def test_implicit_constraints_record_the_approved_design(driver):
    ledger = ConstraintLedger()
    created = derive_implicit_constraints(driver, ledger)
    assert any("must not fall below the approved" in c.rule for c in created)
    assert all(c.implicit and c.priority is Priority.MEDIUM for c in created)


def test_mapping_is_unique_when_the_comment_names_a_label(driver):
    analyzer = CommentAnalyzer()
    comment = analyzer.analyze_comment("C-001", "Increase parking space P12 width to 2.50 m.")
    mapping = ElementMapper(driver).map_comment(comment)
    assert mapping.resolution is Resolution.UNIQUE
    assert mapping.selected == ["parking_p12"]
    assert mapping.before["value"] == pytest.approx(2.4)


def test_mapping_is_ambiguous_without_a_discriminator(driver):
    analyzer = CommentAnalyzer()
    comment = analyzer.analyze_comment("C-003", "Increase the parking space width to 2.50 m.")
    mapping = ElementMapper(driver).map_comment(comment)
    assert mapping.resolution is Resolution.AMBIGUOUS
    assert mapping.selected == []


def test_mapping_reports_a_missing_element(driver):
    comment = MunicipalComment(
        comment_id="C-020", department="Planning", original_text="widen P99",
        requirement=Requirement({"selector": {"label": "P99"}}, "width", ">=", 2.5))
    mapping = ElementMapper(driver).map_comment(comment)
    assert mapping.resolution is Resolution.NOT_FOUND


def test_set_metrics_map_to_the_whole_set(driver):
    analyzer = CommentAnalyzer()
    comment = analyzer.analyze_comment("C-006", "Provide at least 34 parking spaces.")
    mapping = ElementMapper(driver).map_comment(comment)
    assert mapping.resolution is Resolution.UNIQUE
    assert len(mapping.selected) == 3
