"""Which adapter opens what, and which one a comment belongs to."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..drawing.api import DrawingAPIError, DrawingDriver
from ..models import MunicipalComment
from .base import (
    ARCHITECTURE,
    DEPARTMENT_DISCIPLINE,
    DOCUMENTS,
    EDIT,
    Adapter,
    AdapterStatus,
    AdapterUnavailable,
    SourceRef,
)
from .dwg import DwgAdapter
from .json_model import JsonAdapter
from .pdf import PdfAdapter
from .revit import RevitAdapter


class AdapterRegistry:
    """The adapters this installation knows about."""

    def __init__(self, adapters: list[Adapter] | None = None):
        self.adapters: list[Adapter] = list(adapters or [])

    def register(self, adapter: Adapter) -> Adapter:
        self.adapters.append(adapter)
        return adapter

    def get(self, name: str) -> Adapter | None:
        return next((a for a in self.adapters if a.name == name), None)

    def for_source(self, source: SourceRef) -> Adapter | None:
        return next((a for a in self.adapters if a.detects(source)), None)

    def for_discipline(self, discipline: str) -> list[Adapter]:
        return [a for a in self.adapters if discipline in a.disciplines]

    def statuses(self, source: SourceRef | None = None) -> list[AdapterStatus]:
        return [a.status(source) for a in self.adapters]

    def describe(self) -> list[dict]:
        return [a.describe() for a in self.adapters]


def default_registry(revit_url: str = "", token: str = "") -> AdapterRegistry:
    revit = RevitAdapter(revit_url or RevitAdapter().url, token=token)
    return AdapterRegistry([revit, JsonAdapter(), DwgAdapter(), PdfAdapter()])


# ----------------------------------------------------------------------
@dataclass
class OpenSource:
    """One source the workspace tried to open."""

    source: SourceRef
    adapter_name: str
    driver: DrawingDriver | None = None
    status: AdapterStatus | None = None
    error: str = ""

    @property
    def available(self) -> bool:
        return self.driver is not None

    @property
    def disciplines(self) -> tuple[str, ...]:
        return tuple(self.status.disciplines) if self.status else ()

    def can_edit(self) -> bool:
        return bool(self.status and EDIT in self.status.capabilities and self.available)

    def to_dict(self) -> dict:
        return {"source": self.source.to_dict(), "adapter": self.adapter_name,
                "available": self.available, "error": self.error,
                "status": self.status.to_dict() if self.status else None}


class Workspace:
    """Every source of one permit package, opened through its adapter."""

    def __init__(self, registry: AdapterRegistry | None = None):
        self.registry = registry or default_registry()
        self.opened: list[OpenSource] = []

    def add(self, source: SourceRef) -> OpenSource:
        adapter = self.registry.for_source(source)
        if adapter is None:
            entry = OpenSource(source, "none", error=f"no adapter opens {source.location}")
            self.opened.append(entry)
            return entry
        status = adapter.status(source)
        entry = OpenSource(source, adapter.name, status=status)
        if status.available:
            try:
                entry.driver = adapter.open(source)
            except (AdapterUnavailable, DrawingAPIError) as error:
                entry.error = str(error)
        else:
            entry.error = status.reason
        self.opened.append(entry)
        return entry

    # ------------------------------------------------------------------
    def drivers(self) -> list[DrawingDriver]:
        return [entry.driver for entry in self.opened if entry.driver is not None]

    def primary(self) -> DrawingDriver | None:
        """The architectural model: what versions, previews and reports follow."""
        for entry in self.opened:
            if entry.available and ARCHITECTURE in entry.disciplines:
                return entry.driver
        return next((entry.driver for entry in self.opened if entry.available), None)

    def for_discipline(self, discipline: str) -> list[OpenSource]:
        return [entry for entry in self.opened
                if entry.available and discipline in entry.disciplines]

    def unavailable(self) -> list[OpenSource]:
        return [entry for entry in self.opened if not entry.available]

    def close(self) -> None:
        for entry in self.opened:
            if entry.driver is not None:
                entry.driver.close()

    def to_dict(self) -> list[dict]:
        return [entry.to_dict() for entry in self.opened]


# ----------------------------------------------------------------------
@dataclass
class Routing:
    """Where a comment should be worked, and why."""

    comment_id: str
    discipline: str
    source: OpenSource | None = None
    reason: str = ""
    needed: str = ""
    candidates: list[str] = field(default_factory=list)

    @property
    def routed(self) -> bool:
        return self.source is not None and self.source.available

    def to_dict(self) -> dict:
        return {"comment_id": self.comment_id, "discipline": self.discipline,
                "adapter": self.source.adapter_name if self.source else "",
                "routed": self.routed, "reason": self.reason, "needed": self.needed,
                "candidates": self.candidates}


class Router:
    """Decides which adapter a municipal comment has to be worked in.

    Discipline comes from the department that wrote the comment; the *source*
    comes from which open drawing actually contains the element it names.  A
    comment for a discipline whose adapter is not available does not vanish -
    it is routed nowhere, with the adapter's own reason attached, and the
    orchestrator turns that into an open item.
    """

    def __init__(self, workspace: Workspace):
        self.workspace = workspace

    def discipline_of(self, comment: MunicipalComment) -> str:
        if comment.affected_discipline in ("civil",):
            return "drainage"
        return DEPARTMENT_DISCIPLINE.get(comment.department, ARCHITECTURE)

    def route(self, comment: MunicipalComment) -> Routing:
        discipline = self.discipline_of(comment)
        routing = Routing(comment.comment_id, discipline)

        if comment.requirement is None:
            # Nothing geometric to find: a document/annotation demand belongs to
            # whichever source holds the drawing, or to the document adapter.
            routing.source = self._first_available(discipline) or self._primary_source()
            if routing.source is None:
                routing.reason = "no source is open"
            return routing

        candidates = self.workspace.for_discipline(discipline) or (
            [entry for entry in self.workspace.opened if entry.available])
        routing.candidates = [entry.adapter_name for entry in candidates]
        for entry in candidates:
            if self._holds(entry, comment):
                routing.source = entry
                return routing

        blocked = [entry for entry in self.workspace.unavailable()
                   if discipline in (entry.status.disciplines if entry.status else ())]
        if blocked:
            routing.reason = blocked[0].error or "the adapter for this discipline is unavailable"
            routing.needed = f"the {blocked[0].adapter_name} adapter, or the drawing that holds this element"
            return routing
        if candidates:
            routing.source = candidates[0]
            routing.reason = "no open drawing contains the element the comment names"
        else:
            routing.reason = f"no source is open for {discipline}"
            routing.needed = f"a drawing for {discipline}"
        return routing

    # ------------------------------------------------------------------
    def _holds(self, entry: OpenSource, comment: MunicipalComment) -> bool:
        """Does this source actually contain what the comment points at?"""
        from ..mapping import ElementMapper
        from ..models import Resolution

        try:
            mapping = ElementMapper(entry.driver).map_comment(comment)
        except DrawingAPIError:
            return False
        return mapping.resolution is not Resolution.NOT_FOUND

    def _first_available(self, discipline: str) -> OpenSource | None:
        found = self.workspace.for_discipline(discipline)
        return found[0] if found else None

    def _primary_source(self) -> OpenSource | None:
        primary = self.workspace.primary()
        return next((entry for entry in self.workspace.opened if entry.driver is primary), None)


__all__ = ["AdapterRegistry", "OpenSource", "Router", "Routing", "Workspace",
           "default_registry", "DOCUMENTS"]
