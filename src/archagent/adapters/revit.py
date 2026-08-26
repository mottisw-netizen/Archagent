"""Revit, live, through the Archagent add-in."""

from __future__ import annotations

from ..drawing.api import DrawingAPIError, DrawingDriver
from ..drawing.protocol import PROTOCOL_VERSION
from ..drawing.revit import HostUnavailable, RevitDriver
from .base import (
    ACCESSIBILITY,
    ARCHITECTURE,
    EDIT,
    FIRE,
    MEASURE,
    PREVIEW,
    READ,
    STRUCTURE,
    VERSION,
    AdapterStatus,
    AdapterUnavailable,
    BaseAdapter,
    SourceRef,
    unavailable,
)

DEFAULT_URL = "http://127.0.0.1:8735"


class RevitAdapter(BaseAdapter):
    """The architectural model: read, measure, edit, version - live.

    A ``.rvt`` file on disk is *not* something this adapter can open by itself.
    Revit's API only exists inside Revit, so the source has to be a running
    Revit with the add-in loaded and the project open.  That is stated rather
    than hidden: pointing this adapter at a file returns a status explaining
    what to do, not a broken driver.
    """

    name = "revit"
    disciplines = (ARCHITECTURE, STRUCTURE, ACCESSIBILITY, FIRE)
    capabilities = (READ, MEASURE, EDIT, PREVIEW, VERSION)
    suffixes = (".rvt",)

    def __init__(self, url: str = DEFAULT_URL, token: str = "", timeout: float = 120.0):
        self.url = url
        self.token = token
        self.timeout = timeout

    # ------------------------------------------------------------------
    def detects(self, source: SourceRef) -> bool:
        if source.kind == "host":
            return source.options.get("host", "revit") in ("revit", "auto")
        return source.suffix in self.suffixes

    def status(self, source: SourceRef | None = None) -> AdapterStatus:
        url = self._url(source)
        if source is not None and source.kind == "file":
            return unavailable(
                self.name,
                "a .rvt file cannot be opened directly - the Revit API only runs inside "
                "Revit. Open the project in Revit with the Archagent add-in loaded and "
                f"point the adapter at the add-in (default {DEFAULT_URL}).",
                self.capabilities, self.disciplines, file=source.location)
        try:
            info = RevitDriver(url, self.timeout, self.token).info()
        except HostUnavailable as error:
            return unavailable(self.name, str(error), self.capabilities, self.disciplines,
                               url=url)
        except DrawingAPIError as error:
            return unavailable(self.name, str(error), self.capabilities, self.disciplines,
                               url=url)
        capabilities = tuple(c for c in self.capabilities if not (info.read_only and c in (EDIT, VERSION)))
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
        driver = RevitDriver(self._url(source), self.timeout, self.token)
        plot = (source.options or {}).get("plot")
        if plot:
            driver.set_plot(plot)
        return driver

    # ------------------------------------------------------------------
    def _url(self, source: SourceRef | None) -> str:
        if source is not None and source.kind == "host":
            return source.location
        return self.url
