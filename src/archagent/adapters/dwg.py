"""AutoCAD and Civil 3D: live over the add-in, or headless over a file.

Traffic, roads, site development and drainage arrive as consultant DWGs. Two
ways to reach one are not equivalent, and this adapter is honest about which
one it actually does, and with what it needs:

* **Live**, like Revit: the add-in in ``autocad-addin/`` hosts the same
  protocol as the Revit add-in (``archagent.drawing.protocol`` - one contract,
  every host), editing the drawing the consultant has open.
* **File**, headless, no CAD seat anywhere: a ``.dxf`` opens with nothing extra
  (``ezdxf``, MIT licence, already a dependency); a ``.dwg`` needs converting
  to DXF first with the free Open Design Alliance File Converter, run as a
  separate process and never bundled - the same posture as calling
  ``pdftotext`` for PDF comment text. A ``.dwfx``/``.dwf`` is Autodesk's
  publish/view format: there is no live document behind it to edit, so it
  stays declared, same as a file this adapter genuinely cannot open.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from ..drawing.api import DrawingAPIError, DrawingDriver
from ..drawing.dwg import DwgDriver
from ..drawing.dxf_model import HAVE_EZDXF, DxfModelDriver, convert_dwg_to_dxf
from ..drawing.protocol import PROTOCOL_VERSION
from ..drawing.revit import HostUnavailable
from .base import (
    DRAINAGE,
    EDIT,
    LANDSCAPE,
    MARKUP,
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

NO_EZDXF_REASON = "ezdxf is not installed; add the archagent[dxf] extra (`pip install ezdxf`)"

NO_ODA_REASON = (
    "a .dwg file needs converting to .dxf first, with the free Open Design Alliance File "
    "Converter (https://www.opendesign.com/guestfiles/oda_file_converter) on PATH - a plain "
    ".dxf needs no extra tool at all"
)

DWF_REASON = (
    "a .dwf/.dwfx is Autodesk's publish/view format - there is no live, editable document "
    "behind it, only a fixed snapshot. Traffic, roads and drainage comments on one are "
    "reported as open items with a measured instruction list rather than an edit."
)


class DwgAdapter(BaseAdapter):
    """A consultant's AutoCAD/Civil 3D drawing: read, measure, edit - live or headless.

    A live source needs the add-in loaded with the drawing open, same
    reasoning as Revit; a file source needs nothing running at all, only
    ``ezdxf`` (and, for a ``.dwg``, the ODA converter) - see the module
    docstring for exactly what each path needs and why.
    """

    name = "dwg"
    disciplines = (TRAFFIC, ROADS, DRAINAGE, LANDSCAPE)
    capabilities = (READ, MEASURE, EDIT, PREVIEW, VERSION)
    suffixes = (".dwg", ".dxf")
    view_only_suffixes = (".dwf", ".dwfx")

    def __init__(self, url: str = DEFAULT_URL, token: str = "", timeout: float = 120.0):
        self.url = url
        self.token = token
        self.timeout = timeout

    # ------------------------------------------------------------------
    def detects(self, source: SourceRef) -> bool:
        if source.kind == "host":
            return source.options.get("host") in ("autocad", "civil3d")
        return source.suffix in self.suffixes or source.suffix in self.view_only_suffixes

    def status(self, source: SourceRef | None = None) -> AdapterStatus:
        if source is not None and source.kind == "file":
            return self._file_status(source)
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

    def _file_status(self, source: SourceRef) -> AdapterStatus:
        if source.suffix in self.view_only_suffixes:
            return unavailable(self.name, DWF_REASON, (READ, MARKUP), self.disciplines,
                               file=source.location)
        if not HAVE_EZDXF:
            return unavailable(self.name, NO_EZDXF_REASON, self.capabilities, self.disciplines,
                               file=source.location)
        if source.suffix == ".dwg" and not (shutil.which("ODAFileConverter")
                                            or shutil.which("odafileconverter")):
            return unavailable(self.name, NO_ODA_REASON, self.capabilities, self.disciplines,
                               file=source.location)
        return AdapterStatus(self.name, True, "", self.capabilities, self.disciplines,
                             {"file": source.location, "format": source.suffix.lstrip(".")})

    def open(self, source: SourceRef) -> DrawingDriver:
        status = self.status(source)
        if not status.available:
            raise AdapterUnavailable(status.reason)
        if source.kind == "file":
            path = Path(source.location)
            if path.suffix.casefold() == ".dwg":
                converted = path.with_name(path.stem + ".archagent.dxf")
                convert_dwg_to_dxf(path, converted)
                path = converted
            return DxfModelDriver(path)
        return DwgDriver(self._url(source), self.timeout, self.token)

    # ------------------------------------------------------------------
    def _url(self, source: SourceRef | None) -> str:
        if source is not None and source.kind == "host":
            return source.location
        return self.url
