"""National (Israeli) planning/building regulation defaults.

The Core Requirement Engine layer of :mod:`archagent.constraints`, alongside
municipal-comment-derived and "do not break the approved design" constraints
(:func:`archagent.constraints.derive_implicit_constraints`). Every number in
this module is sourced to a specific, citable Israeli statute or regulation
- not to any one municipality's spec document, and not guessed. An authority
profile (:mod:`archagent.authority`) may still require something stricter for
a specific project; when it does not, these are the actual floor the engine
checks against, so a real violation is never missed just because no comment
happened to mention it (spec §7.1's own point: the schedule/comment is never
the only source of truth - the model itself is measured).

Emitted as ``source="Planning Regulation"`` - already the second-strongest
rank in :data:`archagent.constraints.SOURCE_RANK` (weaker only than an
explicit municipal comment) and already routed to
:class:`~archagent.models.Priority.CRITICAL` by
:func:`archagent.constraints.priority_for`. Nothing about conflict ranking or
priority needed to change to wire this in - the constraint engine already
anticipated a "Planning Regulation" source; this module is the first thing
to actually emit one.

Scope, stated plainly: this checks what the generic
:class:`~archagent.drawing.api.DrawingDriver` model can actually measure
today - element width/length via ``driver.measure()`` - not the typed
:mod:`archagent.traffic` semantic objects (``ParkingSpace``, ``Ramp``,
``TurningPath``), which have no code path that ever constructs them from a
real project (see ``docs/ARCHITECTURE_MAP.md``). Ramp slope, turning radius
and drive-aisle width are NOT covered here yet: slope is not a metric the
generic driver model can measure at all (only the typed, unwired ``Ramp``
dataclass carries one), and a defensible national turning-radius number was
not found with a citable public source at the time this was written - see
``docs/NATIONAL_VS_LOCAL_STANDARDS.md`` for the full parameter-by-parameter
survey and what each gap actually is.
"""

from __future__ import annotations

from dataclasses import dataclass

from .constraints import ConstraintLedger, priority_for
from .drawing.api import DrawingAPIError, DrawingDriver
from .lang.messages import DEFAULT as DEFAULT_MESSAGES, Messages
from .models import Constraint, Requirement


@dataclass(frozen=True)
class NationalStandard:
    value: float
    unit: str
    source: str


#: Planning and Building Regulations (Installation of Parking Spaces),
#: 5743-1983 (תקנות התכנון והבניה (התקנת מקומות חניה), תשמ"ג-1983), regulation 2.
PARKING_MIN_WIDTH = NationalStandard(
    2.30, "m", 'תקנות התכנון והבניה (התקנת מקומות חניה), תשמ"ג-1983, תקנה 2 - '
    "רוחב מזערי (ללא קיר/עמוד צמוד)")
PARKING_MIN_WIDTH_ACCESSIBLE = NationalStandard(
    3.00, "m", 'תקנות התכנון והבניה (התקנת מקומות חניה), תשמ"ג-1983 - '
    "רוחב מזערי לחניית נכים")
#: The shortest of the regulation's three length scenarios (against a curb,
#: with clearance beyond it) - used as the safe floor when the generic
#: driver model has no "what is at the far end of this space" property to
#: pick the stricter against-a-wall (5.00 m) or open (4.75 m) figure from.
#: See the module docstring: this never guesses which scenario applies.
PARKING_MIN_LENGTH = NationalStandard(
    4.25, "m", 'תקנות התכנון והבניה (התקנת מקומות חניה), תשמ"ג-1983, תקנה 2 - '
    "אורך מזערי (המקרה המחמיר פחות מבין השלושה שבתקנה)")


def _tiered_width(props: dict) -> NationalStandard:
    if props.get("category") == "accessible":
        return PARKING_MIN_WIDTH_ACCESSIBLE
    return PARKING_MIN_WIDTH


def derive_national_constraints(driver: DrawingDriver, ledger: ConstraintLedger,
                                messages: Messages | None = None) -> list[Constraint]:
    """Statutory minimums for whatever the drawing model actually contains.

    Mirrors :func:`archagent.constraints.derive_implicit_constraints`'s shape
    on purpose - same "skip what cannot be measured, never fabricate" rule,
    same ledger-add pattern - so the two are easy to read side by side.
    """
    m = messages or DEFAULT_MESSAGES
    created: list[Constraint] = []

    def add(rule: str, test: Requirement) -> None:
        created.append(ledger.add(Constraint(
            constraint_id=ledger.next_id("N"),
            source="Planning Regulation",
            rule=rule,
            priority=priority_for(rule, "Planning Regulation"),
            test=test,
            confidence=1.0,
        )))

    for element in getattr(driver, "elements", list)():
        if element.get("type") != "parking":
            continue
        props = element.get("properties", {}) or {}
        element_id = element["id"]
        label = element.get("label", element_id)

        width_standard = _tiered_width(props)
        try:
            width = driver.measure({"element_id": element_id}, "width")
        except DrawingAPIError:
            width = None
        if width is not None:
            add(m.t("national_standard", element=label, parameter=m.metric("width"),
                    value=m.value(width_standard.value), source=width_standard.source),
                Requirement(subject={"element_id": element_id, "label": label},
                           metric="width", op=">=", value=width_standard.value,
                           unit=width_standard.unit))

        try:
            length = driver.measure({"element_id": element_id}, "length")
        except DrawingAPIError:
            length = None
        if length is not None:
            add(m.t("national_standard", element=label, parameter=m.metric("length"),
                    value=m.value(PARKING_MIN_LENGTH.value), source=PARKING_MIN_LENGTH.source),
                Requirement(subject={"element_id": element_id, "label": label},
                           metric="length", op=">=", value=PARKING_MIN_LENGTH.value,
                           unit=PARKING_MIN_LENGTH.unit))

    return created
