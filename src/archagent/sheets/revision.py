"""Sheet revision tracking (spec §35).

Keeps the latest revision of each sheet number and the ones it superseded -
the same "never assume the newest is the only one that ever existed" caution
as the permit lifecycle engine, applied to drawing sheets instead of comments.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .model import Sheet


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
