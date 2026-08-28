"""National (Israeli) planning/building regulation defaults.

The Core Requirement Engine layer of :mod:`archagent.constraints`, alongside
municipal-comment-derived and "do not break the approved design" constraints
(:func:`archagent.constraints.derive_implicit_constraints`). Every entry in
this module states plainly what kind of source actually backs its number -
never conflate a proven statute with a proven guideline with a plausible
guess. An authority profile (:mod:`archagent.authority`) may still require
something stricter for a specific project; when it does not, these are the
actual floor the engine checks against, so a real violation is never missed
just because no comment happened to mention it (spec §7.1's own point: the
schedule/comment is never the only source of truth - the model itself is
measured).

:class:`NationalStandard.basis` has three honest values:

- ``"statute"`` - confirmed by directly reading a Knesset-level regulation's
  own text. Emitted ``source="Planning Regulation"`` - CRITICAL priority,
  second-strongest source rank (§3.4 SOURCE_RANK), weaker only than an
  explicit municipal comment.
- ``"guideline"`` - confirmed by directly reading a ministry-published
  planning guideline's own text (e.g. a gov.il PDF) - real and citable, but
  advisory rather than statutory. Emitted ``source="Planning Guideline"`` -
  same source rank as a project requirement, MEDIUM priority by default
  (not automatically CRITICAL the way a statute is).
- ``"unconfirmed"`` - a working default whose likely origin (usually ת"י
  1918, an Israel Standard sold by מכון התקנים and not freely published)
  could not be verified against primary text. Emitted ``source="Reference"``
  - the weakest source rank, MEDIUM priority, lower confidence (0.6).

No entry may claim ``"statute"`` or ``"guideline"`` from a search-result
summary alone - only from a session that actually opened and read the
document. See ``docs/NATIONAL_VS_LOCAL_STANDARDS.md``'s "Verified against
primary source text" section for exactly what was checked, including a real
correction this module went through: the parking width/length figures below
were first wired citing תקנות התכנון והבניה (התקנת מקומות חניה), תשמ"ג-1983,
תקנה 2 as "statute", and a direct fetch of that regulation's actual text
proved the citation wrong - תקנה 2 only covers space *count* authority; the
תוספת's own dimensions are area-only (25/60/100 m²), with no width/length
breakdown at all. The figures were not withdrawn - they are still real,
sensible Israeli parking-design numbers, plausibly from ת"י 1918 - but they
are now honestly marked ``"unconfirmed"`` rather than falsely cited as
statute.

Scope, stated plainly: this checks what the generic
:class:`~archagent.drawing.api.DrawingDriver` model can actually measure
today - element width/length via ``driver.measure()`` - not the typed
:mod:`archagent.traffic`/:mod:`archagent.site` semantic objects
(``ParkingSpace``, ``Ramp``, ``TurningPath``, ``Road``, ``Curb``), which have
no code path that ever constructs them from a real project (see
``docs/ARCHITECTURE_MAP.md``). This is also why several *confirmed* figures
found in the same research pass are still not wired here: ramp slope and
turning radius have no matching driver-measurable metric or element type at
all (no "slope" metric, no "turning path" element type); general curb height
has a real confirmed ceiling (10/15 cm by street type) that would falsely
flag a legitimate 15 cm *accessible bus-stop* curb (a real, confirmed floor
from the same research pass) if applied blindly, because the drawing model
has no property distinguishing a bus-stop curb from any other - wiring
either without a way to tell them apart would produce wrong violations, so
neither is wired; see the survey doc for the specifics of each gap.
"""

from __future__ import annotations

from dataclasses import dataclass

from .constraints import ConstraintLedger, priority_for
from .drawing.api import DrawingAPIError, DrawingDriver
from .lang.messages import DEFAULT as DEFAULT_MESSAGES, Messages
from .models import Constraint, Requirement

_SOURCE_BY_BASIS = {
    "statute": "Planning Regulation",
    "guideline": "Planning Guideline",
    "unconfirmed": "Reference",
}
_CONFIDENCE_BY_BASIS = {"statute": 1.0, "guideline": 1.0, "unconfirmed": 0.6}


@dataclass(frozen=True)
class NationalStandard:
    value: float
    unit: str
    source: str
    #: "statute" | "guideline" | "unconfirmed" - see the module docstring.
    #: Never "statute" or "guideline" without having read the actual text.
    basis: str = "unconfirmed"

    def __post_init__(self) -> None:
        if self.basis not in _SOURCE_BY_BASIS:
            raise ValueError(f"unknown basis: {self.basis!r}")


