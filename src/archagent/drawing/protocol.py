"""The wire contract between Archagent and a live CAD host.

One protocol, two implementations: the Revit add-in (C#, in ``revit-addin/``)
and the mock host used by the tests.  Writing it down here - rather than in
each side - is what lets an Archicad or AutoCAD host join later without
touching anything above the driver.

Design decisions that the protocol encodes, because they are forced by Revit
and would otherwise leak into every caller:

* **Metres at the boundary.** Revit works internally in feet. Every length in
  this protocol is metres and every area is square metres; the host converts.
* **Stable ids.** Revit's ``ElementId`` is not stable across sessions, so the
  element id on the wire is the ``UniqueId`` GUID.
* **A plan is applied as one batch.** Revit only allows a transaction inside a
  single API context, so a transaction cannot stay open between HTTP calls.
  ``/apply`` therefore takes the whole action list: the host opens one
  transaction group, applies every action, and commits - or rolls the group
  back and reports which action failed. Half-applied plans cannot exist.
* **Simulation never touches the live document.** The driver takes a snapshot
  of the host's geometry, applies the plan to that snapshot locally, and
  measures there. The user's model is only written once, after the plan has
  been simulated and (in consultation mode) approved - and every number in the
  report is re-measured through the host afterwards.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Bumped when a request or response shape changes incompatibly; the minor
#: moves when an endpoint or a field is *added* (1.1 added ``/highlight``), and
#: a client only insists on the major - see :meth:`HostInfo.compatible`.
PROTOCOL_VERSION = "1.1"

#: Every length is metres, every area m²; the host converts from its own units.
UNIT_LENGTH = "m"
UNIT_AREA = "m2"

# ----------------------------------------------------------------------
# endpoints
# ----------------------------------------------------------------------
HEALTH = "/health"
FIND = "/find"
ELEMENT = "/element"
GEOMETRY = "/geometry"
PROPERTIES = "/properties"
SHEETS = "/sheets"
MEASURE = "/measure"
DISTANCE = "/distance"
OVERLAP = "/overlap"
CLEARANCE = "/clearance"
BEGIN = "/transaction/begin"
COMMIT = "/transaction/commit"
ROLLBACK = "/transaction/rollback"
APPLY = "/apply"          # one action, or a batch: {"actions": [...]}
EXPORT = "/export"
SAVE_AS = "/save_as"
CHANGES = "/changes"
HIGHLIGHT = "/highlight"   # select the changed elements in the host's own UI

READ_ENDPOINTS = (HEALTH, FIND, ELEMENT, GEOMETRY, PROPERTIES, SHEETS, MEASURE,
                  DISTANCE, OVERLAP, CLEARANCE, CHANGES)

#: Changes the view, not the document - so it needs no transaction and no plan.
UI_ENDPOINTS = (HIGHLIGHT,)

# ----------------------------------------------------------------------
# actions a plan may ask the host to perform
# ----------------------------------------------------------------------
MOVE = "move"
RESIZE = "resize"
ROTATE = "rotate"
DELETE = "delete"
CREATE = "create"
SET_TEXT = "set_text"
SET_PARAMETER = "set_parameter"
UPDATE_DIMENSION = "update_dimension"
UPDATE_SCHEDULE = "update_schedule"

ACTIONS = (MOVE, RESIZE, ROTATE, DELETE, CREATE, SET_TEXT, SET_PARAMETER,
           UPDATE_DIMENSION, UPDATE_SCHEDULE)

# ----------------------------------------------------------------------
# error codes - the host returns these; the driver maps them to exceptions
# ----------------------------------------------------------------------
ERR_NOT_FOUND = "element_not_found"
ERR_AMBIGUOUS = "ambiguous"
ERR_UNSUPPORTED = "unsupported"
ERR_NO_TRANSACTION = "no_transaction"
ERR_READ_ONLY = "read_only"
ERR_HOST = "host_error"
ERR_MEASUREMENT = "measurement_failed"
ERR_BUSY = "document_busy"

#: Categories the agent reasons about, and how a host maps them home.  A host
#: is free to add more; these are the ones the planner knows how to change.
CATEGORY_ALIASES = {
    "parking": ("Parking", "OST_Parking"),
    "building": ("Mass", "OST_Mass", "OST_Walls"),
    "wall": ("Walls", "OST_Walls"),
    "room": ("Rooms", "OST_Rooms"),
    "door": ("Doors", "OST_Doors"),
    "window": ("Windows", "OST_Windows"),
    "stair": ("Stairs", "OST_Stairs"),
    "railing": ("Railings", "OST_StairsRailing"),
    "floor": ("Floors", "OST_Floors"),
    "roof": ("Roofs", "OST_Roofs"),
    "column": ("Columns", "OST_Columns"),
    "driveway": ("Roads", "OST_Roads", "OST_Site"),
    "sidewalk": ("Site", "OST_Site"),
    "balcony": ("Floors", "OST_Floors"),
    "dimension": ("Dimensions", "OST_Dimensions"),
    "text": ("Text Notes", "OST_TextNotes"),
    "generic": ("Generic Models", "OST_GenericModel"),
}


@dataclass(frozen=True)
class HostInfo:
    """What a host reports about itself and the document it has open."""

    protocol: str
    host: str                 # "revit" | "archicad" | "mock"
    host_version: str
    document: str
    units: str = UNIT_LENGTH
    read_only: bool = False
    project_north: float = 0.0     # degrees clockwise from true north
    element_count: int = 0

    @classmethod
    def from_dict(cls, data: dict) -> "HostInfo":
        return cls(
            protocol=str(data.get("protocol", "")),
            host=str(data.get("host", "unknown")),
            host_version=str(data.get("host_version", "")),
            document=str(data.get("document", "")),
            units=str(data.get("units", UNIT_LENGTH)),
            read_only=bool(data.get("read_only", False)),
            project_north=float(data.get("project_north", 0.0) or 0.0),
            element_count=int(data.get("element_count", 0) or 0),
        )

    def compatible(self) -> bool:
        """Same major version is enough; minors add fields only."""
        return self.protocol.split(".")[0] == PROTOCOL_VERSION.split(".")[0]


def element_shape() -> dict:
    """The element document every host must return (documentation, not code).

    ``geometry.bbox`` is the axis-aligned bounding box **in plan**, in metres,
    in project coordinates with +x east and +y north - the same frame the
    planner and the previews use.
    """
    return {
        "id": "<stable unique id>",
        "category": "parking | wall | room | ...",
        "type_name": "<family / type name>",
        "name": "<element name>",
        "label": "<mark or number shown on the drawing>",
        "level": "<level name>",
        "sheet": "<sheet number the element appears on, if known>",
        "geometry": {"bbox": {"x": 0.0, "y": 0.0, "w": 0.0, "h": 0.0},
                     "elevation": 0.0, "height": 0.0, "rotation": 0.0},
        "properties": {"<parameter name>": "<value>"},
        "editable": True,
        "pinned": False,
        "workset": "<workset name>",
    }
