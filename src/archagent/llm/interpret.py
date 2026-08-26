"""Claude reads the municipal comment (SKILL.md 5.2).

This is the interpretation layer: Claude decides what a comment *means* - which
department it belongs to, which element it points at, what has to become true -
and returns it as a validated object.  It never returns a measurement: the
value it reports is the value the comment demands, and everything about the
drawing's current state is measured by the driver afterwards.

Anything the model returns is validated against the vocabulary the drawing
layer can actually measure.  A requirement naming a metric no element supports
is rejected rather than half-executed.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..models import Requirement
from .client import LLMClient, LLMError

#: Metrics the drawing drivers can measure (SKILL.md 12.1).
METRICS = ("width", "length", "height", "area", "floor_area", "count",
           "setback", "clear_width", "clear_distance")
UNITS = ("m", "cm", "mm", "m2", "count")
OPS = (">=", "<=", "==")
EDGES = ("north", "south", "east", "west", "none")
ANNOTATIONS = ("update_text", "update_dimension", "update_schedule")
DEPARTMENTS = ("Planning", "Architecture", "Licensing", "Traffic", "Parking",
               "Accessibility", "Fire Safety", "Sanitation", "Water", "Drainage",
               "Landscaping", "Environment", "Infrastructure", "Engineering", "Unknown")

SCHEMA: dict = {
    "type": "object",
    "properties": {
        "language": {"type": "string", "enum": ["he", "en", "ar", "other"]},
        "department": {"type": "string", "enum": list(DEPARTMENTS)},
        "kind": {"type": "string",
                 "enum": ["measurable", "annotation", "statement", "unclear"]},
        "summary": {"type": "string"},
        "requirement": {
            "type": ["object", "null"],
            "properties": {
                "metric": {"type": "string", "enum": list(METRICS)},
                "op": {"type": "string", "enum": list(OPS)},
                "value": {"type": "number"},
                "unit": {"type": "string", "enum": list(UNITS)},
                "subject_kind": {"type": "string",
                                 "enum": ["element_label", "element_type", "project"]},
                "subject_label": {"type": ["string", "null"]},
                "subject_type": {"type": ["string", "null"]},
                "edge": {"type": "string", "enum": list(EDGES)},
            },
            "required": ["metric", "op", "value", "unit", "subject_kind",
                         "subject_label", "subject_type", "edge"],
            "additionalProperties": False,
        },
        "annotation_action": {"type": ["string", "null"]},
        "ambiguities": {"type": "array", "items": {"type": "string"}},
        "confidence": {
            "type": "object",
            "properties": {
                "extraction": {"type": "number"},
                "interpretation": {"type": "number"},
            },
            "required": ["extraction", "interpretation"],
            "additionalProperties": False,
        },
        "reasoning": {"type": "string"},
    },
    "required": ["language", "department", "kind", "summary", "requirement",
                 "annotation_action", "ambiguities", "confidence", "reasoning"],
    "additionalProperties": False,
}

SYSTEM = """\
You read municipal building-permit comments and restate each one as a single \
testable requirement about an architectural drawing. Your output is consumed by \
software that will measure the drawing and then edit it, so precision matters \
more than helpfulness.

The comments are usually Hebrew (Israeli planning committees) and sometimes \
English. Read the comment in its own language. Never translate the comment \
itself; the `summary` you write must be in the same language as the comment, \
because an architect reads it in a report.

## What you must produce

`kind`:
- `measurable` - the comment demands a state that can be measured on the \
drawing (a dimension, a setback, a clear width, a count, an area). Fill in \
`requirement`.
- `annotation` - the comment asks to add, correct or update text, a dimension \
tag, a table or a schedule; nothing geometric changes. Fill in \
`annotation_action`.
- `statement` - the comment demands nothing ("נרשם", "לידיעה", "Noted").
- `unclear` - it demands something, but not something measurable, or you cannot \
tell what it demands ("לשפר את חזית הבניין"). Leave `requirement` null and say \
why in `ambiguities`.

`requirement` fields:
- `metric` - one of: width, length, height, area, floor_area, count, setback, \
clear_width, clear_distance.
  * `setback` = נסיגה / קו בניין - distance from a facade to the plot line. \
Always set `edge` for it.
  * `clear_width` = רוחב נטו / רוחב מעבר חופשי - the free width across \
something after obstructions.
  * `floor_area` = שטח בנייה / שטח בנוי - the project total, not one room.
  * `count` = a number of things (מקומות חניה).
