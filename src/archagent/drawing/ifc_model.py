"""A minimal, read-only reader for a plain IFC (.ifc / STEP-SPF text) file.

Scope, stated plainly: this parses entity **type**, **GlobalId**, and
**Name** out of the STEP (ISO 10303-21) text records in an IFC file's `DATA`
section, using nothing but the standard library - no `ifcopenshell`, no
geometry interpretation, no property-set extraction, no round-trip (nothing
here can write an IFC file back out). A real IFC element's placement,
extrusion, and Pset properties are not read, so an element this produces has
no `geometry` and cannot be measured by the constraint engine - the same
"read/markup only, never fabricate a capability" boundary the PDF adapter
already documents (SKILL.md §3.3), applied to IFC. This is **not** wired into
`archagent.adapters` as a live adapter: opening an `.ifc` file still only
means the input manifest recognises the extension (SKILL.md's existing
"unreadable file" list), not that a `DrawingDriver` exists for it. Use
:func:`read_ifc` directly when a preliminary element listing (for a report,
or for manual review) is useful on its own.
"""

from __future__ import annotations

import re
from pathlib import Path

#: STEP (ISO 10303-21) keywords are case-insensitive, and real exporters do
#: differ - `IFCWINDOW`, `IfcWindow` and `ifcwindow` are the same entity - so
#: the record is matched case-insensitively and the type upper-cased before
#: it is looked up in :data:`IFC_TYPE_MAP`.
_STEP_RECORD = re.compile(
    r"^#(?P<id>\d+)\s*=\s*(?P<type>[A-Za-z][A-Za-z0-9_]*)\s*\((?P<args>.*)\)\s*;\s*$")

#: IFC entity type -> the generic vocabulary the rest of the pipeline already
#: uses (archagent.drawing.dxf_model.LAYER_CATEGORIES' target names). An IFC
#: type with no entry here is skipped, not guessed.
IFC_TYPE_MAP = {
    "IFCWALL": "wall", "IFCWALLSTANDARDCASE": "wall",
    "IFCDOOR": "door", "IFCWINDOW": "window",
    "IFCSPACE": "room", "IFCSLAB": "floor", "IFCROOF": "roof",
    "IFCSTAIR": "stair", "IFCSTAIRFLIGHT": "stair",
    "IFCCOLUMN": "column", "IFCRAILING": "railing",
    "IFCBUILDING": "building", "IFCSITE": "site",
    "IFCBUILDINGSTOREY": "level",
    "IFCBEAM": "beam", "IFCRAMP": "ramp", "IFCRAMPFLIGHT": "ramp",
}


def _split_args(args: str) -> list[str]:
    """Split a STEP argument list on top-level commas only - a comma inside
    a nested `(...)` or a quoted `'...'` string does not separate arguments."""
    parts: list[str] = []
    depth = 0
    in_string = False
    current: list[str] = []
    for ch in args:
        if ch == "'":
            in_string = not in_string
            current.append(ch)
        elif ch == "(" and not in_string:
            depth += 1
            current.append(ch)
        elif ch == ")" and not in_string:
            depth -= 1
            current.append(ch)
        elif ch == "," and depth == 0 and not in_string:
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(ch)
    if current:
        parts.append("".join(current).strip())
    return parts


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == "'" and value[-1] == "'":
        return value[1:-1]
    return ""


def read_ifc(path: str | Path) -> dict:
    """Every recognised entity in ``path``'s ``DATA`` section, as a plain
    dict list - never geometry, never a claim of full IFC support."""
    path = Path(path)
    text = path.read_text(encoding="utf-8", errors="replace")

    elements: list[dict] = []
    in_data = False
    buffer = ""
    for raw_line in text.splitlines():
        line = raw_line.strip()
        marker = line.upper()          # STEP section keywords are case-insensitive too
        if marker == "DATA;":
            in_data = True
            continue
        if marker == "ENDSEC;":
            in_data = False
            continue
        if not in_data:
            continue
        buffer = f"{buffer} {line}".strip() if buffer else line
        if not buffer.endswith(";"):
            continue
        record, buffer = buffer, ""
        match = _STEP_RECORD.match(record)
        if not match:
            continue
        ifc_type = match.group("type").upper()
        element_type = IFC_TYPE_MAP.get(ifc_type)
        if element_type is None:
            continue
        args = _split_args(match.group("args"))
        global_id = _unquote(args[0]) if args else ""
        name = _unquote(args[2]) if len(args) > 2 else ""
        elements.append({
            "id": f"#{match.group('id')}",
            "type": element_type,
            "label": name or global_id or f"#{match.group('id')}",
            "properties": {"ifc_type": ifc_type, "global_id": global_id},
        })

    return {
        "project_id": path.stem,
        "units": "m",
        "source_format": "IFC",
        "elements": elements,
    }
