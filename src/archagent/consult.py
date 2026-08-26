"""Step 9 - user consultation (SKILL.md 10).

The consultation agent renders the question exactly as 10 specifies - comment,
what was found, proposed correction, consequences, alternatives,
recommendation - and records the answer as a :class:`Decision`.

Responders decide how the answer arrives: interactively, from a scripted file,
or automatically in autonomous mode.  A responder never sees the model; it can
only approve, reject, modify or pick an alternative.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import units
from .models import Decision, MunicipalComment, CorrectionPlan, ElementMapping, new_id
from .simulate import SimulationResult


@dataclass
class Question:
    comment: MunicipalComment
    plan: CorrectionPlan
    mapping: ElementMapping
    simulation: SimulationResult | None = None
    options: list[str] = field(default_factory=list)
    recommended: str = "A"

    def render(self) -> str:
        lines = [f"## Consultation - {self.comment.comment_id} ({self.comment.department})", ""]
        lines += ["### The municipal comment", "", "```text", self.comment.original_text.strip(), "```", ""]
        lines += ["### What was found", "", "```text", "Affected elements:"]
        for element_id in self.mapping.selected or ["(none identified)"]:
            lines.append(f"- {element_id}")
        lines += ["```", "", "### Proposed correction", "", "```text", self.plan.strategy, "```", ""]
        lines += ["### Consequences", "", "```text"]
        consequences = self.consequences()
        lines += consequences or ["- no secondary effect detected"]
        lines += ["```", ""]
        if self.plan.alternatives:
            lines += ["### Alternatives", ""]
            for index, alternative in enumerate(self.plan.alternatives, start=2):
                letter = chr(ord("A") + index - 1)
                lines.append(f"{letter}. {alternative['strategy']}")
            lines.append("")
        lines += ["### Recommendation", "",
                  f"Option {self.recommended}: {self.plan.strategy}",
                  f"Confidence: {self.plan.confidence.value:.0%} "
                  f"(limited by {self.plan.confidence.limiting_component})", ""]
        if self.plan.consultation_reasons:
            lines += ["Asking because:", ""]
            lines += [f"- {reason}" for reason in self.plan.consultation_reasons]
            lines.append("")
        lines += ["Answer with: approve | reject | alternative:<letter> | modify:<instruction>", ""]
        return "\n".join(lines)

    def consequences(self) -> list[str]:
        lines = []
        for effect in self.plan.expected_effects:
            verdict = "still compliant" if effect.still_compliant else "NO LONGER COMPLIANT"
            lines.append(
                f"- {effect.element} {effect.property}: "
                f"{units.format_value(effect.from_value or 0.0)} -> "
                f"{units.format_value(effect.to_value or 0.0)} ({verdict}, {effect.constraint_id})")
        if self.simulation:
            for violation in self.simulation.violations:
                lines.append(f"- unmet: {violation.constraint_id} {violation.rule}")
            for regression in self.simulation.regressions:
                lines.append(f"- regression: {regression['constraint_id']} {regression['rule']}")
        return lines

    def option_letters(self) -> list[str]:
        return [chr(ord("A") + index) for index in range(1 + len(self.plan.alternatives))]


Responder = Callable[[Question], str]


def auto_approve(question: Question) -> str:
    return "approve"


def defer(question: Question) -> str:
    return "question"


def cli_responder(question: Question) -> str:  # pragma: no cover - interactive
    print(question.render())
    try:
        answer = input("> ").strip()
    except EOFError:
        return "question"
    return answer or "question"


class ScriptedResponder:
    """Answers from a JSON file: ``{"C-001": "approve", "C-002": "alternative:B"}``.

    Comments without an entry are deferred, so a scripted run can never
    silently approve something the script did not mention.
    """

    def __init__(self, answers: dict[str, str]):
        self.answers = answers

    @classmethod
    def from_file(cls, path) -> "ScriptedResponder":
        return cls(json.loads(Path(path).read_text(encoding="utf-8")))

    def __call__(self, question: Question) -> str:
        return self.answers.get(question.comment.comment_id, "question")


class ConsultationAgent:
    def __init__(self, responder: Responder | None = None):
        self.responder = responder or defer
        self.transcript: list[dict] = []

    def consult(self, comment: MunicipalComment, plan: CorrectionPlan, mapping: ElementMapping,
                simulation: SimulationResult | None = None) -> Decision:
        question = Question(comment=comment, plan=plan, mapping=mapping, simulation=simulation,
                            options=[plan.strategy] + [a["strategy"] for a in plan.alternatives])
        question.options = question.options or [plan.strategy]
        answer = (self.responder(question) or "question").strip()
        decision = Decision(
            decision_id=new_id("D"),
            plan_id=plan.plan_id,
            presented_options=question.option_letters(),
            recommended=question.recommended,
            user_choice=answer,
        )
        if answer.startswith("modify:"):
            decision.user_note = answer.split(":", 1)[1].strip()
        self.transcript.append({"question": question.render(), "answer": answer})
        return decision


def apply_decision(decision: Decision, plan: CorrectionPlan) -> tuple[str, CorrectionPlan]:
    """Return ``(outcome, plan)`` where outcome is approve/reject/question/modify.

    Choosing an alternative rewrites the plan's strategy but never bypasses
    re-simulation: the caller re-plans and re-validates (SKILL.md 10.1).
    """
    choice = decision.user_choice.strip().casefold()
    if choice in ("approve", "approved", "yes", "y", "a"):
        return "approve", plan
    if choice in ("reject", "no", "n"):
        plan.status = "rejected"
        return "reject", plan
    if choice.startswith("alternative:"):
        letter = choice.split(":", 1)[1].strip().upper()
        index = ord(letter) - ord("A") - 1
        if 0 <= index < len(plan.alternatives):
            decision.resulting_plan_id = f"{plan.plan_id}-alt{letter}"
            return "alternative", plan
        plan.notes.append(f"unknown alternative {letter!r}")
        return "question", plan
    if choice.startswith("modify:"):
        return "modify", plan
    return "question", plan
