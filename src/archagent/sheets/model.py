"""Plan/sheet awareness (spec §35).

A permit package is not one drawing: a finding should be traceable to a sheet
(``A-101``, ``A-TR-02``, ``DR-01``) wherever possible, not only to an element
id that means nothing outside the model that produced it.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..models import Serialisable


@dataclass
class Sheet(Serialisable):
    sheet_number: str
    discipline: str = ""
    title: str = ""
    revision: str = ""
    date: str = ""
    scale: str = ""
    view: str = ""
    source: str = ""


@dataclass
class Revision(Serialisable):
    """One changelog entry for a sheet - who changed it, when, and why.

    ``Sheet.revision`` is just the label ("B") stamped on the sheet itself;
    this is the accompanying record a revision cloud/changelog would carry -
    kept as its own object because a sheet only ever has one current label,
    while its revision history can have many entries.
    """

    revision_id: str
    sheet_number: str
    number: str = ""
    date: str = ""
    description: str = ""
    author: str = ""
