"""The reference adapter: a JSON plan model on disk.

It is what the tests, the demos and the mock host run on, and it is the
worked example for anyone writing a new adapter.
"""

from __future__ import annotations

from ..drawing.api import DrawingDriver
from ..drawing.json_model import JSONModelDriver
from .base import (
    ARCHITECTURE,
    EDIT,
    MEASURE,
    PREVIEW,
    READ,
    TRAFFIC,
    VERSION,
    AdapterUnavailable,
    BaseAdapter,
    SourceRef,
)


class JsonAdapter(BaseAdapter):
    name = "json"
    disciplines = (ARCHITECTURE, TRAFFIC)
    capabilities = (READ, MEASURE, EDIT, PREVIEW, VERSION)
    suffixes = (".json",)

    def detects(self, source: SourceRef) -> bool:
        if source.kind != "file" or source.suffix not in self.suffixes:
            return False
        try:
            import json

            return "elements" in json.loads(source.path.read_text(encoding="utf-8"))
        except Exception:
            return False

    def open(self, source: SourceRef) -> DrawingDriver:
        if not self.detects(source):
            raise AdapterUnavailable(f"{source.location} is not a JSON plan model")
        return JSONModelDriver.load(source.location)
