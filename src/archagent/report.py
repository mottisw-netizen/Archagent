"""The correction report (SKILL.md 15) and the definition of done (23)."""

from __future__ import annotations

from .lang.messages import DEFAULT as DEFAULT_MESSAGES, Messages
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
                 consulted: set[str] | None = None,
                 messages: Messages | None = None,
                 narrative: tuple[str, list[str]] | None = None) -> str:
    m = messages or DEFAULT_MESSAGES
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
    lines: list[str] = []
    if m.rtl:
        lines.append('<div dir="rtl" align="right">')
        lines.append("")
    lines += [f"# {m.t('report_title')}", ""]
    if unmet:
        lines += [f"> {m.t('partial_warning')}", ">"]
        lines += [f"> - {text}" for text, _ok in unmet]
        lines.append("")
    if context.execution_mode == "markup_only":
        lines += [f"> {m.t('markup_warning')}", ""]

    lines += [
        f"{m.t('project')}: {context.project_id}",
        f"{m.t('run')}: {context.run_id}",
        f"{m.t('source_version')}: {parent_version} → {version}",
        f"{m.t('mode')}: {m.mode(context.operating_mode)}",
        f"{m.t('execution')}: {m.execution(context.execution_mode)}",
        f"{m.t('generated')}: {context.created_at}",
        "", f"## {m.t('summary')}", "",
    ]
    if narrative and narrative[0]:
        lines += [narrative[0], ""]
        if narrative[1]:
            lines += [f"{m.t('attention')}:", ""]
            lines += [f"- {item}" for item in narrative[1]]
            lines.append("")
    lines += [
        f"{m.t('total_comments')}: {len(validation.comments)}", "",
        f"{m.t('resolved_auto')}: {len(auto)}",
        f"{m.t('resolved_consulted')}: {len(after_consultation)}",
        f"{m.t('requires_review')}: {len(review)}",
        "",
    ]

    rows = []
    for comment in context.municipal_comments:
        item = statuses.get(comment.comment_id)
        plan = plans_by_comment.get(comment.comment_id)
        confidence = plan.confidence.value if plan else comment.confidence.value
        rows.append([comment.comment_id, m.department(comment.department),
                     m.status(item.status) if item else "-", f"{confidence:.0%}"])
    lines += [_table([m.t("th_comment"), m.t("th_department"), m.t("th_status"),
                      m.t("th_confidence")], rows), ""]

    for comment in context.municipal_comments:
        lines += _comment_section(comment, statuses.get(comment.comment_id),
                                 plans_by_comment.get(comment.comment_id),
                                 changes_by_comment.get(comment.comment_id, []),
                                 [d for d in decisions
                                  if plans_by_comment.get(comment.comment_id)
                                  and d.plan_id.startswith(f"PLAN-{comment.comment_id}")],
                                 m)

    lines += ["---", "", f"## {m.t('open_items')}", ""]
    open_rows = [[item["ref"], item["why"], item["needed"]] for item in context.open_items]
    lines += [_table([m.t("th_ref"), m.t("th_why_open"), m.t("th_needed")], open_rows), ""]

    lines += [f"## {m.t('constraint_summary')}", ""]
    constraint_rows = []
    for item in validation.constraints:
        measured = (m.value(item.measured, item.unit, item.op)
                    if item.measured is not None else "-")
        required = (m.value(item.required, item.unit)
                    if item.required is not None else "-")
        status = m.check_status(item.status) + (f" ({m.t('at_limit')})" if item.at_limit else "")
        constraint_rows.append([item.constraint_id, m.priority(item.priority), item.rule,
                                f"{item.op} {required}", measured, status])
    lines += [_table([m.t("th_constraint"), m.t("th_priority"), m.t("th_rule"),
                      m.t("th_required"), m.t("th_measured"), m.t("th_status")],
                     constraint_rows), ""]

    lines += [f"## {m.t('drawing_validation')}", ""]
    lines += [_table([m.t("th_check"), m.t("th_status"), m.t("th_details")],
                     [[m.check(check["check"]), m.check_status(check["status"]),
                       "; ".join(check["details"]) or "-"]
                      for check in validation.drawing_checks]), ""]

    non_visual = [c for c in changes if c.kind == "schedule" or c.property in ("text", "value")]
    lines += [f"## {m.t('non_visual')}", ""]
    if non_visual:
        lines += ["- " + m.t("updated", element=c.element_id, property=c.property,
                             before=_short(c.before, m), after=_short(c.after, m))
                  for c in non_visual]
    else:
        lines.append(f"- {m.t('none')}")
    lines.append("")

    lines += [f"## {m.t('versions')}", "",
              m.t("rollback_line", parent=parent_version, version=version),
              m.t("validation_result_line", result=m.result(validation.result)), ""]
    if files:
        lines += [f"{m.t('artefacts')}:", ""]
        lines += [f"- {name}: `{path}`" for name, path in sorted(files.items())]
        lines.append("")

    lines += [f"## {m.t('definition_of_done')}", ""]
    lines += [f"- [{'x' if ok else ' '}] {text}" for text, ok in definition_of_done]
    lines += ["", f"## {m.t('sign_off')}", "", m.t("sign_off_text"), "",
              m.t("reviewed_by"), ""]
    if m.rtl:
        lines += ["", "</div>"]
    return "\n".join(lines)


