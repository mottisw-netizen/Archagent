"""Structured data schemas.

Direct implementation of the JSON objects specified in SKILL.md: the project
context (5.1), municipal comments (5.2), constraints (8), element mappings
(7.1), correction plans (9), decisions (10.1), validation results (14.4) and
version manifests (16).
"""

from __future__ import annotations

import dataclasses
import enum
import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from . import units


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def sha256_file(path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _plain(value: Any) -> Any:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        custom = getattr(type(value), "to_dict", None)
        if custom is not None and custom is not Serialisable.to_dict:
            return _plain(custom(value))
        return {field.name: _plain(getattr(value, field.name))
                for field in dataclasses.fields(value)}
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    return value


class Serialisable:
    def to_dict(self) -> dict:
        return _plain(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)


class Mode(str, enum.Enum):
    CONSULTATION = "consultation"
    AUTONOMOUS = "autonomous"


class Priority(str, enum.Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

    @property
    def rank(self) -> int:
        return {"critical": 0, "high": 1, "medium": 2, "low": 3}[self.value]

    def outranks(self, other: "Priority") -> bool:
        return self.rank < other.rank


class CommentStatus(str, enum.Enum):
    """Status vocabulary of SKILL.md 14.1."""

    RESOLVED = "Resolved"
    PARTIALLY_RESOLVED = "Partially resolved"
    ADDRESSED_NEEDS_CONFIRMATION = "Addressed - requires confirmation"
    NOT_RESOLVED = "Not resolved"
    REQUIRES_HUMAN_REVIEW = "Requires human review"
    NOT_APPLICABLE = "Not applicable"


class Resolution(str, enum.Enum):
    UNIQUE = "unique"
    SELECTED_BY_DISCRIMINATOR = "selected_by_discriminator"
    AMBIGUOUS = "ambiguous"
    NOT_FOUND = "not_found"


@dataclass
class InputFile(Serialisable):
    """Input manifest entry (SKILL.md 3.2)."""

    file: str
    role: str
    format: str
    sha256: str = ""
    pages: int = 0
    read_status: str = "ok"
    notes: str = ""


@dataclass
class Measurement(Serialisable):
    """A value produced by a measurement tool, never by estimation."""

    metric: str
    value: float
    unit: str = units.DEFAULT_UNIT
    basis: str = "clear"
    tool: str = ""
    subject: dict = field(default_factory=dict)
    details: dict = field(default_factory=dict)

    def formatted(self, op: str | None = None) -> str:
        return units.format_value(self.value, self.unit, op)


def describe_selector(selector: dict) -> str:
    """Render an element selector as a short human phrase."""
    if not selector:
        return "the project"
    parts = [f"{key}={value}" for key, value in selector.items()]
    return " ".join(parts)


@dataclass
class Requirement(Serialisable):
    """A testable restatement of a comment or a rule (SKILL.md 5.2, 8)."""

    subject: dict
    metric: str
    op: str
    value: float
    unit: str = units.DEFAULT_UNIT
    basis: str = "clear"

    def describe(self) -> str:
        subject = (
            self.subject.get("label")
            or self.subject.get("element_id")
            or describe_selector(self.subject.get("selector", {}))
        )
        edge = self.subject.get("edge")
        subject = f"{subject} ({edge})" if edge else subject
        return f"{subject} {self.metric} {self.op} {units.format_value(self.value, self.unit)}"

    def describe_in(self, messages) -> str:
        """The same requirement, phrased in the report's language."""
        selector = self.subject.get("selector") or {}
        subject = self.subject.get("label") or self.subject.get("element_id")
        if not subject or subject in selector.values():
            subject = subject or ""
        if selector.get("counts_as_floor_area"):
            subject = messages.t("etype.project")
        elif subject and (subject == selector.get("type")
                          or messages.knows(f"etype.{subject}")):
            subject = messages.element_type(subject)
        elif not subject:
            subject = (messages.element_type(selector["type"]) if selector.get("type")
                       else describe_selector(selector))
        metric = messages.metric(self.metric)
        edge = self.subject.get("edge")
        if edge:
            metric = f"{metric} {messages.edge(edge)}"
        return messages.t("requirement_line", subject=subject, metric=metric,
                          op=self.op, value=messages.value(self.value, self.unit))


@dataclass
class Confidence(Serialisable):
    """Component confidence model (SKILL.md 20)."""

    extraction: float = 1.0
    interpretation: float = 1.0
    identification: float = 1.0
    solution: float = 1.0
    verification: float = 1.0

    COMPONENTS = ("extraction", "interpretation", "identification", "solution", "verification")

    @property
    def value(self) -> float:
        return min(getattr(self, name) for name in self.COMPONENTS)

    @property
    def limiting_component(self) -> str:
        return min(self.COMPONENTS, key=lambda name: getattr(self, name))

    @property
    def band(self) -> str:
        value = self.value
        if value >= 0.95:
            return "deterministic"
        if value >= 0.85:
            return "high"
        if value >= 0.60:
            return "medium"
        return "low"

    def with_(self, **components: float) -> "Confidence":
        data = {name: getattr(self, name) for name in self.COMPONENTS}
        data.update({k: v for k, v in components.items() if v is not None})
        return Confidence(**data)

    def to_dict(self) -> dict:
        data = {name: round(getattr(self, name), 3) for name in self.COMPONENTS}
        data["value"] = round(self.value, 3)
        data["band"] = self.band
        data["limiting_component"] = self.limiting_component
        return data


@dataclass
class MunicipalComment(Serialisable):
    """SKILL.md 5.2."""

    comment_id: str
    department: str
    original_text: str
    normalized_requirement: str = ""
    requirement: Requirement | None = None
    affected_discipline: str = "architecture"
    affected_elements: list[str] = field(default_factory=list)
    required_action: str = ""
    confidence: Confidence = field(default_factory=Confidence)
    source_ref: str = ""
    language: str = ""
    #: One-line restatement in the comment's own language, for the report.
    summary: str = ""
    #: Where the interpretation came from: llm+rules | llm | rules | none
    interpretation_source: str = "rules"
    parse_notes: list[str] = field(default_factory=list)
    conflicts_with: list[str] = field(default_factory=list)


@dataclass
class Constraint(Serialisable):
    """SKILL.md 8."""

    constraint_id: str
    source: str
    rule: str
    priority: Priority = Priority.HIGH
    test: Requirement | None = None
    source_ref: str = ""
    affected_elements: list[str] = field(default_factory=list)
    confidence: float = 1.0
    origin_comment_id: str = ""
    implicit: bool = False


@dataclass
class Candidate(Serialisable):
    element_id: str
    match_basis: list[str] = field(default_factory=list)
    confidence: float = 0.0


@dataclass
class ElementMapping(Serialisable):
    """SKILL.md 7.1."""

    comment_id: str
    candidates: list[Candidate] = field(default_factory=list)
    selected: list[str] = field(default_factory=list)
    resolution: Resolution = Resolution.NOT_FOUND
    before: dict = field(default_factory=dict)
    notes: str = ""


@dataclass
class Action(Serialisable):
    """One step of a correction plan (SKILL.md 9)."""

    action: str
    element: str
    parameter: str = ""
    value: Any = None
    from_value: Any = None
    to_value: Any = None
    distance: float | None = None
    direction: str = ""
    anchor: str = ""
    text: str = ""

    def describe(self) -> str:
        if self.action in ("resize", "set_property") and self.parameter:
            return f"{self.action} {self.element}.{self.parameter}: {self.from_value} -> {self.to_value}"
        if self.action == "move":
            return f"move {self.element} {self.distance}m {self.direction}"
        return f"{self.action} {self.element}"


@dataclass
class ExpectedEffect(Serialisable):
    element: str
    property: str
    from_value: float | None = None
    to_value: float | None = None
    constraint_id: str = ""
    still_compliant: bool = True


@dataclass
class Precondition(Serialisable):
    element: str
    property: str
    expected: Any


@dataclass
class CorrectionPlan(Serialisable):
    """SKILL.md 9."""

    plan_id: str
    comment_ids: list[str]
    strategy: str = ""
    preconditions: list[Precondition] = field(default_factory=list)
    plan: list[Action] = field(default_factory=list)
    expected_effects: list[ExpectedEffect] = field(default_factory=list)
    alternatives: list[dict] = field(default_factory=list)
    rollback: str = ""
    risk: str = "low"
    confidence: Confidence = field(default_factory=Confidence)
    requires_consultation: bool = False
    consultation_reasons: list[str] = field(default_factory=list)
    deterministic: bool = False
    status: str = "proposed"
    notes: list[str] = field(default_factory=list)


@dataclass
class ChangeRecord(Serialisable):
    """Returned by every mutating tool (SKILL.md 12.1)."""

    element_id: str
    property: str
    before: Any
    after: Any
    plan_id: str = ""
    comment_id: str = ""
    tool: str = ""
    sheet: str = ""
    kind: str = "modified"  # modified | created | removed | schedule


@dataclass
class Decision(Serialisable):
    """SKILL.md 10.1."""

    decision_id: str
    plan_id: str
    presented_options: list[str] = field(default_factory=list)
    recommended: str = ""
    user_choice: str = ""
    user_note: str = ""
    decided_at: str = field(default_factory=now)
    resulting_plan_id: str = ""


@dataclass
class CommentValidation(Serialisable):
    comment_id: str
    status: CommentStatus
    evidence: dict = field(default_factory=dict)
    note: str = ""


@dataclass
class ConstraintValidation(Serialisable):
    constraint_id: str
    status: str  # pass | fail | not_evaluated
    priority: Priority = Priority.HIGH
    rule: str = ""
    measured: float | None = None
    required: float | None = None
    unit: str = units.DEFAULT_UNIT
    op: str = ">="
    at_limit: bool = False
    note: str = ""


@dataclass
class ValidationResult(Serialisable):
    """SKILL.md 14.4."""

    version: str
    comments: list[CommentValidation] = field(default_factory=list)
    constraints: list[ConstraintValidation] = field(default_factory=list)
    drawing_checks: list[dict] = field(default_factory=list)
    regressions: list[dict] = field(default_factory=list)
    result: str = "passed"

    @property
    def passed(self) -> bool:
        return self.result != "failed"


@dataclass
class VersionManifest(Serialisable):
    """SKILL.md 16."""

    version: str
    parent_version: str
    changes: list[ChangeRecord] = field(default_factory=list)
    timestamp: str = field(default_factory=now)
    validation_result: str = "not_evaluated"
    run_id: str = ""
    operating_mode: str = Mode.CONSULTATION.value
    source_sha256: str = ""
    output_sha256: str = ""
    comment_ids: list[str] = field(default_factory=list)
    decisions: list[str] = field(default_factory=list)
    created_by: str = "municipal-permit-review v1.0"


@dataclass
class ProjectContext(Serialisable):
    """SKILL.md 5.1."""

    project_id: str
    run_id: str
    source_format: str = "JSON"
    input_manifest: list[InputFile] = field(default_factory=list)
    municipal_comments: list[MunicipalComment] = field(default_factory=list)
    planning_constraints: list[Constraint] = field(default_factory=list)
    drawing_elements: list[dict] = field(default_factory=list)
    mappings: list[ElementMapping] = field(default_factory=list)
    plans: list[CorrectionPlan] = field(default_factory=list)
    decisions: list[Decision] = field(default_factory=list)
    operating_mode: str = Mode.CONSULTATION.value
    execution_mode: str = "applied"  # applied | markup_only
    confidence_threshold: float = 0.85
    units: str = units.DEFAULT_UNIT
    created_at: str = field(default_factory=now)
    open_items: list[dict] = field(default_factory=list)
    #: Every source of the package and the adapter that opened it (or did not).
    sources: list[dict] = field(default_factory=list)
    #: Which adapter each comment was routed to, and why.
    routing: list[dict] = field(default_factory=list)

    def comment(self, comment_id: str) -> MunicipalComment | None:
        return next((c for c in self.municipal_comments if c.comment_id == comment_id), None)

    def mapping(self, comment_id: str) -> ElementMapping | None:
        return next((m for m in self.mappings if m.comment_id == comment_id), None)

    def constraint(self, constraint_id: str) -> Constraint | None:
        return next((c for c in self.planning_constraints if c.constraint_id == constraint_id), None)

    def add_open_item(self, ref: str, why: str, needed: str) -> None:
        item = {"ref": ref, "why": why, "needed": needed}
        if item not in self.open_items:
            self.open_items.append(item)
