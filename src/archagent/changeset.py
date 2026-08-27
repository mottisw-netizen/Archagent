"""The Diff / Change Set: exactly what changed, in the CAD tool's own terms.

The report explains the run to a person and the preview shows it to an eye.
This is the third thing, and the one a CAD tool can act on: every element the
run touched, named by the id the *host* uses - a Revit ``UniqueId``, not an
index into a JSON file - with its before and after, the comment that demanded
it, and the constraint the change was meant to satisfy.

Two things depend on it:

* an architect selecting the changed elements in Revit to see what moved;
* the next run, or a reviewer, reconstructing the delta between two versions
  without re-deriving it from geometry.

It is written from the change records, not measured again, because the records
are what the host itself reported after applying the plan - and geometry that
disagrees with them is a bug worth seeing rather than a difference to smooth
over. What *is* re-derived is the geometry delta (§ :func:`_geometry_delta`),
so a reader can highlight the element without opening the CAD tool.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .lang.messages import DEFAULT as DEFAULT_MESSAGES, Messages
from .models import ChangeRecord, CommentStatus, MunicipalComment, ValidationResult, now

#: Bumped when the artefact's shape changes; a reader can branch on it.
CHANGE_SET_VERSION = "1.0"


def _source_summary(source: dict | None) -> dict:
    """Where the change set was produced - flat, because a reader wants it flat."""
    if not source:
        return {}
    reference = source.get("source", source)
    detail = (source.get("status") or {}).get("detail", {})
    return {"kind": reference.get("kind", ""), "location": reference.get("location", ""),
            "adapter": source.get("adapter", ""), "discipline": reference.get("discipline", ""),
            "document": detail.get("document", ""), "host": detail.get("host", "")}


def _sources_summary(sources: list[dict] | None) -> list[dict]:
    return [_source_summary(source) for source in (sources or [])]


def _index(model: dict) -> dict[str, dict]:
    return {element["id"]: element for element in (model or {}).get("elements", [])}


def _geometry_delta(before: dict | None, after: dict | None) -> dict:
    """What moved, in metres - enough to draw a highlight without the CAD tool."""
    if not before or not after:
        return {}
    first, second = before.get("geometry", {}), after.get("geometry", {})
    delta = {}
    for axis, key in (("dx", "x"), ("dy", "y"), ("dw", "w"), ("dh", "h")):
        if key in first and key in second:
            moved = round(float(second[key]) - float(first[key]), 6)
            if moved:
                delta[axis] = moved
    if delta:
        delta["before"] = {k: first.get(k) for k in ("x", "y", "w", "h") if k in first}
        delta["after"] = {k: second.get(k) for k in ("x", "y", "w", "h") if k in second}
    return delta


def build(changes: list[ChangeRecord], before_model: dict, after_model: dict,
          version: str, parent_version: str, comments: list[MunicipalComment],
          validation: ValidationResult | None = None, run_id: str = "",
          source: dict | None = None, sources: list[dict] | None = None,
          baseline: dict | None = None,
          messages: Messages | None = None) -> dict:
    """Assemble the change set. Pure: it reads, it does not measure or write.

    ``before_model``/``after_model`` are the primary architectural source, so
    the geometry delta and the spatial preview stay meaningful; a change made
    in a second live tool (a DWG, say) still gets its full before/after per
    property from ``changes`` - only the geometry delta is unavailable for it.
    """
    m = messages or DEFAULT_MESSAGES
    before_index, after_index = _index(before_model), _index(after_model)
    by_comment = {comment.comment_id: comment for comment in comments}
    multi_source = len({change.adapter for change in changes if change.adapter}) > 1

    elements: dict[str, dict] = {}
    for change in changes:
        entry = elements.setdefault(change.element_id, {
            "element_id": change.element_id,
            "kind": change.kind,
            "adapter": change.adapter,
            "label": (after_index.get(change.element_id)
                      or before_index.get(change.element_id) or {}).get("label", ""),
            "category": (after_index.get(change.element_id)
                         or before_index.get(change.element_id) or {}).get("type", ""),
            "sheet": change.sheet,
            "comments": [],
            "plans": [],
            "properties": [],
            "geometry": _geometry_delta(before_index.get(change.element_id),
                                        after_index.get(change.element_id)),
        })
        entry["properties"].append({
            "property": change.property,
            "before": change.before,
            "after": change.after,
            "tool": change.tool,
            "comment_id": change.comment_id,
            "plan_id": change.plan_id,
        })
        for key, value in (("comments", change.comment_id), ("plans", change.plan_id)):
            if value and value not in entry[key]:
                entry[key].append(value)

    # Grouped by adapter as well as flat: a live host is asked to select only
    # the elements that are actually its own, one call per tool.
    highlight_by_source: dict[str, list[str]] = {}
    for element_id, entry in elements.items():
        highlight_by_source.setdefault(entry["adapter"] or "", []).append(element_id)

    document: dict[str, Any] = {
        "change_set_version": CHANGE_SET_VERSION,
        "run_id": run_id,
        "created_at": now(),
        "version": version,
        "parent_version": parent_version,
        "language": m.code,
        "source": _source_summary(source or (sources[0] if sources else None)),
        "sources": _sources_summary(sources if sources is not None else
                                    ([source] if source else [])),
        "multi_source": multi_source,
        "counts": {
            "elements": len(elements),
            "changes": len(changes),
            "comments": len({c.comment_id for c in changes if c.comment_id}),
        },
        "elements": list(elements.values()),
        # The ids a host is asked to select. Named separately because that is
        # the one thing a CAD tool consumes without parsing the rest.
        "highlight": list(elements),
        "highlight_by_source": highlight_by_source,
        "by_comment": [],
        "constraints": [],
    }

    statuses = {item.comment_id: item for item in (validation.comments if validation else [])}
    for comment_id in sorted({change.comment_id for change in changes if change.comment_id}):
        item = statuses.get(comment_id)
        comment = by_comment.get(comment_id)
        document["by_comment"].append({
            "comment_id": comment_id,
            "department": comment.department if comment else "",
            "summary": (comment.summary or comment.normalized_requirement
                        or comment.required_action) if comment else "",
            "status": item.status.value if item else CommentStatus.NOT_RESOLVED.value,
            "status_label": m.status(item.status) if item else "",
            "evidence": item.evidence if item else {},
            "elements": [change.element_id for change in changes
                         if change.comment_id == comment_id],
        })

    # Only constraints this run moved, or that are still failing: a list of
    # every rule that already passed and still passes is noise in a diff.
    for constraint in (validation.constraints if validation else []):
        was = (baseline or {}).get(constraint.constraint_id)
        if was == constraint.status == "pass":
            continue
        document["constraints"].append({
            "constraint_id": constraint.constraint_id,
            "rule": constraint.rule,
            "op": constraint.op,
            "required": constraint.required,
            "measured": constraint.measured,
            "unit": constraint.unit,
            "status_before": was or "not_evaluated",
            "status_after": constraint.status,
            "at_limit": constraint.at_limit,
            "resolved_here": bool(was and was != "pass" and constraint.status == "pass"),
            "regressed_here": bool(was == "pass" and constraint.status == "fail"),
        })
    return document


def write(output_dir, document: dict) -> Path:
    path = Path(output_dir) / "change_set.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    return path
