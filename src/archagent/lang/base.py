"""Language-agnostic machinery for reading municipal comments.

A :class:`Lexicon` describes one language: how its departments are named, how
it spells a metric, how it expresses "at least" and "at most", which verbs
demand an increase, and how numbers and units are written.  The parser in
:mod:`archagent.comments` is built from a lexicon, so adding a language means
adding a lexicon - not another parser.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Iterable

#: Characters that carry no meaning for parsing but appear in real documents.
_INVISIBLE = dict.fromkeys(map(ord, "‎‏‪‫‬⁦⁧⁨⁩­"))

#: Hebrew geresh/gershayim and the maqaf, normalised to their ASCII shapes.
_PUNCTUATION = {
    "׳": "'", "״": '"', "’": "'", "‘": "'",
    "“": '"', "”": '"', "־": "-", "–": "-", "—": "-",
}

_NUMBER_TOKEN = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:[.,]\d+)?")


def clean(text: str) -> str:
    """Normalise a comment for matching, without altering its meaning."""
    text = unicodedata.normalize("NFC", text).translate(_INVISIBLE)
    for source, target in _PUNCTUATION.items():
        text = text.replace(source, target)
    return " ".join(text.split())


def parse_number(raw: str) -> float:
    """Read a number written the way people write it.

    ``1,850`` is one thousand eight hundred and fifty; ``2,50`` is two and a
    half.  Guessing wrong here would put a decimal point in a floor area, so
    the two forms are separated explicitly.
    """
    raw = raw.strip()
    if re.fullmatch(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?", raw):
        return float(raw.replace(",", ""))
    return float(raw.replace(",", "."))


def alternation(words: Iterable[str], prefix: str = "") -> str:
    """Longest-first regex alternation, each entry allowed an optional prefix."""
    ordered = sorted({word for word in words}, key=len, reverse=True)
    return "|".join(f"(?:{prefix}{word})" for word in ordered)


@dataclass(frozen=True)
class Lexicon:
    """Everything the parser needs to know about one language."""

    code: str
    name: str
    #: surface form -> canonical (English) department name
    departments: dict[str, str]
    #: surface form (regex fragment) -> metric key understood by the drivers
    metrics: dict[str, str]
    #: surface form -> element type in the model
    elements: dict[str, str]
    #: surface form -> north/south/east/west
    directions: dict[str, str]
    at_least: str
    at_most: str
    increase_verbs: str
    decrease_verbs: str
    set_verbs: str
    #: how "to <value>" is written ("to 2.50", "ל-2.50")
    to_marker: str
    unit_pattern: str
    units: dict[str, str]
    statements: tuple[str, ...]
    #: surface form -> annotation action
    annotations: dict[str, str]
    annotation_verbs: str
    #: (regex, selector) pairs for counted things ("34 parking spaces")
    count_nouns: tuple[tuple[str, dict], ...]
    department_line: str
    comment_id_patterns: tuple[str, ...]
    label_patterns: tuple[str, ...]
    #: verbs that name the metric by themselves - "widen" means width
    implied_metrics: tuple[tuple[str, str, str], ...] = ()  # (verb regex, metric, op)
    #: optional word prefixes; Hebrew glues ב/ה/ו/כ/ל/מ/ש onto the next word
    prefix: str = ""
    #: does the direction come before the metric ("northern setback") or after
    #: it ("קו בניין צפוני")?  ``both`` tries either order.
    setback_order: str = "direction_first"
    number_pattern: str = r"(?P<value>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:[.,]\d+)?)"
    _cache: dict = field(default_factory=dict, repr=False, compare=False)

    # ------------------------------------------------------------------
    def metric_alternation(self) -> str:
        return alternation(self.metrics, self.prefix)

    def element_alternation(self) -> str:
        return alternation(self.elements, self.prefix)

    def direction_alternation(self) -> str:
        return alternation(self.directions, self.prefix)

    def annotation_alternation(self) -> str:
        return alternation(self.annotations, self.prefix)

    # ------------------------------------------------------------------
    def _canonical(self, table: dict[str, str], text: str) -> str | None:
        """Map a matched surface form back to its canonical key."""
        cleaned = clean(text).casefold()
        for surface in sorted(table, key=len, reverse=True):
            if re.search(surface, cleaned):
                return table[surface]
        return None

    def metric_of(self, text: str) -> str | None:
        return self._canonical(self.metrics, text)

    def element_of(self, text: str) -> str | None:
        return self._canonical(self.elements, text)

    def direction_of(self, text: str) -> str | None:
        return self._canonical(self.directions, text)

    def annotation_of(self, text: str) -> str | None:
        return self._canonical(self.annotations, text)

    def unit_of(self, raw: str | None) -> str:
        if not raw:
            return "m"
        cleaned = clean(raw).casefold().rstrip(".")
        for surface in sorted(self.units, key=len, reverse=True):
            if re.fullmatch(surface, cleaned) or cleaned.startswith(surface):
                return self.units[surface]
        return "m"

    def department_of(self, name: str, strict: bool = False) -> str | None:
        cleaned = clean(name).strip(":- ").casefold()
        if cleaned in self.departments:
            return self.departments[cleaned]
        if strict:
            return None
        for surface, canonical in self.departments.items():
            if surface in cleaned:
                return canonical
        return None

    def is_statement(self, text: str) -> bool:
        cleaned = clean(text).casefold().rstrip(".:! ")
        return any(re.fullmatch(word, cleaned) or cleaned.startswith(word)
                   for word in self.statements)

    def find_label(self, text: str) -> str | None:
        for pattern in self.label_patterns:
            match = re.search(pattern, clean(text))
            if match:
                return match.group("label").replace(" ", "").replace("_", "-")
        return None

    def compile(self, pattern: str, flags: int = re.I) -> re.Pattern:
        key = (pattern, flags)
        if key not in self._cache:
            self._cache[key] = re.compile(pattern, flags)
        return self._cache[key]


def detect_script(text: str) -> str:
    """Which writing system a comment is in - decided by the text, not a flag."""
    hebrew = sum(1 for ch in text if "֐" <= ch <= "׿")
    arabic = sum(1 for ch in text if "؀" <= ch <= "ۿ")
    latin = sum(1 for ch in text if ch.isalpha() and ch.isascii())
    if hebrew and hebrew >= latin:
        return "he"
    if arabic and arabic >= latin:
        return "ar"
    return "en"
