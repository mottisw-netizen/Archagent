"""The correction report (SKILL.md 15) and the definition of done (23)."""

from __future__ import annotations

from . import units
from .models import (
    ChangeRecord,
    CommentStatus,
    CorrectionPlan,
    Decision,
    MunicipalComment,
    ProjectContext,
    ValidationResult,
)

STATUS_ORDER = [
    CommentStatus.RESOLVED,
    CommentStatus.PARTIALLY_RESOLVED,
    CommentStatus.ADDRESSED_NEEDS_CONFIRMATION,
    CommentStatus.NOT_RESOLVED,
    CommentStatus.REQUIRES_HUMAN_REVIEW,
    CommentStatus.NOT_APPLICABLE,
]


def _table(headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        rows = [["-"] * len(headers)]
    lines = ["| " + " | ".join(headers) + " |",
             "| " + " | ".join("---" for _ in headers) + " |"]
    lines += ["| " + " | ".join(str(cell) for cell in row) + " |" for row in rows]
    return "\n".join(lines)


def build_report(context: ProjectContext, validation: ValidationResult,
                 changes: list[ChangeRecord], plans: list[CorrectionPlan],
                 decisions: list[Decision], version: str, parent_version: str,
                 files: dict[str, str], definition_of_done: list[tuple[str, bool]],
                 consulted: set[str] | None = None) -> str:
    consulted = consulted or set()
    statuses = {item.comment_id: item for item in validation.comments}
    plans_by_comment: dict[str, CorrectionPlan] = {}
    for plan in plans:
        for comment_id in plan.comment_ids:
            plans_by_comment.setdefault(comment_id, plan)
    changes_by_comment: dict[str, list[ChangeRecord]] = {}
    for change in changes:
        changes_by_comment.setdefault(change.comment_id, []).append(change)

    resolved = [c for c in validation.comments if c.status is CommentStatus.RESOLVED]
    auto = [c for c in resolved if c.comment_id not in consulted]
    after_consultation = [c for c in resolved if c.comment_id in consulted]
    review = [c for c in validation.comments
              if c.status in (CommentStatus.REQUIRES_HUMAN_REVIEW, CommentStatus.NOT_RESOLVED)]

    unmet = [item for item in definition_of_done if not item[1]]
    lines: list[str] = ["# Municipal Correction Report", ""]
    if unmet:
        lines += ["> **This run is partial.** The following are not satisfied:", ">"]
        lines += [f"> - {text}" for text, _ok in unmet]
        lines.append("")
    if context.execution_mode == "markup_only":
        lines += ["> **Markup only.** No editable source model was supplied, so no drawing was "
                  "modified. The corrections below are instructions for a drafter.", ""]

    lines += [
        f"Project: {context.project_id}",
        f"Run: {context.run_id}",
        f"Source version: {parent_version} → {version}",
        f"Mode: {context.operating_mode}",
        f"Execution: {context.execution_mode}",
        f"Generated: {context.created_at}",
        "", "## Summary", "",
        f"Total municipal comments: {len(validation.comments)}", "",
        f"Resolved automatically: {len(auto)}",
        f"Resolved after user consultation: {len(after_consultation)}",
        f"Requires human review: {len(review)}",
        "",
    ]

    rows = []
    for comment in context.municipal_comments:
        item = statuses.get(comment.comment_id)
        plan = plans_by_comment.get(comment.comment_id)
        confidence = plan.confidence.value if plan else comment.confidence.value
        rows.append([comment.comment_id, comment.department,
                     item.status.value if item else "-", f"{confidence:.0%}"])
    lines += [_table(["Comment", "Department", "Status", "Confidence"], rows), ""]

    for comment in context.municipal_comments:
        lines += _comment_section(comment, statuses.get(comment.comment_id),
                                 plans_by_comment.get(comment.comment_id),
                                 changes_by_comment.get(comment.comment_id, []),
                                 [d for d in decisions
                                  if plans_by_comment.get(comment.comment_id)
                                  and d.plan_id.startswith(f"PLAN-{comment.comment_id}")])

    lines += ["---", "", "## Open items", ""]
    open_rows = [[item["ref"], item["why"], item["needed"]] for item in context.open_items]
    lines += [_table(["Ref", "Why it is open", "What is needed"], open_rows), ""]

    lines += ["## Constraint validation summary", ""]
    constraint_rows = []
    for item in validation.constraints:
        measured = (units.format_value(item.measured, item.unit, item.op)
                    if item.measured is not None else "-")
        required = (units.format_value(item.required, item.unit)
                    if item.required is not None else "-")
        status = item.status + (" (at the limit)" if item.at_limit else "")
        constraint_rows.append([item.constraint_id, item.priority.value.upper(), item.rule,
                                f"{item.op} {required}", measured, status])
    lines += [_table(["Constraint", "Priority", "Rule", "Required", "Measured", "Status"],
                     constraint_rows), ""]

    lines += ["## Drawing validation", ""]
    lines += [_table(["Check", "Status", "Details"],
                     [[check["check"], check["status"],
                       "; ".join(check["details"]) or "-"] for check in validation.drawing_checks]), ""]

    non_visual = [c for c in changes if c.kind == "schedule" or c.property in ("text", "value")]
    lines += ["## Non-visual changes", ""]
    if non_visual:
        lines += [f"- {c.element_id} {c.property} updated ({_short(c.before)} → {_short(c.after)})"
                  for c in non_visual]
    else:
        lines.append("- none")
    lines.append("")

    lines += ["## Versions", "",
              f"{parent_version} → {version}. Rollback: restore {parent_version}.",
              f"Validation result: {validation.result}.", ""]
    if files:
        lines += ["Artefacts:", ""]
        lines += [f"- {name}: `{path}`" for name, path in sorted(files.items())]
        lines.append("")

    lines += ["## Definition of done", ""]
    lines += [f"- [{'x' if ok else ' '}] {text}" for text, ok in definition_of_done]
    lines += ["", "## Sign-off", "",
              "This report and the accompanying drawings are an AI-generated proposal.",
              "They require review and approval by the responsible licensed professional",
              "before submission to the authority.", "",
              "Reviewed by: ______________________  Date: ____________", ""]
    return "\n".join(lines)


def _comment_section(comment: MunicipalComment, item, plan: CorrectionPlan | None,
                     changes: list[ChangeRecord], decisions: list[Decision]) -> list[str]:
    lines = ["---", "", f"## {comment.comment_id}", "",
             f"Department: {comment.department}", "",
             "Municipal comment:", f'"{comment.original_text.strip()}"', ""]
    lines += ["Interpretation:", comment.normalized_requirement or "(none extracted)", ""]
    if decisions:
        decision = decisions[-1]
        lines += ["User decision:", f"{decision.user_choice} ({decision.decision_id})", ""]
    if changes:
        lines.append("Correction:")
        for change in changes:
            lines.append(f"- {change.element_id} {change.property}: "
                         f"{_short(change.before)} → {_short(change.after)}")
        lines.append("")
        sheets = sorted({change.sheet for change in changes if change.sheet})
        lines += ["Affected drawings:", ", ".join(sheets) or "(not sheeted)", ""]
    elif plan and plan.status == "already_compliant":
        lines += ["Correction:", "None required - the model already satisfies the comment.", ""]
    else:
        lines += ["Correction:", "None applied.", ""]

    if plan and plan.expected_effects:
        lines.append("Planning impact:")
        for effect in plan.expected_effects:
            verdict = "still compliant" if effect.still_compliant else "NOT compliant"
            lines.append(f"- {effect.element} {effect.property}: "
                         f"{units.format_value(effect.from_value or 0.0)} → "
                         f"{units.format_value(effect.to_value or 0.0)} "
                         f"({verdict}, {effect.constraint_id})")
        lines.append("")
    elif changes:
        lines += ["Planning impact:", "None detected.", ""]

    lines.append("Validation:")
    if item is None:
        lines.append("Not evaluated.")
    else:
        evidence = item.evidence
        if evidence:
            lines.append(
                f"{item.status.value}. Measured "
                f"{units.format_value(evidence['measured'], evidence['unit'], evidence['op'])} "
                f"{evidence['op']} {units.format_value(evidence['required'], evidence['unit'])} "
                f"required ({evidence['tool']}, {evidence['basis']} basis)."
            )
        else:
            lines.append(f"{item.status.value}. {item.note}")
    lines.append("")

    confidence = plan.confidence if plan else comment.confidence
    lines += ["Confidence:", f"{confidence.value:.0%} (limited by {confidence.limiting_component})", ""]
    if plan and plan.consultation_reasons:
        lines += ["Consultation triggers:", ""]
        lines += [f"- {reason}" for reason in plan.consultation_reasons]
        lines.append("")
    return lines


def _short(value) -> str:
    if isinstance(value, float):
        return f"{value:.2f}"
    if isinstance(value, dict):
        keys = ("x", "y", "w", "h")
        if all(key in value for key in keys):
            return "(" + ", ".join(f"{value[key]:.2f}" for key in keys) + ")"
        return "…"
    if isinstance(value, list):
        return f"{len(value)} row(s)"
    return str(value)
