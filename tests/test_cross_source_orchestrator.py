"""Cross-source conflict detection wired into a real Orchestrator.run()."""

from __future__ import annotations

import json

from archagent.orchestrator import Orchestrator

SITE = {"plot": {"kind": "rect", "x": 0.0, "y": 0.0, "w": 40.0, "h": 30.0}}


def _model(elements):
    return {"project_id": "p", "units": "m", "north": "+y", "site": SITE,
           "sheets": [], "elements": elements, "schedules": {}}


def test_orchestrator_reports_a_real_cross_source_conflict(tmp_path):
    project = tmp_path / "project"
    (project / "municipal_comments").mkdir(parents=True)
    (project / "municipal_comments" / "comments.md").write_text(
        "Department: Planning\n\nC-001: Noted.\n", encoding="utf-8")

    primary = tmp_path / "architecture.json"
    primary.write_text(json.dumps(_model([
        {"id": "basement-wall", "type": "wall", "label": "basement wall",
         "geometry": {"kind": "rect", "x": 10.5, "y": 10.0, "w": 0.2, "h": 0.2}},
    ])), encoding="utf-8")

    civil = tmp_path / "civil.json"
    civil.write_text(json.dumps(_model([
        {"id": "drain-1", "type": "municipal_drain", "label": "municipal drain",
         "geometry": {"kind": "rect", "x": 10.0, "y": 10.0, "w": 0.2, "h": 0.2}},
    ])), encoding="utf-8")

    result = Orchestrator(project, mode="consultation",
                          sources=[str(primary), str(civil)]).run()

    assert len(result.cross_source_conflicts) == 1
    conflict = result.cross_source_conflicts[0]
    assert {conflict.source_element, conflict.target_element} == {"basement-wall", "drain-1"}

    refs = {item["ref"] for item in result.context.open_items}
    assert any("basement-wall" in ref and "drain-1" in ref for ref in refs)