#: A direct fetch of תקנות התכנון והבניה (התקנת מקומות חניה), תשמ"ג-1983
#: (regulation 2 and the whole תוספת) found NO width/length dimensions
#: anywhere in it - only space *count* rules and area-only figures (25/60/
#: 100 m² per vehicle type). These numbers are still real, standard Israeli
#: parking-space dimensions - plausibly from ת"י 1918, which is paywalled -
#: but that origin is unconfirmed, so basis="unconfirmed" and the source
#: text says so rather than citing a clause that does not actually contain
#: them.
PARKING_MIN_WIDTH = NationalStandard(
    2.30, "m", 'מקור מדויק לא אומת מול טקסט חוק חופשי - קרוב לוודאי ת"י 1918 '
    '(בתשלום). נבדק ונשלל כמקור: תקנות התכנון והבניה (התקנת מקומות חניה), '
    'תשמ"ג-1983 - רוחב מזערי (ללא קיר/עמוד צמוד)')
PARKING_MIN_WIDTH_ACCESSIBLE = NationalStandard(
    3.00, "m", 'מקור מדויק לא אומת מול טקסט חוק חופשי - קרוב לוודאי ת"י 1918 '
    '(בתשלום). נבדק ונשלל כמקור: תקנות התכנון והבניה (התקנת מקומות חניה), '
    'תשמ"ג-1983 - רוחב מזערי לחניית נכים')
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
    'תשמ"ג-1983 - אורך מזערי')

#: Ministry parking design guidelines PDF (gov.il), p. 61, just before
#: "רדיוסים בפניות" - confirmed by direct download and text extraction
#: (WebFetch could not render the PDF; a local `pypdf` pass could). The
#: shorter, one-way figure is used as the safe floor when the drawing model
#: has no "is this aisle one-way or two-way" property, the same
#: never-guess-the-scenario approach as the parking length floor above.
DRIVEWAY_MIN_WIDTH_ONE_WAY = NationalStandard(
    3.50, "m", 'הנחיות משרד לתכנון חניה (gov.il), עמ\' 61 - רוחב מסדרון '
    "מזערי, תנועה חד-סטרית", basis="guideline")
DRIVEWAY_MIN_WIDTH_TWO_WAY = NationalStandard(
    5.80, "m", 'הנחיות משרד לתכנון חניה (gov.il), עמ\' 61 - רוחב מסדרון '
    "מזערי, תנועה דו-סטרית", basis="guideline")


def _tiered_width(props: dict) -> NationalStandard:
    if props.get("category") == "accessible":
        return PARKING_MIN_WIDTH_ACCESSIBLE
    return PARKING_MIN_WIDTH


def _driveway_width(props: dict) -> NationalStandard:
    if props.get("direction") == "two_way":
        return DRIVEWAY_MIN_WIDTH_TWO_WAY
    return DRIVEWAY_MIN_WIDTH_ONE_WAY


def derive_national_constraints(driver: DrawingDriver, ledger: ConstraintLedger,
                                messages: Messages | None = None) -> list[Constraint]:
    """National minimums for whatever the drawing model actually contains.

    Mirrors :func:`archagent.constraints.derive_implicit_constraints`'s shape
    on purpose - same "skip what cannot be measured, never fabricate" rule,
    same ledger-add pattern - so the two are easy to read side by side.
    """
    m = messages or DEFAULT_MESSAGES
    created: list[Constraint] = []

    def add(rule: str, test: Requirement, standard: NationalStandard) -> None:
        source = _SOURCE_BY_BASIS[standard.basis]
        created.append(ledger.add(Constraint(
            constraint_id=ledger.next_id("N"),
            source=source,
            rule=rule,
            priority=priority_for(rule, source),
            test=test,
            confidence=_CONFIDENCE_BY_BASIS[standard.basis],
        )))

    def _check_width(element_id: str, label: str, standard: NationalStandard) -> None:
        try:
            width = driver.measure({"element_id": element_id}, "width")
        except DrawingAPIError:
            return
        if width is None:
            return
        add(m.t("national_standard", element=label, parameter=m.metric("width"),
                value=m.value(standard.value), source=standard.source),
            Requirement(subject={"element_id": element_id, "label": label},
                       metric="width", op=">=", value=standard.value, unit=standard.unit),
            standard)

    for element in getattr(driver, "elements", list)():
        element_type = element.get("type")
        if element_type not in ("parking", "driveway"):
            continue
        props = element.get("properties", {}) or {}
        element_id = element["id"]
        label = element.get("label", element_id)

        if element_type == "parking":
            _check_width(element_id, label, _tiered_width(props))
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
        else:  # driveway
            _check_width(element_id, label, _driveway_width(props))

    return created
