import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from archagent.drawing.json_model import JSONModelDriver  # noqa: E402

EXAMPLE = ROOT / "examples" / "project"
EXAMPLE_HE = ROOT / "examples" / "project_he"


def _copy(source, destination):
    shutil.copytree(source, destination)
    for stale in ("versions", "output"):
        shutil.rmtree(destination / stale, ignore_errors=True)
    return destination


@pytest.fixture
def project(tmp_path):
    """A writable copy of the example project."""
    return _copy(EXAMPLE, tmp_path / "project")


@pytest.fixture
def project_he(tmp_path):
    """A writable copy of the Hebrew example project."""
    return _copy(EXAMPLE_HE, tmp_path / "project_he")


@pytest.fixture
def answers_file(tmp_path):
    path = tmp_path / "answers.json"
    path.write_text('{"C-005": "approve"}', encoding="utf-8")
    return path


@pytest.fixture
def driver(project):
    return JSONModelDriver.load(project / "source" / "project.json")


@pytest.fixture
def small_model():
    return {
        "site": {"plot": {"kind": "rect", "x": 0, "y": 0, "w": 20, "h": 20}},
        "sheets": [{"id": "A-101", "name": "Plan"}],
        "elements": [
            {"id": "a", "type": "parking", "label": "A1", "level": "L0", "sheet": "A-101",
             "geometry": {"kind": "rect", "x": 0, "y": 0, "w": 2.4, "h": 5.0},
             "properties": {"width_axis": "x", "anchor": "south_west"}},
            {"id": "b", "type": "parking", "label": "B1", "level": "L0", "sheet": "A-101",
             "geometry": {"kind": "rect", "x": 2.4, "y": 0, "w": 2.4, "h": 5.0},
             "properties": {"width_axis": "x", "anchor": "south_west"}},
        ],
        "schedules": {
            "table": {"title": "Parking schedule", "source": {"type": "parking"},
                      "fields": {"Mark": "label", "Width": "width"}, "rows": []},
        },
    }
