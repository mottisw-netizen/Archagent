"""Evidence / professional approval model and checker (spec §15, §21, §28, §38)."""

from __future__ import annotations

from archagent.evidence import (
    Evidence,
    EvidenceGraph,
    EvidenceStatus,
    PermitEvidenceChecker,
    ProfessionalApproval,
    ProfessionalApprovalStatus,
    ResolutionState,
    resolve,
)


# ----------------------------------------------------------------------
# checker - never fabricates
# ----------------------------------------------------------------------
def test_missing_evidence_is_reported_missing_not_assumed():
    checker = PermitEvidenceChecker()
    result = checker.check("hydrologic_report", project_id="P-1")
    assert result.status == EvidenceStatus.MISSING
    assert result.present is False
    assert result.authority_approval_present is None


def test_present_but_wrong_project_is_incomplete():
    checker = PermitEvidenceChecker([
        Evidence(type="acoustic_report", project_id="OTHER-PROJECT",
                professional_role="acoustic_consultant", approval_status="approved"),
    ])
    result = checker.check("acoustic_report", project_id="P-1",
                           expected_role="acoustic_consultant")
    assert result.status == EvidenceStatus.INCOMPLETE
    assert result.refers_to_project is False
    assert any("does not identify this project" in note for note in result.notes)


def test_satisfied_requires_every_requested_check_to_pass():
    checker = PermitEvidenceChecker([
        Evidence(type="hydrologic_report", project_id="P-1",
                professional_role="hydrologist", revision="B", signed=True,
                approval_status="approved", covered_elements=["chamber-D-04"]),
    ])
    result = checker.check(
        "hydrologic_report", project_id="P-1", expected_role="hydrologist",
        expected_revision="B", affected_element="chamber-D-04",
        require_signature=True, require_authority_approval=True)
    assert result.status == EvidenceStatus.SATISFIED
    assert result.present is True
    assert result.authority_approval_present is True


def test_unsigned_document_is_incomplete_when_signature_required():
    checker = PermitEvidenceChecker([Evidence(type="asbestos_survey", project_id="P-1")])
    result = checker.check("asbestos_survey", project_id="P-1", require_signature=True)
    assert result.status == EvidenceStatus.INCOMPLETE
    assert result.signed is False


# ----------------------------------------------------------------------
# resolution semantics - spec §38 worked example
# ----------------------------------------------------------------------
def test_parking_geometry_resolved_but_approval_missing_is_not_fully_resolved():
    result = resolve(needs_geometry=True, needs_approval=True,
                     geometry_ok=True, approval_ok=False)
    assert result.state == ResolutionState.GEOMETRY_RESOLVED
    assert result.state != ResolutionState.FULLY_RESOLVED
    assert "geometry corrected" in result.describe()
    assert "professional deliverable still required" in result.describe()


def test_fully_resolved_needs_every_applicable_dimension():
    result = resolve(needs_geometry=True, needs_approval=True,
                     geometry_ok=True, approval_ok=True)
    assert result.state == ResolutionState.FULLY_RESOLVED


def test_nothing_applicable_is_not_resolved():
    result = resolve()
    assert result.state == ResolutionState.NOT_RESOLVED


def test_professional_approval_satisfied_property():
    pending = ProfessionalApproval(requirement_id="REQ-1", professional_owner="traffic_engineer")
    assert pending.satisfied is False
    present = ProfessionalApproval(requirement_id="REQ-1",
                                   approval_status=ProfessionalApprovalStatus.PRESENT)
    assert present.satisfied is True
    expired = ProfessionalApproval(requirement_id="REQ-1",
                                   approval_status=ProfessionalApprovalStatus.EXPIRED)
    assert expired.satisfied is False


def test_evidence_carries_extraction_provenance():
    scanned = Evidence(type="acoustic_report", document="ENV-03.pdf", page=4,
                       region="table 2", extraction_method="ocr", confidence=0.62)
    assert scanned.page == 4
    assert scanned.extraction_method == "ocr"
    assert scanned.confidence == 0.62
    # A manually-entered record defaults to full confidence, never fabricated
    # low/high - it simply was not extracted by OCR.
    manual = Evidence(type="hydrologic_report")
    assert manual.extraction_method == "manual"
    assert manual.confidence == 1.0


# ----------------------------------------------------------------------
# evidence graph traceability - spec §22
# ----------------------------------------------------------------------
def test_drawing_to_document_traceability_path():
    graph = EvidenceGraph()
    graph.add_node("R-123", "requirement")
    graph.add_node("P-17", "drawing_element", "ParkingSpace P-17")
    graph.add_node("A-TR-02", "sheet", "Traffic plan A-TR-02")
    graph.add_node("balance-table", "document", "Parking balance table")
    graph.add_node("traffic-approval", "approval", "Traffic engineer approval")
    graph.add_edge("R-123", "P-17", "satisfies")
    graph.add_edge("P-17", "A-TR-02", "shown_on")
    graph.add_edge("A-TR-02", "balance-table", "supports")
    graph.add_edge("balance-table", "traffic-approval", "depends_on")

    path = [node["node_id"] for node in graph.trace("R-123")]
    assert path == ["R-123", "P-17", "A-TR-02", "balance-table", "traffic-approval"]


def test_unknown_node_kind_rejected():
    graph = EvidenceGraph()
    try:
        graph.add_node("x", "not_a_kind")
        assert False, "expected ValueError"
    except ValueError:
        pass
