"""Preview and highlight system (SKILL.md 13).

Renders the model to SVG, highlights every change with a colour *and* a text
tag (colour is never the only carrier of meaning), and writes a before/after
comparison page with a slider and a change map that links each highlight back
to the municipal comment that caused it.
"""

from __future__ import annotations

import html
import json
from pathlib import Path

from .drawing.geometry import Box, box_from_dict
from .lang.messages import DEFAULT as DEFAULT_MESSAGES, Messages
from .models import ChangeRecord, CommentStatus, ValidationResult

#: SKILL.md 13 colour key.
COLOURS = {
    "modified": "#2e9e4f",
    "created": "#2e9e4f",
    "removed": "#d33b2c",
    "indirect": "#e8c33a",
    "resolved": "#3574d4",
    "unresolved": "#e8862d",
}

LEGEND_KEYS = [
    ("modified", "legend_modified"),
    ("removed", "legend_removed"),
    ("indirect", "legend_indirect"),
    ("resolved", "legend_resolved"),
    ("unresolved", "legend_unresolved"),
]


def legend(messages: Messages = DEFAULT_MESSAGES) -> list[tuple[str, str]]:
    return [(kind, messages.t(key)) for kind, key in LEGEND_KEYS]

TYPE_STYLE = {
    "building": ("#dfe6ee", "#41556b"),
    "parking": ("#f3f1e7", "#8a7f5c"),
    "driveway": ("#eeeeee", "#9a9a9a"),
    "balcony": ("#e8eef6", "#5b7fa6"),
    "room": ("#f7f7f2", "#a9a191"),
    "ramp": ("#eef3ec", "#6f8f6a"),
    "landscape": ("#eaf3e6", "#6f9a5e"),
}
DEFAULT_STYLE = ("#f4f4f4", "#8c8c8c")

WIDTH = 960
MARGIN = 40


class Preview:
    """Renders one model state."""

    def __init__(self, model: dict, messages: Messages | None = None):
        self.model = model
        self.m = messages or DEFAULT_MESSAGES
        plot = model.get("site", {}).get("plot")
        boxes = [box_from_dict(e["geometry"]) for e in model.get("elements", [])
                 if "geometry" in e]
        if plot:
            boxes.append(box_from_dict(plot))
        self.extent = _union(boxes) or Box(0, 0, 10, 10)
        self.scale = (WIDTH - 2 * MARGIN) / max(self.extent.w, 1e-6)
        self.height = int(self.extent.h * self.scale + 2 * MARGIN)

    # ------------------------------------------------------------------
    def _x(self, value: float) -> float:
        return MARGIN + (value - self.extent.x) * self.scale

    def _y(self, value: float) -> float:
        """Flip the y axis: north is up in the drawing, down on screen."""
        return MARGIN + (self.extent.y_max - value) * self.scale

    def render(self, highlights: dict[str, str] | None = None,
               tags: dict[str, str] | None = None, title: str = "") -> str:
        highlights = highlights or {}
        tags = tags or {}
        parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {self.height}" '
            f'width="{WIDTH}" height="{self.height}" font-family="system-ui, sans-serif">',
            f'<rect width="{WIDTH}" height="{self.height}" fill="#ffffff"/>',
        ]
        plot = self.model.get("site", {}).get("plot")
        if plot:
            box = box_from_dict(plot)
            parts.append(self._rect(box, "#ffffff", "#333333", dash="6 4"))
            parts.append(self._text(self._x(box.x) + 4, self._y(box.y_max) - 6,
                                    self.m.t("plot_boundary"), size=11, colour="#555555"))
        for element in self.model.get("elements", []):
            if "geometry" not in element or element.get("type") in ("dimension", "text"):
                continue
            box = box_from_dict(element["geometry"])
            fill, stroke = TYPE_STYLE.get(element.get("type", ""), DEFAULT_STYLE)
            parts.append(self._rect(box, fill, stroke))
            label = element.get("label") or element["id"]
            parts.append(self._text(self._x(box.x) + 4, self._y(box.y_max) + 14, label, size=11))
            kind = highlights.get(element["id"])
            if kind:
                colour = COLOURS.get(kind, COLOURS["modified"])
                parts.append(self._rect(box, "none", colour, width=3))
                tag = tags.get(element["id"], "")
                if tag:
                    parts.append(self._tag(self._x(box.x), self._y(box.y_max) - 8, tag, colour))
        if title:
            parts.append(self._text(MARGIN, 24, title, size=15, colour="#222222", weight="600"))
        parts.append(self._legend())
        parts.append("</svg>")
        return "\n".join(parts)

    # ------------------------------------------------------------------
    def _rect(self, box: Box, fill: str, stroke: str, width: float = 1.2, dash: str = "") -> str:
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        return (f'<rect x="{self._x(box.x):.1f}" y="{self._y(box.y_max):.1f}" '
                f'width="{box.w * self.scale:.1f}" height="{box.h * self.scale:.1f}" '
                f'fill="{fill}" stroke="{stroke}" stroke-width="{width}"{dash_attr}/>')

    @staticmethod
    def _text(x: float, y: float, text: str, size: int = 12, colour: str = "#333333",
              weight: str = "400") -> str:
        return (f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" fill="{colour}" '
                f'font-weight="{weight}">{html.escape(text)}</text>')

    def _tag(self, x: float, y: float, text: str, colour: str) -> str:
        width = 7 * len(text) + 10
        return (f'<g><rect x="{x:.1f}" y="{y - 14:.1f}" width="{width}" height="16" rx="3" '
                f'fill="{colour}"/>'
                f'<text x="{x + 5:.1f}" y="{y - 2:.1f}" font-size="11" fill="#ffffff">'
                f'{html.escape(text)}</text></g>')

    def _legend(self) -> str:
        parts = ['<g>']
        y = self.height - MARGIN + 6
        x = MARGIN
        for kind, description in legend(self.m):
            parts.append(f'<rect x="{x}" y="{y - 10}" width="12" height="12" '
                         f'fill="{COLOURS[kind]}"/>')
            parts.append(self._text(x + 17, y, description, size=10, colour="#444444"))
            x += 20 + 6.2 * len(description)
        parts.append("</g>")
        return "\n".join(parts)