- `op` - `>=` for a minimum (לפחות, לא יפחת מ-, at least), `<=` for a maximum \
(לא יעלה על, לכל היותר, at most), `==` only when an exact value is demanded.
  A verb alone tells you the direction: להגדיל/להרחיב → `>=`, \
להקטין/לצמצם/להצר → `<=`.
- `value` and `unit` - exactly the number the comment states, in the unit the \
comment states. מ' / מטר = m, ס"מ = cm, מ"מ = mm, מ"ר = m2. Do not convert. \
Read 1,850 as one thousand eight hundred fifty; read 2,50 as two and a half.
- `subject_kind`:
  * `element_label` when the comment names a specific element (P12, \
"מקום חניה מס' 12"). Put the mark in `subject_label`, matching the drawing \
inventory below when one of its entries clearly corresponds.
  * `element_type` when it names a class ("the parking spaces", "שביל הגישה"). \
Put the type in `subject_type`, using the vocabulary of the inventory.
  * `project` for floor_area or anything about the project as a whole.

## Rules

- Never invent a number, a mark or a rule that is not in the comment. If the \
comment states no value, it is not `measurable`.
- Never state what the drawing currently is. You are told nothing about \
current dimensions and must not guess them; software measures that.
- One comment demanding two independent things: describe the first in \
`requirement` and list the second in `ambiguities` so a human sees it.
- If several elements could match and the comment gives no discriminator, still \
fill in what you can, and say so in `ambiguities`.
- Departments: infer from the comment's content and the header it came under. \
Use `Unknown` rather than guessing.

## Confidence

