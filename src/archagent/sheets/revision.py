"""Sheet revision tracking (spec §35).

Keeps the latest revision of each sheet number and the ones it superseded -
the same "never assume the newest is the only one that ever existed" caution
as the permit lifecycle engine, applied to drawing sheets instead of comments.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .model import Revision, Sheet


@dataclass
class SheetHistory:
    sheet_number: str
    revisions: list[Sheet] = field(default_factory=list)

    @property
    def latest(self) -> Sheet | None:
        return self.revisions[-1] if self.revisions else None


class SheetIndex:
    """Every sheet ever seen across versions, keyed by sheet number."""

    def __init__(self) -> None:
        self.history: dict[str, SheetHistory] = {}
        self._revision_notes: dict[str, list[Revision]] = {}

    def add(self, sheet: Sheet) -> Sheet:
        record = self.history.setdefault(sheet.sheet_number, SheetHistory(sheet.sheet_number))
        record.revisions.append(sheet)
        return sheet

    def latest(self, sheet_number: str) -> Sheet | None:
        record = self.history.get(sheet_number)
        return record.latest if record else None

    def superseded(self, sheet_number: str) -> list[Sheet]:
        record = self.history.get(sheet_number)
        return record.revisions[:-1] if record else []

    def all_latest(self) -> list[Sheet]:
        return [record.latest for record in self.history.values() if record.latest]

    # ------------------------------------------------------------------
    def add_revision_note(self, revision: Revision) -> Revision:
        """Record what changed in one revision, alongside the sheet itself."""
        self._revision_notes.setdefault(revision.sheet_number, []).append(revision)
        return revision

    def notes_for(self, sheet_number: str) -> list[Revision]:
        return list(self._revision_notes.get(sheet_number, []))
