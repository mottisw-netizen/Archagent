"""A driver for a plain DXF file - AutoCAD's open exchange format - read and
written with `ezdxf <https://ezdxf.mankier.com/>`_ (MIT licence, pure Python).

This is the file, headless half of the DWG story the live add-in
(``autocad-addin/``) does not cover: no AutoCAD, no Windows, nothing running -
just a file on disk. A real ``.dwg`` needs converting to DXF first (the free
Open Design Alliance File Converter, run as a separate process - never
bundled, see :func:`convert_dwg_to_dxf`); a ``.dxf`` needs nothing extra at
all.

``DxfModelDriver`` does almost none of the work itself: it parses a DXF file
into the same JSON model shape ``JSONModelDriver`` already uses
(:func:`read_dxf`), then *is* a ``JSONModelDriver`` - every query, measurement
and mutation the pipeline calls is the reference implementation, unchanged and
already fully tested. The only DXF-specific work left is turning the mutated
model back into DXF entities when a version is saved (:meth:`save_as`).

Entities are categorised the same way the live AutoCAD add-in categorises
them (see ``autocad-addin/README.md``), because the two are meant to feel like
the same product from two directions:

1. an ``ARCHAGENT`` XDATA tag - one JSON string per entity;
2. failing that, the entity's layer name, matched against the same AIA-style
   keywords (``A-PARK`` -> parking, ``A-BLDG`` -> building, ...).
"""

from __future__ import annotations

import copy
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .api import DrawingAPIError
from .json_model import JSONModelDriver

try:
    import ezdxf
    from ezdxf import bbox as ezdxf_bbox
except ImportError:  # pragma: no cover - exercised via HAVE_EZDXF below
    ezdxf = None
    ezdxf_bbox = None

HAVE_EZDXF = ezdxf is not None

APP_NAME = "ARCHAGENT"

#: INSUNITS code -> metres per drawing unit (DXF group code 70 of $INSUNITS).
METRES_PER_UNIT = {
    0: 1.0,        # unitless: treat as already metres rather than guess feet
    1: 0.0254,     # inches
    2: 0.3048,     # feet
    4: 0.001,      # millimetres
    5: 0.01,       # centimetres
    6: 1.0,        # metres
    7: 1000.0,     # kilometres
    8: 0.9144,     # yards
    9: 1609.344,   # miles
}

#: Layer-name keyword -> the vocabulary the planner reasons about - identical
#: table to ``autocad-addin/src/EntityView.cs`` so a drawing behaves the same
#: whether it is opened live or headlessly.
LAYER_CATEGORIES = (
    ("PARK", "parking"), ("BLDG", "building"), ("BUILDING", "building"),
    ("WALL", "wall"), ("ROOM", "room"), ("DOOR", "door"), ("WIND", "window"),
    ("STAIR", "stair"), ("RAIL", "railing"), ("FLOOR", "floor"), ("ROOF", "roof"),
    ("COL", "column"), ("ROAD", "driveway"), ("DRIVE", "driveway"),
    ("WALK", "sidewalk"), ("DIM", "dimension"), ("TEXT", "text"), ("ANNO", "text"),
    ("SITE", "site"), ("PROP", "site"),
)


def metres_per_unit(doc) -> float:
    insunits = int(doc.header.get("$INSUNITS", 0) or 0)
    return METRES_PER_UNIT.get(insunits, 1.0)


def _tag_of(entity) -> dict:
    try:
        data = entity.get_xdata(APP_NAME)
    except Exception:  # ezdxf raises DXFValueError; a missing appid can also KeyError
        return {}
    for tag in data:
        if tag.code == 1000:
            try:
                return json.loads(tag.value)
            except (ValueError, TypeError):
                return {}
    return {}


def _category_of(entity, tag: dict) -> str:
    category = tag.get("category")
    if category:
        return str(category)
    dxftype = entity.dxftype()
    if dxftype == "DIMENSION":
        return "dimension"
    if dxftype in ("TEXT", "MTEXT"):
        return "text"
    layer = (entity.dxf.layer or "").upper()
    for keyword, name in LAYER_CATEGORIES:
        if keyword in layer:
            return name
    return "generic"