- `extraction` - how sure you are that you read the text correctly (lower it \
for garbled OCR, truncation, missing context).
- `interpretation` - how sure you are that the requirement is what the \
department means. 0.95+ only when the comment is explicit and unambiguous. \
Use 0.5-0.7 when you had to infer the metric or the subject. Below 0.5 when \
you are guessing - a low number routes the comment to a human, which is the \
correct outcome. Never inflate it.
"""


@dataclass
class Interpretation:
    """What Claude made of one comment, after validation."""

    kind: str = "unclear"
    department: str = "Unknown"
    language: str = "en"
    summary: str = ""
    requirement: Requirement | None = None
    annotation_action: str = ""
    ambiguities: list[str] = field(default_factory=list)
    extraction: float = 1.0
    interpretation: float = 0.35
    reasoning: str = ""
    rejected: list[str] = field(default_factory=list)
    raw: dict = field(default_factory=dict)

    @property
    def usable(self) -> bool:
        return self.kind in ("measurable", "annotation", "statement") and not self.rejected


class LLMCommentInterpreter:
    """Turns comment text into a validated :class:`Interpretation`."""

    def __init__(self, client: LLMClient, inventory: list[dict] | None = None,
                 effort: str | None = None):
        self.client = client
        self.inventory = inventory or []
        self.effort = effort

    # ------------------------------------------------------------------
    def interpret(self, comment_id: str, text: str, department_hint: str = "",
                  source_ref: str = "") -> Interpretation:
        user = self._prompt(comment_id, text, department_hint, source_ref)
        response = self.client.complete_json(SYSTEM, user, SCHEMA, self.effort)
        return self.validate(response.data)

    def _prompt(self, comment_id: str, text: str, department_hint: str,
                source_ref: str) -> str:
        lines = ["<comment>", f"id: {comment_id}"]
        if department_hint:
            lines.append(f"heading it appeared under: {department_hint}")
        if source_ref:
            lines.append(f"source document: {source_ref}")
        lines += ["text (verbatim, do not translate):", text.strip(), "</comment>"]
        if self.inventory:
            lines += ["", "<drawing_inventory>",
                      "Elements present in the drawing. Use these marks and types when the "
                      "comment refers to one of them. Dimensions are deliberately not shown.",
                      self._inventory_text(), "</drawing_inventory>"]
        return "\n".join(lines)

    def _inventory_text(self) -> str:
        rows = []
        for element in self.inventory[:250]:
            mark = element.get("label") or element.get("id")
            rows.append(f"- {mark} ({element.get('type', 'unknown')})")
        return "\n".join(rows)

    # ------------------------------------------------------------------
    def validate(self, data: dict) -> Interpretation:
        """Accept only what the drawing layer can act on."""
        result = Interpretation(raw=data)
        result.kind = data.get("kind", "unclear")
        result.department = data.get("department", "Unknown")
        result.language = data.get("language", "en")
        result.summary = (data.get("summary") or "").strip()
        result.ambiguities = [str(item) for item in data.get("ambiguities", []) if item]
        result.reasoning = (data.get("reasoning") or "").strip()
        confidence = data.get("confidence") or {}
        result.extraction = _clamp(confidence.get("extraction", 1.0))
        result.interpretation = _clamp(confidence.get("interpretation", 0.35))

        action = data.get("annotation_action")
        if result.kind == "annotation":
            if action in ANNOTATIONS:
                result.annotation_action = action
            else:
                result.rejected.append(f"unknown annotation action: {action!r}")
                result.kind = "unclear"

        payload = data.get("requirement")
        if result.kind == "measurable":
            if not isinstance(payload, dict):
                result.rejected.append("kind is measurable but no requirement was returned")
                result.kind = "unclear"
            else:
                requirement, problems = self._requirement(payload)
                if problems:
                    result.rejected.extend(problems)
                    result.kind = "unclear"
                else:
                    result.requirement = requirement
        return result

    @staticmethod
    def _requirement(payload: dict) -> tuple[Requirement | None, list[str]]:
        problems: list[str] = []
        metric = payload.get("metric")
        op = payload.get("op")
        unit = payload.get("unit")
        value = payload.get("value")
        if metric not in METRICS:
            problems.append(f"unsupported metric: {metric!r}")
        if op not in OPS:
            problems.append(f"unsupported operator: {op!r}")
        if unit not in UNITS:
            problems.append(f"unsupported unit: {unit!r}")
        try:
            value = float(value)
        except (TypeError, ValueError):
            problems.append(f"value is not a number: {value!r}")
        else:
            if value != value or value in (float("inf"), float("-inf")) or value < 0:
                problems.append(f"value is out of range: {value!r}")
        if metric == "setback" and payload.get("edge") in (None, "none"):
            problems.append("a setback requirement must name an edge")
        if problems:
            return None, problems

        subject: dict = {}
        kind = payload.get("subject_kind")
        label = (payload.get("subject_label") or "").strip()
        element_type = (payload.get("subject_type") or "").strip()
        if metric == "floor_area" or kind == "project":
            subject = {"selector": {"counts_as_floor_area": True}, "label": "floor area"}
        elif kind == "element_label" and label:
            subject = {"selector": {"label": label}, "label": label}
            if element_type:
                subject["selector"]["type"] = element_type
        elif element_type:
            subject = {"selector": {"type": element_type}, "label": element_type}
        elif label:
            subject = {"selector": {"label": label}, "label": label}
        else:
            return None, ["the requirement names neither an element nor a type"]

        edge = payload.get("edge")
        if edge and edge != "none":
            subject["edge"] = edge
            if metric == "setback" and subject.get("selector", {}).get("type") == "building":
                subject = {"element_id": "building", "label": "building", "edge": edge}
        basis = "to plot line" if metric == "setback" else "clear"
        if unit == "count":
            unit = "count"
        return Requirement(subject=subject, metric=metric, op=op, value=float(value),
                           unit=unit, basis=basis), []


def _clamp(value, low: float = 0.0, high: float = 1.0) -> float:
    try:
        return max(low, min(high, float(value)))
    except (TypeError, ValueError):
        return low


def describe_disagreement(llm: Requirement, rule: Requirement) -> str:
    return (f"the model read it as {llm.describe()} and the rule parser as "
            f"{rule.describe()}")


def requirements_agree(first: Requirement, second: Requirement,
                       tolerance: float = 1e-6) -> bool:
    if first is None or second is None:
        return False
    if first.metric != second.metric or first.op != second.op:
        return False
    if first.unit != second.unit:
        return False
    if abs(first.value - second.value) > tolerance:
        return False
    return _subject_key(first) == _subject_key(second)


def _subject_key(requirement: Requirement) -> tuple:
    subject = requirement.subject
    selector = subject.get("selector") or {}
    return (
        subject.get("element_id", ""),
        str(selector.get("label", "")).casefold(),
        str(selector.get("type", "")).casefold(),
        subject.get("edge", ""),
    )


def inventory_from_driver(driver) -> list[dict]:
    """A compact element list for the prompt - marks and types only, no sizes."""
    elements = getattr(driver, "elements", None)
    if elements is None:
        return []
    return [{"id": element["id"], "label": element.get("label", ""),
             "type": element.get("type", "")}
            for element in elements()
            if element.get("type") not in ("dimension", "text")]


__all__ = ["ANNOTATIONS", "DEPARTMENTS", "Interpretation", "LLMCommentInterpreter",
           "METRICS", "OPS", "SCHEMA", "SYSTEM", "UNITS", "LLMError",
           "describe_disagreement", "inventory_from_driver", "requirements_agree"]