def _comment_section(comment: MunicipalComment, item, plan: CorrectionPlan | None,
                     changes: list[ChangeRecord], decisions: list[Decision],
                     m: Messages = DEFAULT_MESSAGES) -> list[str]:
    lines = ["---", "", f"## {comment.comment_id}", "",
             f"{m.t('department')}: {m.department(comment.department)}", "",
             f"{m.t('municipal_comment')}:", f'"{comment.original_text.strip()}"', ""]
    interpretation = comment.summary
    if not interpretation and comment.requirement is not None:
        interpretation = comment.requirement.describe_in(m)
    interpretation = interpretation or comment.normalized_requirement or m.t("none_extracted")
    lines += [f"{m.t('interpretation')}:", interpretation, ""]
    if comment.summary and comment.normalized_requirement:
        lines += [f"`{comment.normalized_requirement}`", ""]
    if decisions:
        decision = decisions[-1]
        lines += [f"{m.t('user_decision')}:",
                  f"{decision.user_choice} ({decision.decision_id})", ""]
    if changes:
        lines.append(f"{m.t('correction')}:")
        for change in changes:
            lines.append(f"- {change.element_id} {change.property}: "
                         f"{_short(change.before, m)} → {_short(change.after, m)}")
        lines.append("")
        sheets = sorted({change.sheet for change in changes if change.sheet})
        lines += [f"{m.t('affected_drawings')}:",
                  ", ".join(sheets) or m.t("not_sheeted"), ""]
    elif plan and plan.status == "already_compliant":
        lines += [f"{m.t('correction')}:", m.t("none_required"), ""]
    else:
        lines += [f"{m.t('correction')}:", m.t("none_applied"), ""]

    if plan and plan.expected_effects:
        lines.append(f"{m.t('planning_impact')}:")
        for effect in plan.expected_effects:
            verdict = m.t("still_compliant") if effect.still_compliant else m.t("not_compliant")
            lines.append(f"- {effect.element} {m.effect_property(effect.property)}: "
                         f"{m.value(effect.from_value or 0.0)} → "
                         f"{m.value(effect.to_value or 0.0)} "
                         f"({verdict}, {effect.constraint_id})")
        lines.append("")
    elif changes:
        lines += [f"{m.t('planning_impact')}:", m.t("no_impact"), ""]

    lines.append(f"{m.t('validation')}:")
    if item is None:
        lines.append(m.t("not_evaluated"))
    else:
        evidence = item.evidence
        if evidence:
            lines.append(m.t(
                "evidence_line", status=m.status(item.status),
                measured=m.value(evidence["measured"], evidence["unit"], evidence["op"]),
                op=evidence["op"],
                required=m.value(evidence["required"], evidence["unit"]),
                tool=evidence["tool"], basis=evidence["basis"]))
        else:
            lines.append(f"{m.status(item.status)}. {item.note}")
    lines.append("")

    confidence = plan.confidence if plan else comment.confidence
    lines += [f"{m.t('confidence')}:",
              m.t("confidence_limited", value=f"{confidence.value:.0%}",
                  component=m.component(confidence.limiting_component)), ""]
    if plan and plan.consultation_reasons:
        lines += [f"{m.t('consultation_triggers')}:", ""]
        lines += [f"- {reason}" for reason in plan.consultation_reasons]
        lines.append("")
    return lines


def _short(value, m: Messages = DEFAULT_MESSAGES) -> str:
    if isinstance(value, float):
        return f"{value:.2f}"
    if isinstance(value, dict):
        keys = ("x", "y", "w", "h")
        if all(key in value for key in keys):
            return "(" + ", ".join(f"{value[key]:.2f}" for key in keys) + ")"
        return "…"
    if isinstance(value, list):
        return m.t("rows", count=len(value))
    return str(value)
