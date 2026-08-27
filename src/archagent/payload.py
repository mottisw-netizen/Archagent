"""A machine-readable summary of a finished run.

Written to ``run_payload.json`` beside the report, so any driver - the web
application, Claude Code, CI - can render a run without re-deriving it from the
markdown.
"""

from __future__ import annotations

from pathlib import Path

from .lang.messages import DEFAULT as DEFAULT_MESSAGES, Messages
from .models import CommentStatus

STATUS_TONE = {
    CommentStatus.RESOLVED: "good",
    CommentStatus.PARTIALLY_RESOLVED: "warn",
    CommentStatus.ADDRESSED_NEEDS_CONFIRMATION: "warn",
    CommentStatus.NOT_RESOLVED: "bad",
    CommentStatus.REQUIRES_HUMAN_REVIEW: "bad",
    CommentStatus.NOT_APPLICABLE: "muted",
}


def run_payload(result, messages: Messages | None = None) -> dict:
    """Everything a viewer needs, already localised."""
    messages = messages or DEFAULT_MESSAGES
    context = result.context
    validation = result.validation
    statuses = {item.comment_id: item for item in validation.comments}
    plans = {}
    for plan in result.plans:
        for comment_id in plan.comment_ids:
            plans.setdefault(comment_id, plan)
    changes: dict[str, list] = {}
    for change in result.changes:
        changes.setdefault(change.comment_id, []).append({
            "element": change.element_id, "property": change.property,
            "before": _short(change.before), "after": _short(change.after),
            "sheet": change.sheet, "tool": change.tool,
        })

    comments = []
    for comment in context.municipal_comments:
        item = statuses.get(comment.comment_id)
        plan = plans.get(comment.comment_id)
        evidence = item.evidence if item else {}
        comments.append({
            "id": comment.comment_id,
            "department": messages.department(comment.department),
            "text": comment.original_text.strip(),
            "summary": comment.summary or (comment.requirement.describe_in(messages)
                                           if comment.requirement else ""),
            "requirement": comment.normalized_requirement,
            "requirement_type": comment.requirement_type.value if comment.requirement_type else "",
            "requirement_type_label": messages.requirement_type(comment.requirement_type),
            "discipline": comment.affected_discipline,
            "source": comment.interpretation_source,
            "status": messages.status(item.status) if item else "",
            "status_key": item.status.value if item else "",
            "tone": STATUS_TONE.get(item.status, "muted") if item else "muted",
            "confidence": round((plan.confidence if plan else comment.confidence).value, 3),
            "limiting": messages.component(
                (plan.confidence if plan else comment.confidence).limiting_component),
            "note": item.note if item else "",
            "evidence": {
                "measured": messages.value(evidence["measured"], evidence["unit"],
                                           evidence["op"]),
                "required": messages.value(evidence["required"], evidence["unit"]),
                "op": evidence["op"], "tool": evidence["tool"], "basis": evidence["basis"],
            } if evidence else None,
            "changes": changes.get(comment.comment_id, []),
            "triggers": plan.consultation_reasons if plan else [],
            "strategy": plan.strategy if plan else "",
            "notes": comment.parse_notes,
        })

    constraints = [{
        "id": item.constraint_id,
        "priority": messages.priority(item.priority),
        "priority_key": item.priority.value,
        "rule": item.rule,
        "required": messages.value(item.required, item.unit) if item.required is not None else "-",
        "measured": (messages.value(item.measured, item.unit, item.op)
                     if item.measured is not None else "-"),
        "op": item.op,
        "status": item.status,
        "status_label": messages.check_status(item.status),
        "at_limit": item.at_limit,
    } for item in validation.constraints]

    counts: dict[str, int] = {}
    for item in validation.comments:
        counts[messages.status(item.status)] = counts.get(messages.status(item.status), 0) + 1

    return {
        "language": result.language,
        "direction": messages.text_direction,
        "version": result.version,
        "parent_version": result.parent_version,
        "validation": validation.result,
        "validation_label": messages.result(validation.result),
        "mode": messages.mode(context.operating_mode),
        "execution": messages.execution(context.execution_mode),
        "counts": counts,
        "kpis": {
            "comments": len(validation.comments),
            "resolved": sum(1 for item in validation.comments
                            if item.status is CommentStatus.RESOLVED),
            "changes": len(result.changes),
            "open_items": len(context.open_items),
            "consulted": len(result.consulted),
        },
        "comments": comments,
        "constraints": constraints,
        "checks": [{"check": messages.check(check["check"]),
                    "status": check["status"],
                    "status_label": messages.check_status(check["status"]),
                    "details": check["details"]}
                   for check in validation.drawing_checks],
        "open_items": context.open_items,
        "definition_of_done": [{"text": text, "ok": ok}
                               for text, ok in result.definition_of_done],
        "decisions": [decision.to_dict() for decision in result.decisions],
        "llm": result.llm,
        "files": {name: Path(path).name for name, path in result.files.items()},
        "paths": result.files,
        "impact": result.impact,
        # The change set travels with the payload so a viewer can highlight the
        # diff without reading a second file.
        "change_set": result.change_set,
    }


def _short(value) -> str:
    if isinstance(value, float):
        return f"{value:.2f}"
    if isinstance(value, dict):
        keys = ("x", "y", "w", "h")
        if all(key in value for key in keys):
            return "(" + ", ".join(f"{value[key]:.2f}" for key in keys) + ")"
        return "…"
    if isinstance(value, list):
        return f"{len(value)}"
    return str(value)
