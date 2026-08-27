"""Structured conditional requirements (spec §6/§27).

The municipal record contains conditions in prose - "if a municipal drainage
line crosses the plot, survey it, show it, and keep a 2 m setback; otherwise
do nothing" - that must become executable structured logic, not a comment the
agent re-reads as English every time. A :class:`Condition` evaluates against a
plain ``facts`` dict the caller supplies (from measured geometry, from
extracted evidence, from project metadata) - it never invents a fact that
was not given.

Example (the spec's own worked case, §6)::

    Condition(type="exists", subject="municipal_drainage_line_on_plot")

    ConditionalRequirement(
        requirement_id="REQ-1",
        condition=Condition(type="exists", subject="municipal_drainage_line_on_plot"),
        then_actions=["survey_line", "show_line", {"maintain_setback": "2.0m"}],
        else_actions=["no_action"],
    )
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .models import Serialisable

_COMPARISON_TYPES = {
    "equals": lambda a, b: a == b,
    "==": lambda a, b: a == b,
    "not_equals": lambda a, b: a != b,
    "!=": lambda a, b: a != b,
    "gt": lambda a, b: a is not None and a > b,
    ">": lambda a, b: a is not None and a > b,
    "gte": lambda a, b: a is not None and a >= b,
    ">=": lambda a, b: a is not None and a >= b,
    "lt": lambda a, b: a is not None and a < b,
    "<": lambda a, b: a is not None and a < b,
    "lte": lambda a, b: a is not None and a <= b,
    "<=": lambda a, b: a is not None and a <= b,
}


@dataclass
class Condition(Serialisable):
    type: str
    subject: str = ""
    value: Any = None
    conditions: list["Condition"] = field(default_factory=list)

    @classmethod
    def exists(cls, subject: str) -> "Condition":
        return cls(type="exists", subject=subject)

    @classmethod
    def not_exists(cls, subject: str) -> "Condition":
        return cls(type="not_exists", subject=subject)

    @classmethod
    def compare(cls, subject: str, op: str, value: Any) -> "Condition":
        if op not in _COMPARISON_TYPES:
            raise ValueError(f"unknown comparison operator: {op!r}")
        return cls(type=op, subject=subject, value=value)

    @classmethod
    def all_of(cls, *conditions: "Condition") -> "Condition":
        return cls(type="and", conditions=list(conditions))

    @classmethod
    def any_of(cls, *conditions: "Condition") -> "Condition":
        return cls(type="or", conditions=list(conditions))

    @classmethod
    def negate(cls, condition: "Condition") -> "Condition":
        return cls(type="not", conditions=[condition])

    @classmethod
    def from_dict(cls, data: dict) -> "Condition":
        return cls(
            type=data["type"],
            subject=data.get("subject", ""),
            value=data.get("value"),
            conditions=[cls.from_dict(item) for item in data.get("conditions", [])],
        )


def evaluate(condition: Condition, facts: dict) -> bool:
    """Never invents a fact: an absent key reads as falsy/``None``, not "unknown -> true"."""
    if condition.type == "exists":
        return bool(facts.get(condition.subject))
    if condition.type == "not_exists":
        return not bool(facts.get(condition.subject))
    if condition.type == "and":
        return all(evaluate(item, facts) for item in condition.conditions)
    if condition.type == "or":
        return any(evaluate(item, facts) for item in condition.conditions)
    if condition.type == "not":
        if len(condition.conditions) != 1:
            raise ValueError("'not' takes exactly one sub-condition")
        return not evaluate(condition.conditions[0], facts)
    comparator = _COMPARISON_TYPES.get(condition.type)
    if comparator is None:
        raise ValueError(f"unknown condition type: {condition.type!r}")
    return comparator(facts.get(condition.subject), condition.value)


Action = str | dict


@dataclass
class ConditionalRequirement(Serialisable):
    requirement_id: str
    condition: Condition
    then_actions: list[Action] = field(default_factory=list)
    else_actions: list[Action] = field(default_factory=list)
    source_comment_id: str = ""

    def resolve(self, facts: dict) -> list[Action]:
        return self.then_actions if evaluate(self.condition, facts) else self.else_actions

    @classmethod
    def from_dict(cls, data: dict) -> "ConditionalRequirement":
        return cls(
            requirement_id=data.get("requirement_id", ""),
            condition=Condition.from_dict(data["condition"]),
            then_actions=list(data.get("then", [])),
            else_actions=list(data.get("else", [])),
            source_comment_id=data.get("source_comment_id", ""),
        )
