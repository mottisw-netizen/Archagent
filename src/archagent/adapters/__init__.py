"""Adapters: one agent, many planning tools.

The permit package is multi-discipline - Revit for architecture, DWG for
traffic and roads, documents for the rest - so the agent talks to adapters, not
to a CAD program.  ``RevitAdapter`` is the first real implementation; the others
declare what they need before they can join.
"""

from .base import (
    ALL_DISCIPLINES,
    ARCHITECTURE,
    DEPARTMENT_DISCIPLINE,
    DOCUMENTS,
    DRAINAGE,
    EDIT,
    MARKUP,
    MEASURE,
    PREVIEW,
    READ,
    ROADS,
    TRAFFIC,
    VERSION,
    Adapter,
    AdapterStatus,
    AdapterUnavailable,
    BaseAdapter,
    SourceRef,
)
from .dwg import DwgAdapter
from .json_model import JsonAdapter
from .pdf import PdfAdapter
from .registry import (
    AdapterRegistry,
    OpenSource,
    Router,
    Routing,
    Workspace,
    default_registry,
)
from .revit import RevitAdapter

__all__ = [
    "ALL_DISCIPLINES", "ARCHITECTURE", "Adapter", "AdapterRegistry", "AdapterStatus",
    "AdapterUnavailable", "BaseAdapter", "DEPARTMENT_DISCIPLINE", "DOCUMENTS", "DRAINAGE",
    "DwgAdapter", "EDIT", "JsonAdapter", "MARKUP", "MEASURE", "OpenSource", "PREVIEW",
    "PdfAdapter", "READ", "ROADS", "RevitAdapter", "Router", "Routing", "SourceRef",
    "TRAFFIC", "VERSION", "Workspace", "default_registry",
]