def _union(boxes: list[Box]) -> Box | None:
    if not boxes:
        return None
    x = min(b.x for b in boxes)
    y = min(b.y for b in boxes)
    return Box(x, y, max(b.x_max for b in boxes) - x, max(b.y_max for b in boxes) - y)


def build_change_map(changes: list[ChangeRecord], impact_set: list[str],
                     validation: ValidationResult) -> dict:
    """Highlight -> element -> comment mapping (SKILL.md 13.2)."""
    resolved = {c.comment_id for c in validation.comments if c.status is CommentStatus.RESOLVED}
    open_comments = {c.comment_id for c in validation.comments
                     if c.status in (CommentStatus.REQUIRES_HUMAN_REVIEW,
                                     CommentStatus.NOT_RESOLVED,
                                     CommentStatus.PARTIALLY_RESOLVED)}
    entries: dict[str, dict] = {}
    for change in changes:
        entry = entries.setdefault(change.element_id, {
            "element_id": change.element_id,
            "highlight": "created" if change.kind == "created" else
                         ("removed" if change.kind == "removed" else "modified"),
            "comments": [],
            "changes": [],
            "sheet": change.sheet,
        })
        entry["changes"].append({
            "property": change.property,
            "before": change.before,
            "after": change.after,
            "tool": change.tool,
        })
        if change.comment_id and change.comment_id not in entry["comments"]:
            entry["comments"].append(change.comment_id)
    for element_id in impact_set:
        if element_id not in entries:
            entries[element_id] = {"element_id": element_id, "highlight": "indirect",
                                   "comments": [], "changes": [], "sheet": ""}
    return {
        "entries": list(entries.values()),
        "resolved_comments": sorted(resolved),
        "open_comments": sorted(open_comments),
        "colours": COLOURS,
    }


def highlight_maps(change_map: dict) -> tuple[dict[str, str], dict[str, str]]:
    highlights, tags = {}, {}
    for entry in change_map["entries"]:
        highlights[entry["element_id"]] = entry["highlight"]
        if entry["comments"]:
            tags[entry["element_id"]] = ", ".join(entry["comments"])
        elif entry["highlight"] == "indirect":
            tags[entry["element_id"]] = DEFAULT_MESSAGES.t("affected")
    return highlights, tags


