"""National (Israeli) planning/building regulation defaults.

The Core Requirement Engine layer of :mod:`archagent.constraints`, alongside
municipal-comment-derived and "do not break the approved design" constraints
(:func:`archagent.constraints.derive_implicit_constraints`). Every entry in
this module states plainly whether its number is confirmed against a
directly-read statute's own text (``confirmed=True``) or is a working
default whose likely source (usually ת"י 1918, an Israel Standard sold by
מכון התקנים and not freely published) could not be verified
(``confirmed=False``) - never conflate the two. An authority profile
(:mod:`archagent.authority`) may still require something stricter for a
specific project; when it does not, these are the actual floor the engine
checks against, so a real violation is never missed just because no comment
happened to mention it (spec §7.1's own point: the schedule/comment is never
the only source of truth - the model itself is measured).

A confirmed standard is emitted as ``source="Planning Regulation"`` - the
second-strongest rank in :data:`archagent.constraints.SOURCE_RANK` (weaker
only than an explicit municipal comment) and routed to
:class:`~archagent.models.Priority.CRITICAL` by
:func:`archagent.constraints.priority_for`. An unconfirmed one is emitted as
``source="Reference"`` instead - the weakest source rank, MEDIUM priority -
deliberately less authoritative than a real statute, because it is not
proven to be one yet. See ``docs/NATIONAL_VS_LOCAL_STANDARDS.md``'s
"Verified against primary source text" section for exactly what was checked,
including a real correction: the parking width/length figures below were
first wired citing this regulation's own "תקנה 2" as their source, and a
direct fetch of that regulation's actual text proved that citation wrong
(תקנה 2 only covers space *count* authority; the תוספת's own dimensions are
area-only - 25/60/100 m² - with no width/length breakdown at all). The
figures were not withdrawn - they are still real, sensible Israeli
parking-design numbers - but they are now honestly marked unconfirmed rather
than falsely cited.

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
    #: True only when this figure was confirmed against a directly-read
    #: statute's own text - never set True from a search-result summary.
    confirmed: bool = True


#: A direct fetch of תקנות התכנון והבניה (התקנת מקומות חניה), תשמ"ג-1983
#: (regulation 2 and the whole תוספת) found NO width/length dimensions
#: anywhere in it - only space *count* rules and area-only figures (25/60/
#: 100 m² per vehicle type). These numbers are still real, standard Israeli
#: parking-space dimensions - plausibly from ת"י 1918, which is paywalled -
#: but that origin is unconfirmed, so `confirmed=False` and the source text
#: says so rather than citing a clause that does not actually contain them.
PARKING_MIN_WIDTH = NationalStandard(
    2.30, "m", 'מקור מדויק לא אומת מול טקסט חוק חופשי - קרוב לוודאי ת"י 1918 '
    '(בתשלום). נבדק ונשלל כמקור: תקנות התכנון והבניה (התקנת מקומות חניה), '
    'תשמ"ג-1983 - רוחב מזערי (ללא קיר/עמוד צמוד)', confirmed=False)
PARKING_MIN_WIDTH_ACCESSIBLE = NationalStandard(
    3.00, "m", 'מקור מדויק לא אומת מול טקסט חוק חופשי - קרוב לוודאי ת"י 1918 '
    '(בתשלום). נבדק ונשלל כמקור: תקנות התכנון והבניה (התקנת מקומות חניה), '
    'תשמ"ג-1983 - רוחב מזערי לחניית נכים', confirmed=False)
#: The shortest of the three length scenarios commonly cited for Israeli
#: parking design (against a curb, with clearance beyond it) - used as the
#: safe floor when the generic driver model has no "what is at the far end
#: of this space" property to pick the stricter against-a-wall (5.00 m) or
#: open (4.75 m) figure from. See the module docstring: this never guesses
#: which scenario applies - and, like the width figures, its exact statutory
#: origin is unconfirmed (same negative result from the same regulation).
PARKING_MIN_LENGTH = NationalStandard(
    4.25, "m", 'מקור מדויק לא אומת מול טקסט חוק חופשי - קרוב לוודאי ת"י 1918 '
    '(בתשלום). נבדק ונשלל כמקור: תקנות התכנון והבניה (התקנת מקומות חניה), '
    'תשמ"ג-1983 - אורך מזערי', confirmed=False)


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

    def add(rule: str, test: Requirement, standard: NationalStandard) -> None:
        # A confirmed statute outranks everything but an explicit municipal
        # comment (SOURCE_RANK); an unconfirmed one is honestly the weakest
        # source - real enough to keep checking, not proven enough to
        # override an approved design or a project requirement.
        source = "Planning Regulation" if standard.confirmed else "Reference"
        created.append(ledger.add(Constraint(
            constraint_id=ledger.next_id("N"),
            source=source,
            rule=rule,
            priority=priority_for(rule, source),
            test=test,
            confidence=1.0 if standard.confirmed else 0.6,
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
                           unit=width_standard.unit),
                width_standard)

        try:
            length = driver.measure({"element_id": element_id}, "length")
        except DrawingAPIError:
            length = None
        if length is not None:
            add(m.t("national_standard", element=label, parameter=m.metric("length"),
                    value=m.value(PARKING_MIN_LENGTH.value), source=PARKING_MIN_LENGTH.source),
                Requirement(subject={"element_id": element_id, "label": label},
                           metric="length", op=">=", value=PARKING_MIN_LENGTH.value,
                           unit=PARKING_MIN_LENGTH.unit),
                PARKING_MIN_LENGTH)

    return created
