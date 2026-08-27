"""AutoCAD and Civil 3D: live over the add-in, declared for a bare file.

Traffic, roads, site development and drainage arrive as consultant DWGs. Two
ways to reach one are not equivalent, and this adapter is honest about which
one it actually does:

* **Live**, like Revit: the add-in in ``autocad-addin/`` hosts the same
  protocol as the Revit add-in (``archagent.drawing.protocol`` - one contract,
  every host), editing the drawing the consultant has open. This is real: it
  is what ``open()`` returns for a live host, and it is exercised in tests
  against the same mock host the Revit path is proven against.
* **File**, headless, for a bare ``.dwg``/``.dxf`` with nothing open: not
  implemented. That would need Autodesk Platform Services Design Automation or
  the ODA libraries to convert and edit a DWG on a server, with no live
  document and so no live approval. Until then a file source is reported as
  unavailable with the reason, and its comments become open items with a
  measured instruction list rather than silently disappearing.
"""

from __future__ import annotations

from ..drawing.api import DrawingAPIError, DrawingDriver
from ..drawing.dwg import DwgDriver
from ..drawing.protocol import PROTOCOL_VERSION
from ..drawing.revit import HostUnavailable
from .base import (
    DRAINAGE,
    EDIT,
    LANDSCAPE,
    MEASURE,
    PREVIEW,
    READ,
    ROADS,
    TRAFFIC,
    VERSION,
    AdapterStatus,
    AdapterUnavailable,
    BaseAdapter,
    SourceRef,
    unavailable,
)

DEFAULT_URL = "http://127.0.0.1:8736"

FILE_REASON = (
    "a bare .dwg/.dxf cannot be opened directly - there is no live document to edit or "
    "get approval against. Traffic, roads and drainage comments on a DWG need either the "
    "AutoCAD/Civil 3D add-in (autocad-addin/) speaking the Archagent host protocol with the "
    "drawing open, or a headless converter (APS Design Automation / ODA). Until the drawing "
    "is opened live, these comments are reported as open items with a measured instruction list."
)


class DwgAdapter(BaseAdapter):
    """A consultant's AutoCAD or Civil 3D drawing: read, measure, edit - live.

    A ``.dwg``/``.dxf`` file on disk is *not* something this adapter opens by
    itself - same reasoning as Revit: the source has to be a running AutoCAD
    or Civil 3D with the add-in loaded and the drawing open.
    """

    name = "dwg"
    disciplines = (TRAFFIC, ROADS, DRAINAGE, LANDSCAPE)
    capabilities = (READ, MEASURE, EDIT, PREVIEW, VERSION)
    suffixes = (".dwg", ".dxf", ".dwfx")

    def __init__(self, url: str = DEFAULT_URL, token: str = "", timeout: float = 120.0):
        self.url = url
        self.token = token
        self.timeout = timeout

    # ------------------------------------------------------------------
    def detects(self, source: SourceRef) -> bool:
        if source.kind == "host":
            return source.options.get("host") in ("autocad", "civil3d")
        return source.suffix in self.suffixes

    def status(self, source: SourceRef | None = None) -> AdapterStatus:
        if source is not None and source.kind == "file":
            return unavailable(self.name, FILE_REASON, self.capabilities, self.disciplines,
                               file=source.location,
                               implementations=["autocad-addin", "civil3d-addin",
                                                "aps-design-automation", "oda"])
        url = self._url(source)
        try:
            info = DwgDriver(url, self.timeout, self.token).info()
        except (HostUnavailable, DrawingAPIError) as error:
            return unavailable(self.name, str(error), self.capabilities, self.disciplines, url=url)
        capabilities = tuple(c for c in self.capabilities
                             if not (info.read_only and c in (EDIT, VERSION)))
        return AdapterStatus(
            self.name, True, "", capabilities, self.disciplines,
            {"url": url, "host": info.host, "host_version": info.host_version,
             "document": info.document, "protocol": info.protocol,
             "expects_protocol": PROTOCOL_VERSION, "elements": info.element_count,
             "read_only": info.read_only})

    def open(self, source: SourceRef) -> DrawingDriver:
        status = self.status(source)
        if not status.available:
            raise AdapterUnavailable(status.reason)
        return DwgDriver(self._url(source), self.timeout, self.token)

    # ------------------------------------------------------------------
    def _url(self, source: SourceRef | None) -> str:
        if source is not None and source.kind == "host":
            return source.location
        return self.url
