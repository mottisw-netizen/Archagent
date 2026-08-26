"""The audit log (SKILL.md 16.2): one JSON line per event."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import now


class AuditLog:
    """Append-only JSONL log.  ``AuditLog.null()`` keeps events in memory."""

    def __init__(self, path: Path | None):
        self.path = Path(path) if path else None
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.events: list[dict] = []

    @classmethod
    def null(cls) -> "AuditLog":
        return cls(None)

    def write(self, actor: str, event: str, **fields: Any) -> dict:
        record = {"ts": now(), "actor": actor, "event": event}
        record.update({k: v for k, v in fields.items() if v is not None})
        self.events.append(record)
        if self.path:
            with open(self.path, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        return record

    def of_kind(self, event: str) -> list[dict]:
        return [e for e in self.events if e["event"] == event]
