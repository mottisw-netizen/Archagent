"""The authority profile schema and its YAML loader (spec §4).

An authority profile is data, not code: which departments a municipality
uses, what its jargon means, which documents it typically asks for and at
what stage, and a handful of project-sourced geometry examples. None of it is
a universal planning rule - every number here must trace back to an actual
project/authority document, which is why :class:`Authority` keeps
``geometry_examples`` and ``evidence_requirements`` as plain dicts rather than
:class:`~archagent.models.Constraint` objects: turning one into an enforced
constraint is a decision for the code that consumes the profile, not for the
profile itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Authority:
    name: str
    display_name: str = ""
    language: str = "he"
    rtl: bool = True
    departments: list[str] = field(default_factory=list)
    #: department -> canonical Archagent discipline (routing)
    disciplines: dict[str, str] = field(default_factory=dict)
    #: Hebrew/English term -> short canonical gloss
    terminology: dict[str, str] = field(default_factory=dict)
    #: surface forms the deterministic parser should recognise
    comment_patterns: list[str] = field(default_factory=list)
    stages: list[str] = field(default_factory=list)
    stage_examples: list[dict] = field(default_factory=list)
    evidence_requirements: list[dict] = field(default_factory=list)
    geometry_examples: list[dict] = field(default_factory=list)
    source_dir: Path | None = None

    def discipline_for(self, department: str) -> str:
        return self.disciplines.get(department, department)

    def evidence_for(self, evidence_type: str) -> dict | None:
        return next((item for item in self.evidence_requirements
                    if item.get("type") == evidence_type), None)

    def matches_pattern(self, text: str) -> list[str]:
        """Which of this authority's known comment patterns appear in text."""
        return [pattern for pattern in self.comment_patterns if pattern in text]


def load_authority(directory: str | Path) -> Authority:
    """Load one authority profile from its YAML pack (spec §4 file layout).

    Needs PyYAML - the only place in the codebase that does, and only when a
    profile is actually loaded from disk: ``pip install archagent[authority]``.
    A missing optional file in the pack is not an error; it just leaves that
    part of the profile empty.
    """
    try:
        import yaml
    except ImportError as error:
        raise ImportError(
            "loading an authority profile from YAML needs PyYAML: "
            "pip install archagent[authority]") from error

    directory = Path(directory)
    if not directory.is_dir():
        raise FileNotFoundError(f"no authority profile directory at {directory}")

    def _read(name: str):
        path = directory / name
        if not path.exists():
            return None
        return yaml.safe_load(path.read_text(encoding="utf-8"))

    authority_doc = _read("authority.yaml") or {}
    disciplines_doc = _read("disciplines.yaml") or {}
    terminology_doc = _read("terminology.yaml") or {}
    patterns_doc = _read("comment_patterns.yaml") or []
    stages_doc = _read("stages.yaml") or {}
    evidence_doc = _read("evidence_requirements.yaml") or []
    geometry_doc = _read("geometry_rules.yaml") or []

    return Authority(
        name=authority_doc.get("authority", directory.name),
        display_name=authority_doc.get("display_name", ""),
        language=authority_doc.get("language", "he"),
        rtl=authority_doc.get("rtl", True),
        departments=list(authority_doc.get("departments", [])),
        disciplines=dict(disciplines_doc or {}),
        terminology=dict(terminology_doc or {}),
        comment_patterns=list(patterns_doc or []),
        stages=list(stages_doc.get("stages", [])),
        stage_examples=list(stages_doc.get("examples", [])),
        evidence_requirements=list(evidence_doc or []),
        geometry_examples=list(geometry_doc or []),
        source_dir=directory,
    )