def _label_of(entity, tag: dict) -> str:
    label = tag.get("label")
    if label:
        return str(label)
    dxftype = entity.dxftype()
    if dxftype == "TEXT":
        return entity.dxf.text
    if dxftype == "MTEXT":
        return entity.text
    return entity.dxf.handle


def _bbox_of(entity, factor: float) -> dict | None:
    box = ezdxf_bbox.extents([entity], fast=True)
    if box is None or not box.has_data:
        return None
    return {
        "kind": "rect",
        "x": round(box.extmin.x * factor, 6),
        "y": round(box.extmin.y * factor, 6),
        "w": round((box.extmax.x - box.extmin.x) * factor, 6),
        "h": round((box.extmax.y - box.extmin.y) * factor, 6),
    }


def read_dxf(path) -> tuple[Any, dict]:
    """Parse a DXF file into ``(the ezdxf document, the JSON model)``."""
    if not HAVE_EZDXF:
        raise DrawingAPIError(
            "ezdxf is not installed; add the archagent[dxf] extra (`pip install ezdxf`)")
    doc = ezdxf.readfile(str(path))
    factor = metres_per_unit(doc)
    elements = []
    for entity in doc.modelspace():
        box = _bbox_of(entity, factor)
        if box is None:
            continue  # no plan geometry (e.g. an empty text) - nothing to measure
        tag = _tag_of(entity)
        properties = dict(tag.get("properties") or {})
        properties.setdefault("width_axis", "x" if box["w"] <= box["h"] else "y")
        properties["layer"] = entity.dxf.layer or ""
        elements.append({
            "id": entity.dxf.handle,
            "type": _category_of(entity, tag),
            "label": _label_of(entity, tag),
            "layer": entity.dxf.layer or "",
            "level": tag.get("level", ""),
            "sheet": tag.get("sheet", ""),
            "text": entity.dxf.text if entity.dxftype() == "TEXT" else "",
            "geometry": box,
            "properties": properties,
        })
    model = {
        "project_id": Path(path).stem,
        "units": "m",
        "north": "+y",
        "site": {},
        "sheets": [{"id": layout.name, "name": layout.name}
                  for layout in doc.layouts if layout.name != "Model"],
        "elements": elements,
        "schedules": {},
    }
    return doc, model


def convert_dwg_to_dxf(dwg_path, dxf_path, converter: str | None = None) -> Path:
    """Convert ``.dwg`` to ``.dxf`` via the free ODA File Converter.

    Run as a separate process, never linked or bundled: the ODA File
    Converter is free to use but is not open source, so Archagent depends on
    it being installed by whoever runs this - the same posture as calling
    ``pdftotext`` for PDF comment text.
    """
    binary = converter or shutil.which("ODAFileConverter") or shutil.which("odafileconverter")
    if not binary:
        raise DrawingAPIError(
            "no .dwg support without the free ODA File Converter on PATH "
            "(https://www.opendesign.com/guestfiles/oda_file_converter) - "
            "a plain .dxf needs no extra tool at all")
    dwg_path, dxf_path = Path(dwg_path), Path(dxf_path)
    dxf_path.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [binary, str(dwg_path.parent), str(dxf_path.parent), "ACAD2018", "DXF", "0", "1",
         dwg_path.name],
        capture_output=True, text=True, timeout=120)
    converted = dxf_path.parent / (dwg_path.stem + ".dxf")
    if not converted.exists():
        raise DrawingAPIError(
            f"ODA File Converter did not produce {converted.name}: "
            f"{result.stdout or result.stderr}".strip())
    if converted != dxf_path:
        converted.replace(dxf_path)
    return dxf_path


def convert_dxf_to_dwg(dxf_path, dwg_path, converter: str | None = None) -> Path:
    """The reverse of :func:`convert_dwg_to_dxf` - for a "download as .dwg"
    action once a run is done; never part of the version history itself
    (see ``DxfModelDriver.preferred_suffix``), so this stays optional."""
    binary = converter or shutil.which("ODAFileConverter") or shutil.which("odafileconverter")
    if not binary:
        raise DrawingAPIError(
            "no .dwg export without the free ODA File Converter on PATH "
            "(https://www.opendesign.com/guestfiles/oda_file_converter)")
    dxf_path, dwg_path = Path(dxf_path), Path(dwg_path)
    dwg_path.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [binary, str(dxf_path.parent), str(dwg_path.parent), "ACAD2018", "DWG", "0", "1",
         dxf_path.name],
        capture_output=True, text=True, timeout=120)
    converted = dwg_path.parent / (dxf_path.stem + ".dwg")
    if not converted.exists():
        raise DrawingAPIError(
            f"ODA File Converter did not produce {converted.name}: "
            f"{result.stdout or result.stderr}".strip())
    if converted != dwg_path:
        converted.replace(dwg_path)
    return dwg_path


