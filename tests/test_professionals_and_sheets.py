"""Professional approval tracking and sheet/revision awareness (spec §8, §28, §35)."""

from __future__ import annotations

from archagent.professionals import ApprovalTracker, Professional
from archagent.professionals.roles import TRAFFIC_ENGINEER
from archagent.evidence import ProfessionalApprovalStatus
from archagent.sheets import Revision, Sheet, SheetIndex


def test_geometry_solvable_but_professional_deliverable_still_required():
    tracker = ApprovalTracker()
    tracker.require("REQ-1", professional_owner=TRAFFIC_ENGINEER,
                    required_license=TRAFFIC_ENGINEER)
    outstanding = tracker.outstanding()
    assert len(outstanding) == 1
    assert outstanding[0].requirement_id == "REQ-1"


def test_recording_a_correctly_licensed_professional_satisfies_the_approval():
    tracker = ApprovalTracker()
    tracker.require("REQ-1", professional_owner=TRAFFIC_ENGINEER,
                    required_license=TRAFFIC_ENGINEER)
    engineer = Professional(name="Dana Cohen", role=TRAFFIC_ENGINEER, license_valid=True)
    approval = tracker.record("REQ-1", engineer, document_ref="A-TR-02")
    assert approval.approval_status == ProfessionalApprovalStatus.PRESENT
    assert tracker.outstanding() == []


def test_wrong_role_is_rejected_not_silently_accepted():
    tracker = ApprovalTracker()
    tracker.require("REQ-1", professional_owner=TRAFFIC_ENGINEER,
                    required_license=TRAFFIC_ENGINEER)
    architect = Professional(name="Someone Else", role="architecture", license_valid=True)
    approval = tracker.record("REQ-1", architect)
    assert approval.approval_status == ProfessionalApprovalStatus.REJECTED
    assert tracker.outstanding() == [approval]


def test_sheet_index_tracks_revisions_and_supersession():
    index = SheetIndex()
    index.add(Sheet(sheet_number="A-301", revision="A", title="Elevations"))
    index.add(Sheet(sheet_number="A-301", revision="B", title="Elevations"))
    assert index.latest("A-301").revision == "B"
    assert [s.revision for s in index.superseded("A-301")] == ["A"]
    assert index.all_latest()[0].revision == "B"


def test_revision_notes_are_kept_separately_from_the_sheet_label():
    index = SheetIndex()
    index.add(Sheet(sheet_number="A-301", revision="B", title="Elevations"))
    index.add_revision_note(Revision(revision_id="REV-1", sheet_number="A-301", number="B",
                                     description="darker cladding colour", author="architect"))
    notes = index.notes_for("A-301")
    assert len(notes) == 1
    assert notes[0].description == "darker cladding colour"
    assert index.notes_for("DR-01") == []
