"""The run payload surfaces requirement_type/discipline for the Web Editor
(UPDATE_PERMIT_ENGINE.md §22 - extend, do not rebuild)."""

from __future__ import annotations

from archagent.consult import ScriptedResponder
from archagent.lang.messages import Messages
from archagent.models import RequirementType
from archagent.orchestrator import Orchestrator
from archagent.payload import run_payload


def test_payload_comments_carry_requirement_type_and_discipline(project_petah_tikva):
    result = Orchestrator(
        project_petah_tikva, mode="consultation",
        responder=ScriptedResponder({"C-001": "approve"}),
    ).run()
    payload = run_payload(result, Messages(result.language))
    by_id = {item["id"]: item for item in payload["comments"]}

    assert by_id["C-001"]["requirement_type"] == RequirementType.GEOMETRIC.value
    assert by_id["C-001"]["requirement_type_label"]  # non-empty, localised
    assert by_id["C-001"]["discipline"] == "architecture"

    assert by_id["C-007"]["requirement_type"] == RequirementType.DOCUMENT.value
    assert by_id["C-008"]["requirement_type"] == RequirementType.APPROVAL.value
    assert by_id["C-011"]["discipline"] == "environment"

    # A plain statement (none in this project) would carry an empty string,
    # never a fabricated type - covered directly against the classifier in
    # tests/test_requirement_types.py; here we only check the payload wiring.
    assert all(isinstance(item["requirement_type"], str) for item in payload["comments"])
