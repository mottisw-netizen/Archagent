"""Language support for reading municipal comments.

The comment parser is lexicon-driven: :func:`for_text` picks the lexicon from
the text itself, so a project may mix Hebrew comments with Latin element marks
(P12, A-101) without configuration.
"""

from __future__ import annotations

from .base import Lexicon, clean, detect_script, parse_number
from .english import ENGLISH
from .hebrew import HEBREW

LEXICONS: dict[str, Lexicon] = {lexicon.code: lexicon for lexicon in (ENGLISH, HEBREW)}
DEFAULT = ENGLISH


def get(code: str) -> Lexicon:
    return LEXICONS.get(code, DEFAULT)


def for_text(text: str) -> Lexicon:
    """The lexicon that matches the script the comment is written in."""
    return LEXICONS.get(detect_script(text), DEFAULT)


__all__ = ["ENGLISH", "HEBREW", "LEXICONS", "DEFAULT", "Lexicon", "clean",
           "detect_script", "for_text", "get", "parse_number"]
