"""Claude writes the report's opening paragraph (SKILL.md 15).

The tables in the report are the record; this is the sentence an architect
reads first. Claude is given only facts already established by measurement -
statuses, applied changes with their before/after values, open items - and is
told plainly that it may not introduce a number that is not in front of it.
"""

from __future__ import annotations

from .client import LLMClient, LLMError

SCHEMA: dict = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "attention": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["summary", "attention"],
    "additionalProperties": False,
}

SYSTEM = """\
You write the opening paragraph of a municipal permit correction report for the \
architect responsible for the submission.

Write in the language named in the request - Hebrew reports are read by Israeli \
architects and must read naturally, not like a translation.

Rules:
- Use only the facts given to you. Never introduce a number, a dimension, a \
comment or a conclusion that is not in the material below.
- Do not claim a comment is resolved unless its status says so.
- 2-4 sentences: what was corrected, what still needs the architect, and any \
result the architect would want to know before opening the drawings.
- `attention` is a short list (0-3 entries) of the items that most need a human \
decision, phrased as actions.
- No greetings, no marketing, no advice about how good the tool is.
"""


class RunSummariser:
    def __init__(self, client: LLMClient, effort: str | None = None):
        self.client = client
        self.effort = effort

    def summarise(self, language: str, facts: str) -> tuple[str, list[str]]:
        prompt = f"language: {language}\n\n{facts}"
        try:
            response = self.client.complete_json(SYSTEM, prompt, SCHEMA, self.effort or "low")
        except LLMError:
            return "", []
        summary = (response.data.get("summary") or "").strip()
        attention = [str(item).strip() for item in response.data.get("attention", []) if item]
        return summary, attention[:3]


def facts_for(context, validation, changes, messages) -> str:
    """The material the summary may draw on - and nothing else."""
    lines = ["<statuses>"]
    for item in validation.comments:
        comment = context.comment(item.comment_id)
        text = (comment.original_text.strip() if comment else "")[:160]
        lines.append(f"- {item.comment_id} [{messages.status(item.status)}] {text}")
    lines += ["</statuses>", "", "<applied_changes>"]
    for change in changes:
        lines.append(f"- {change.comment_id}: {change.element_id} {change.property} "
                     f"{change.before} -> {change.after}")
    if not changes:
        lines.append("- none")
    lines += ["</applied_changes>", "", "<open_items>"]
    for item in context.open_items:
        lines.append(f"- {item['ref']}: {item['why']} | needed: {item['needed']}")
    if not context.open_items:
        lines.append("- none")
    lines += ["</open_items>", "",
              f"<validation_result>{validation.result}</validation_result>",
              f"<mode>{context.operating_mode}</mode>",
              f"<execution>{context.execution_mode}</execution>"]
    failures = [c for c in validation.constraints if c.status == "fail"]
    if failures:
        lines += ["", "<failing_constraints>"]
        lines += [f"- {c.constraint_id} ({c.priority.value}): {c.rule} | measured {c.measured}"
                  for c in failures]
        lines.append("</failing_constraints>")
    return "\n".join(lines)
