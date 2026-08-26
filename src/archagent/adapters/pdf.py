"""Reports, appendices and submitted sheets.

Plenty of a permit package is not a drawing: an environmental report, a traffic
survey, an area schedule, the authority's own comment sheet.  Those comments are
real and must be answered - but they are answered with text and evidence, not by
moving geometry, so this adapter never claims to edit.
"""

from __future__ import annotations

from ..drawing.api import DrawingDriver
from .base import (
    DOCUMENTS,
    ENVIRONMENT,
    MARKUP,
    READ,
    AdapterStatus,
    AdapterUnavailable,
    BaseAdapter,
    SourceRef,
    unavailable,
)

REASON = ("documents are read for evidence and marked up for a human; nothing in a "
          "PDF is edited by the agent (SKILL.md 3.3, 1.2)")


class PdfAdapter(BaseAdapter):
    name = "pdf"
    disciplines = (DOCUMENTS, ENVIRONMENT)
    capabilities = (READ, MARKUP)
    suffixes = (".pdf", ".md", ".txt", ".docx", ".xlsx")

    def status(self, source: SourceRef | None = None) -> AdapterStatus:
        if source is None or self.detects(source):
            return AdapterStatus(self.name, True, REASON, self.capabilities, self.disciplines)
        return unavailable(self.name, "not a document source", self.capabilities,
                           self.disciplines)

    def open(self, source: SourceRef) -> DrawingDriver:
        raise AdapterUnavailable(REASON)

    def read(self, source: SourceRef) -> str:
        """The text of the document, for evidence and for comment extraction."""
        from ..ingest import read_text

        text, status = read_text(source.path)
        if status != "ok" and not text:
            raise AdapterUnavailable(f"{source.location}: {status}")
        return text
