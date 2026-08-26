"""Claude resolves which element a comment points at (SKILL.md 7.1).

When several elements match and the comment names no discriminator, the rules
must escalate.  Claude often can tell from the wording ("the visitor space",
"the space nearest the entrance") - so it is asked, with the candidates and
their properties in front of it.

Two guarantees hold whatever the model answers: it may only return one of the
candidate ids it was given, and its pick is never treated as certain - the
mapping is recorded as chosen by the model, with its reasoning, and a
confidence that keeps a borderline case in front of a human.
"""

from __future__ import annotations

from dataclasses import dataclass

from .client import LLMClient, LLMError

#: A model pick never scores higher than this - it is a judgement, not a match.
MAX_CONFIDENCE = 0.9

SCHEMA: dict = {
    "type": "object",
    "properties": {
        "selected": {"type": ["string", "null"]},
        "confidence": {"type": "number"},
        "reasoning": {"type": "string"},
    },
    "required": ["selected", "confidence", "reasoning"],
    "additionalProperties": False,
}

SYSTEM = """\
You decide which element of an architectural drawing a municipal permit comment \
refers to, when more than one element matches.

You are given the comment verbatim (often in Hebrew), the requirement extracted \
from it, and the candidate elements with their marks, types and properties. \
Choose the one the comment means.

Rules:
- `selected` must be exactly one of the candidate ids given to you, or null.
- Return null whenever the comment genuinely does not distinguish between the \
candidates. A null answer sends the comment to a human, which is the correct \
outcome - a wrong pick edits the wrong part of a building.
- Do not use size to choose unless the comment states a size that identifies one \
candidate; the current dimensions shown are context, not evidence of intent.
- `confidence` is how sure you are of the choice: 0.9 when the comment names \
something only one candidate has, 0.5-0.7 when you are inferring from context, \
below 0.5 when you are guessing (prefer null instead).
- `reasoning` is one sentence, in the language of the comment, that an architect \
can check.
"""


@dataclass
class Choice:
    element_id: str | None = None
    confidence: float = 0.0
    reasoning: str = ""
    error: str = ""

    @property
    def resolved(self) -> bool:
        return bool(self.element_id)


class ElementDisambiguator:
    def __init__(self, client: LLMClient, effort: str | None = None):
        self.client = client
        self.effort = effort
        self.calls = 0

    def choose(self, comment_text: str, requirement_text: str,
               candidates: list[dict]) -> Choice:
        ids = [candidate["id"] for candidate in candidates]
        if len(ids) < 2:
            return Choice(error="nothing to disambiguate")
        prompt = self._prompt(comment_text, requirement_text, candidates)
        try:
            response = self.client.complete_json(SYSTEM, prompt, SCHEMA, self.effort)
        except LLMError as error:
            return Choice(error=str(error))
        self.calls += 1
        data = response.data
        selected = data.get("selected")
        if selected is not None and selected not in ids:
            return Choice(error=f"the model returned an element that was not offered: "
                                f"{selected!r}")
        confidence = min(MAX_CONFIDENCE, max(0.0, float(data.get("confidence") or 0.0)))
        return Choice(element_id=selected, confidence=confidence,
                      reasoning=(data.get("reasoning") or "").strip())

    @staticmethod
    def _prompt(comment_text: str, requirement_text: str, candidates: list[dict]) -> str:
        lines = ["<comment>", comment_text.strip(), "</comment>", "",
                 f"<requirement>{requirement_text}</requirement>", "", "<candidates>"]
        for candidate in candidates:
            properties = {key: value for key, value in (candidate.get("properties") or {}).items()
                          if key not in ("width_axis", "length_axis", "anchor")}
            lines.append(
                f"- id: {candidate['id']} | mark: {candidate.get('label', '')} | "
                f"type: {candidate.get('type', '')} | level: {candidate.get('level', '')} | "
                f"sheet: {candidate.get('sheet', '')} | properties: {properties}")
        lines.append("</candidates>")
        return "\n".join(lines)
