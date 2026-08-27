"""The shared site/civil topology model (Petah Tikva spec §9-10).

Roads/drainage comments cannot be handled as generic DWG entities: a curb, a
sidewalk, a municipal drain and a detention chamber are different things with
different relationships to each other ("sidewalk drains_to road", "detention
chamber overflows_to municipal drain"). :class:`SiteElement` is one shared,
discipline-neutral shape for all of them; :class:`SiteRelation` records the
relationships spec §10 lists as examples, verbatim as a subject/relation/object
triple rather than as a bespoke Python attribute per relation.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..models import Serialisable

#: The site/civil object types of spec §10. A SiteElement's ``kind`` should
#: be one of these, but the model does not enforce it - an authority profile
#: or an adapter may introduce a new kind without a code change here.
ELEMENT_KINDS = (
    "site_surface", "contour", "spot_elevation", "road", "road_edge", "sidewalk",
    "curb", "dropped_curb", "driveway", "ramp", "plot_boundary", "municipal_drain",
    "drainage_pipe", "catch_basin", "drainage_chamber", "detention_chamber",
    "settling_chamber", "overflow", "drainage_outlet", "landscape_zone",
    "paved_area", "basement", "tree",
)

#: Relation vocabulary drawn directly from spec §10's own examples.
RELATION_KINDS = (
    "drains_to", "overflows_to", "crosses", "references", "connects_to",
)


@dataclass
class SiteElement(Serialisable):
    element_id: str
    kind: str
    label: str = ""
    properties: dict = field(default_factory=dict)
    sheet: str = ""


@dataclass
class SiteRelation(Serialisable):
    """e.g. ``sidewalk drains_to road``, ``municipal_drain crosses plot``."""

    subject: str
    relation: str
    object: str


@dataclass
class SiteTopology:
    elements: dict[str, SiteElement] = field(default_factory=dict)
    relations: list[SiteRelation] = field(default_factory=list)

    def add(self, element: SiteElement) -> SiteElement:
        self.elements[element.element_id] = element
        return element

    def relate(self, subject: str, relation: str, obj: str) -> SiteRelation:
        if relation not in RELATION_KINDS:
            raise ValueError(f"unknown site relation: {relation!r}")
        record = SiteRelation(subject=subject, relation=relation, object=obj)
        if record not in self.relations:
            self.relations.append(record)
        return record

    def related(self, subject: str, relation: str | None = None) -> list[SiteRelation]:
        return [r for r in self.relations if r.subject == subject
               and (relation is None or r.relation == relation)]

    def of_kind(self, kind: str) -> list[SiteElement]:
        return [element for element in self.elements.values() if element.kind == kind]