class DxfModelDriver(JSONModelDriver):
    """A DXF file, opened, measured, edited and saved without any CAD seat.

    Every query/measure/mutate call is inherited from :class:`JSONModelDriver`
    unchanged; this class only parses the file in and writes the result back
    out as DXF, keeping the original ``ezdxf`` document so :meth:`save_as`
    edits real entities rather than starting a drawing from nothing.
    """

    name = "dxf"
    preferred_suffix = ".dxf"

    def __init__(self, path):
        self.source_path = Path(path)
        doc, model = read_dxf(self.source_path)
        super().__init__(model, path=self.source_path)
        self.doc = doc
        self._original_ids = {element["id"] for element in self.model["elements"]}

    @classmethod
    def load(cls, path) -> "DxfModelDriver":  # matches JSONModelDriver.load's shape
        return cls(path)

    def sandbox(self) -> "JSONModelDriver":
        # Simulation never touches ezdxf entities or the file: a plain
        # in-memory JSONModelDriver is enough to measure a plan's effect.
        return JSONModelDriver(copy.deepcopy(self.model), path=self.path)

    def save_as(self, path) -> str:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        factor = metres_per_unit(self.doc)
        current_ids = {element["id"] for element in self.model["elements"]}

        for handle in self._original_ids - current_ids:
            entity = self.doc.entitydb.get(handle)
            if entity is not None:
                self.doc.modelspace().delete_entity(entity)

        for element in self.model["elements"]:
            entity = self.doc.entitydb.get(element["id"])
            if entity is not None:
                _apply_geometry(entity, element, factor)
                _apply_tag(entity, element)

        self.doc.saveas(str(path))
        return str(path)


def _apply_geometry(entity, element: dict, factor: float) -> None:
    """Push a (possibly mutated) element's geometry back onto its own entity.

    Every element in this model is an axis-aligned rectangle - the same
    representation :mod:`drawing.geometry` uses everywhere - so a polyline is
    always rebuilt from that rectangle's four corners: lossless for the
    shapes this product reasons about, and simpler than tracking a delta.
    Anything this function does not specially handle is left as parsed; the
    JSON model - what every measurement, the report and the change set read -
    is correct regardless, so only that entity's own DXF geometry can lag.
    """
    box = element["geometry"]
    x, y = box["x"] / factor, box["y"] / factor
    w, h = box["w"] / factor, box["h"] / factor
    dxftype = entity.dxftype()

    if dxftype == "LWPOLYLINE":
        entity.set_points([(x, y), (x + w, y), (x + w, y + h), (x, y + h)])
    elif dxftype == "INSERT":
        entity.dxf.insert = (x, y, entity.dxf.insert.z)
    elif dxftype == "TEXT":
        entity.dxf.insert = (x, y, entity.dxf.insert.z)
        if element.get("text"):
            entity.dxf.text = element["text"]
    elif dxftype == "MTEXT":
        entity.dxf.insert = (x, y, entity.dxf.insert.z)
        if element.get("text"):
            entity.text = element["text"]


def _apply_tag(entity, element: dict) -> None:
    """Write the element's label/level/sheet/properties back into its XDATA
    tag - not just geometry - so a label or parameter set through
    ``set_text``/``set_parameter`` survives the round trip too, the same way
    it would in a live host's own storage."""
    tag = {"label": element.get("label", ""), "level": element.get("level", ""),
          "sheet": element.get("sheet", ""),
          "properties": {k: v for k, v in element.get("properties", {}).items()
                        if k not in ("width_axis", "layer")}}
    entity.set_xdata(APP_NAME, [(1000, json.dumps(tag))])