def write_previews(output_dir: Path, before_model: dict, after_model: dict,
                   change_map: dict, version: str,
                   messages: Messages | None = None) -> dict:
    """Write before/after/highlighted SVGs plus the comparison page."""
    m = messages or DEFAULT_MESSAGES
    output_dir = Path(output_dir)
    compare_dir = output_dir / "compare"
    compare_dir.mkdir(parents=True, exist_ok=True)
    highlights, tags = highlight_maps(change_map)

    before_svg = Preview(before_model, m).render(title=m.t("before"))
    after_svg = Preview(after_model, m).render(title=m.t("after", version=version))
    highlighted_svg = Preview(after_model, m).render(
        highlights, tags, title=m.t("changes", version=version))

    files = {
        "before": compare_dir / "before.svg",
        "after": compare_dir / "after.svg",
        "highlighted": output_dir / f"preview_{version}_changes.svg",
        "comparison": output_dir / "compare_before_after.html",
        "change_map": output_dir / "change_map.json",
    }
    files["before"].write_text(before_svg, encoding="utf-8")
    files["after"].write_text(after_svg, encoding="utf-8")
    files["highlighted"].write_text(highlighted_svg, encoding="utf-8")
    files["change_map"].write_text(json.dumps(change_map, indent=2, ensure_ascii=False) + "\n",
                                   encoding="utf-8")
    files["comparison"].write_text(
        _comparison_page(before_svg, highlighted_svg, change_map, version, m),
        encoding="utf-8")
    return {name: str(path) for name, path in files.items()}


def _comparison_page(before_svg: str, after_svg: str, change_map: dict, version: str,
                     m: Messages = DEFAULT_MESSAGES) -> str:
    rows = []
    for entry in change_map["entries"]:
        changes = "<br>".join(
            f"{html.escape(str(c['property']))}: {html.escape(str(c['before']))} → "
            f"{html.escape(str(c['after']))}" for c in entry["changes"]) \
            or html.escape(m.t("affected_indirectly"))
        rows.append(
            f"<tr><td><span class='dot' style=\"background:"
            f"{COLOURS.get(entry['highlight'], '#888')}\"></span>"
            f"{html.escape(entry['element_id'])}</td>"
            f"<td>{html.escape(', '.join(entry['comments']) or '-')}</td>"
            f"<td>{changes}</td></tr>")
    legend_html = "".join(
        f"<span class='key'><span class='dot' style=\"background:{COLOURS[kind]}\"></span>"
        f"{html.escape(text)}</span>" for kind, text in legend(m))
    return f"""<!doctype html>
<html lang="{m.code}" dir="{m.text_direction}"><head><meta charset="utf-8">
<title>{html.escape(m.t("compare_title", version=version))}</title>
<style>
 body {{ font-family: system-ui, sans-serif; margin: 24px; color: #222; background: #fafafa; }}
 h1 {{ font-size: 20px; }}
 .frame {{ position: relative; max-width: 960px; border: 1px solid #ddd; background: #fff; }}
 .frame .layer {{ position: absolute; inset: 0; overflow: hidden; }}
 .frame svg {{ display: block; width: 100%; height: auto; }}
 .key {{ margin-right: 16px; font-size: 12px; }}
 .dot {{ display: inline-block; width: 10px; height: 10px; border-radius: 2px;
        margin-right: 6px; vertical-align: middle; }}
 table {{ border-collapse: collapse; margin-top: 20px; font-size: 13px; background: #fff; }}
 th, td {{ border: 1px solid #e0e0e0; padding: 6px 10px; text-align: left; vertical-align: top; }}
 input[type=range] {{ width: 100%; max-width: 960px; margin: 10px 0 20px; }}
</style></head>
<body>
<h1>{html.escape(m.t("compare_title", version=version))}</h1>
<div>{legend_html}</div>
<input type="range" id="slider" min="0" max="100" value="50">
<div class="frame" id="frame">
  <div>{before_svg}</div>
  <div class="layer" id="after" style="width:50%">{after_svg}</div>
</div>
<table><thead><tr><th>{html.escape(m.t("th_element"))}</th>
<th>{html.escape(m.t("th_comment"))}</th>
<th>{html.escape(m.t("th_change"))}</th></tr></thead>
<tbody>{''.join(rows) or f'<tr><td colspan="3">{html.escape(m.t("no_changes"))}</td></tr>'}</tbody></table>
<script>
 const slider = document.getElementById('slider');
 const after = document.getElementById('after');
 slider.addEventListener('input', () => {{ after.style.width = slider.value + '%'; }});
</script>
</body></html>
"""
