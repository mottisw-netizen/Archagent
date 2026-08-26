"""AutoCAD and Civil 3D - declared, not yet implemented.

Traffic, roads, site development and drainage arrive as consultant DWGs, so the
product needs this adapter; pretending it exists would be worse than saying
what it needs.  Until it is written, a DWG source is routed here, reported as
unavailable with the reason, and its comments become open items in the report
rather than silently disappearing.

Two implementations are possible, and they are not equivalent:

* **Live**, like Revit: an AutoCAD/Civil 3D add-in (.NET) hosting the same
  protocol, editing the drawing the consultant has open.
* **File**, headless: Autodesk Platform Services Design Automation, or the ODA
  libraries, converting and editing a DWG on a server. No live document, so no
  live approval - the output is a new DWG.
"""

from __future__ import annotations

from ..drawing.api import DrawingDriver
from .base import (
    DRAINAGE,
    LANDSCAPE,
    MARKUP,
    READ,
    ROADS,
    TRAFFIC,
    AdapterStatus,
    AdapterUnavailable,
    BaseAdapter,
    SourceRef,
    unavailable,
)

REASON = (
    "the DWG adapter is not implemented yet. Traffic, roads and drainage comments "
    "on a DWG need either an AutoCAD/Civil 3D add-in speaking the Archagent host "
    "protocol, or a headless converter (APS Design Automation / ODA). Until then "
    "these comments are reported as open items with a measured instruction list."
)


class DwgAdapter(BaseAdapter):
    name = "dwg"
    disciplines = (TRAFFIC, ROADS, DRAINAGE, LANDSCAPE)
    capabilities = (READ, MARKUP)
    suffixes = (".dwg", ".dxf", ".dwfx")

    def detects(self, source: SourceRef) -> bool:
        if source.kind == "host":
            return source.options.get("host") in ("autocad", "civil3d")
        return source.suffix in self.suffixes

    def status(self, source: SourceRef | None = None) -> AdapterStatus:
        return unavailable(self.name, REASON, self.capabilities, self.disciplines,
                           implementations=["autocad-addin", "civil3d-addin",
                                            "aps-design-automation", "oda"])

    def open(self, source: SourceRef) -> DrawingDriver:
        raise AdapterUnavailable(REASON)
