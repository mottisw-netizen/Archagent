"""What an adapter is.

A permit package is never one file. The architectural model is Revit, traffic
and roads arrive as consultant DWGs, the environmental appendix is a PDF report
- and one municipal comment can touch any of them.  So the agent does not talk
to Revit; it talks to *adapters*, and an adapter knows how to open one kind of
source and hand back the same :class:`DrawingDriver` the pipeline already uses.

Adding Archicad, AutoCAD or Civil 3D later means adding an adapter, not
touching the planner, the constraint engine, the validator or the report.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from ..drawing.api import DrawingAPIError, DrawingDriver

# ----------------------------------------------------------------------
# disciplines - the vocabulary the router uses
# ----------------------------------------------------------------------
ARCHITECTURE = "architecture"
STRUCTURE = "structure"
TRAFFIC = "traffic"
ROADS = "roads"
DRAINAGE = "drainage"
LANDSCAPE = "landscape"
ENVIRONMENT = "environment"
ACCESSIBILITY = "accessibility"
FIRE = "fire"
DOCUMENTS = "documents"

ALL_DISCIPLINES = (ARCHITECTURE, STRUCTURE, TRAFFIC, ROADS, DRAINAGE, LANDSCAPE,
                   ENVIRONMENT, ACCESSIBILITY, FIRE, DOCUMENTS)

#: Which discipline a municipal department's comments usually belong to.
DEPARTMENT_DISCIPLINE = {
    "Planning": ARCHITECTURE,
    "Architecture": ARCHITECTURE,
    "Licensing": ARCHITECTURE,
    "Engineering": STRUCTURE,
    "Traffic": TRAFFIC,
    "Parking": TRAFFIC,
    "Accessibility": ACCESSIBILITY,
    "Fire Safety": FIRE,
    "Sanitation": DRAINAGE,
    "Water": DRAINAGE,
    "Drainage": DRAINAGE,
    "Infrastructure": ROADS,
    "Landscaping": LANDSCAPE,
    "Environment": ENVIRONMENT,
}

# ----------------------------------------------------------------------
# capabilities - what an adapter can actually do, stated rather than assumed
# ----------------------------------------------------------------------
READ = "read"          # list elements and their properties
MEASURE = "measure"    # produce a measurement a report can cite
EDIT = "edit"          # change the drawing
PREVIEW = "preview"    # render a before/after view
VERSION = "version"    # write an immutable new version
MARKUP = "markup"      # produce instructions for a human instead of editing


class AdapterUnavailable(DrawingAPIError):
    """The adapter exists but cannot serve this source right now."""


@dataclass
class SourceRef:
    """One thing an adapter can open: a file, or a live host."""

    kind: str                     # "file" | "host"
    location: str                 # path or URL
    discipline: str = ARCHITECTURE
    role: str = "source_model"
    options: dict = field(default_factory=dict)

    @property
    def path(self) -> Path | None:
        return Path(self.location) if self.kind == "file" else None

    @property
    def suffix(self) -> str:
        return (self.path.suffix.casefold() if self.path else "")

    def to_dict(self) -> dict:
        return {"kind": self.kind, "location": self.location,
                "discipline": self.discipline, "role": self.role}

    #: URL scheme -> the ``host`` option an adapter's ``detects()`` matches on.
    HOST_SCHEMES = {"revit": "revit", "autocad": "autocad", "civil3d": "civil3d",
                    "dwg": "autocad"}

    @classmethod
    def parse(cls, value: str, discipline: str = ARCHITECTURE, **options) -> "SourceRef":
        """A file path, or ``<tool>://host:port`` for a live host (``revit://``,
        ``autocad://``, ``civil3d://``, or a bare ``http://…``)."""
        text = str(value)
        if text.startswith(("http://", "https://")):
            return cls("host", text, discipline, options=options)
        for scheme, host in cls.HOST_SCHEMES.items():
            prefix = f"{scheme}://"
            if text.startswith(prefix):
                return cls("host", "http://" + text[len(prefix):], discipline,
                           options={**options, "host": host})
        return cls("file", text, discipline, options=options)


@dataclass
class AdapterStatus:
    """Whether an adapter can be used, and if not, exactly what is missing."""

    name: str
    available: bool
    reason: str = ""
    capabilities: tuple[str, ...] = ()
    disciplines: tuple[str, ...] = ()
    detail: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"name": self.name, "available": self.available, "reason": self.reason,
                "capabilities": list(self.capabilities),
                "disciplines": list(self.disciplines), "detail": self.detail}


@runtime_checkable
class Adapter(Protocol):
    """One planning tool, behind one interface."""

    name: str
    disciplines: tuple[str, ...]
    capabilities: tuple[str, ...]
    suffixes: tuple[str, ...]

    def detects(self, source: SourceRef) -> bool:
        """Can this adapter open that source?"""

    def status(self, source: SourceRef | None = None) -> AdapterStatus:
        """Is it usable here and now - and if not, what is missing?"""

    def open(self, source: SourceRef) -> DrawingDriver:
        """Open the source and return a driver the pipeline can use."""


class BaseAdapter:
    """Shared plumbing; every adapter states its own capabilities."""

    name = "base"
    disciplines: tuple[str, ...] = ()
    capabilities: tuple[str, ...] = ()
    suffixes: tuple[str, ...] = ()

    def detects(self, source: SourceRef) -> bool:
        return source.kind == "file" and source.suffix in self.suffixes

    def status(self, source: SourceRef | None = None) -> AdapterStatus:
        return AdapterStatus(self.name, True, "", self.capabilities, self.disciplines)

    def open(self, source: SourceRef) -> DrawingDriver:  # pragma: no cover - abstract
        raise NotImplementedError

    def can(self, capability: str) -> bool:
        return capability in self.capabilities

    def covers(self, discipline: str) -> bool:
        return discipline in self.disciplines

    def describe(self) -> dict:
        return {"name": self.name, "disciplines": list(self.disciplines),
                "capabilities": list(self.capabilities), "suffixes": list(self.suffixes)}


def unavailable(name: str, reason: str, capabilities=(), disciplines=(), **detail) -> AdapterStatus:
    return AdapterStatus(name, False, reason, tuple(capabilities), tuple(disciplines), detail)


def _unused(*args: Any) -> None:  # pragma: no cover - keeps linters honest
    return None
