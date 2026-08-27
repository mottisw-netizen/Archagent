# National vs. Local Standards — a Parameter-by-Parameter Survey

Per `PERMIT_LEARNING_MISSION.md` Phase 7 ("the system must distinguish
between a universal rule, an authority-specific rule, and a project-specific
requirement") and the project owner's explicit follow-up request: for every
numeric planning parameter already in this codebase, is there a real,
citable Israeli national law or standard behind it, or is it legitimately
local/plan-specific? Researched via public web search (nevo.co.il - the
official legal database, Wikisource's law mirror, and government/professional
sources) - see the caveat at the end on what this method cannot see.

**How to read the verdict column**: *National (wired)* means a real citable
source now backs a default in `archagent.national_standards`, active for
every project regardless of authority profile. *National (not wired)*
means a real source exists but wiring it in hit a genuine implementation gap
- named per parameter. *Local* means the parameter is correctly
authority/plan-specific by the nature of Israeli planning law (not a
research gap - a zoning plan setting its own landscaping ratio, for example,
is how the system is designed to work) or no national source was found.
*Unconfirmed* means a related national regulation was found but not
confirmed to match the exact figure currently in code.

---

## Parking

| Parameter | Current value | Verdict | Source |
|---|---|---|---|
| Parking space min width | 2.30 / 2.55 / 2.80 m (by obstruction) | **National (wired)** | תקנות התכנון והבניה (התקנת מקומות חניה), תשמ"ג-1983, תקנה 2 |
| Accessible parking min width | 3.00 m | **National (wired)** | same regulation |
| Parking space min length | 4.25 / 4.75 / 5.00 m (by end condition) | **National (wired, safe floor)** | same regulation - see the note below |
| Column/wall clearance to drive-path edge | 0.5 m / 0.75 m (service level 2) | Unconfirmed | ת"י 1918 (Israel Standard 1918) reportedly sets driving-lane widths, turning radii, max slopes and min height for parking facilities - but Israel Standards are sold by מכון התקנים (SII), not freely published online, so the exact clearance figure could not be verified against a public, citable text. The two numbers already in `geometry_rules.yaml` remain correctly scoped as Petah Tikva profile data, not promoted to core, until this is confirmed. |
| Turning radius (inner/outer) | none in code (caller-supplied only) | National, not wired | Same ת"י 1918 gap as above - `archagent.traffic.turning.validate_turning_path` exists and is correct, but has no default because no public source for the actual radius number was found |
| Accessible parking count (ratio of total) | not implemented | National, not wired | Set by a schedule/appendix (תוספת) to the 1983 parking regulations, not a flat percentage - implementing this needs the actual schedule table, not a single number, so it was not fabricated as one |
| Bicycle parking (count, dimensions, signage) | not implemented | National, not wired | תקנות התכנון והבניה (בקשה להיתר, תנאיו ואגרות), תש"ל-1970, תוספת שניה חלק ח1 - a real, distinct regulation for *bicycle parking spaces* (bike racks), separate from the `bicycle_stroller_room` storage-room parameter below - not yet implemented |
| Max walking distance, farthest space to entrance | not implemented | National, not wired | Found in search results (250 m) but not yet traced to its exact regulation clause - flagged for a follow-up pass, not fabricated as sourced |

**Note on parking length**: the regulation gives three different minimums
depending on what is at the far end of the space (against a wall: 5.00 m,
open: 4.75 m, against a curb with 50 cm clearance beyond it: 4.25 m). The
generic drawing model has no "what is beyond this space" property today, so
`national_standards.py` checks against 4.25 m - the safe floor that is
correct under every scenario. A space between 4.25 m and 5.00 m against a
genuine end wall would need the stricter figure and this floor alone would
not catch it; see `ARCHITECTURE_MAP.md`'s gap-naming convention -
this is `MISSING_GEOMETRY_OPERATION` (no "end condition" concept yet), not a
wrong number.

## Accessibility

| Parameter | Current value | Verdict | Source |
|---|---|---|---|
| Accessible ramp max slope | not implemented as a default (function takes `max_slope` as a caller-supplied parameter) | National, not wired | 8% (1:12.5), per תקנות שוויון זכויות לאנשים עם מוגבלות (התאמות נגישות...) plus ת"י 1918. **Not wired for a structural reason, not a sourcing gap**: `archagent.drawing.api.DrawingDriver.measure()` has no `"slope"` metric at all - only the typed, never-constructed `Ramp` dataclass carries one (see `ARCHITECTURE_MAP.md`). Wiring this needs either a new driver measurement or reading raw elevation properties directly; deliberately not rushed into this pass. |

## Landscaping / site coverage (all in `geometry_rules.yaml`)

| Parameter | Current value | Verdict | Reasoning |
|---|---|---|---|
| Common landscaping share | ≥ 30% of plot area | **Local** | Landscaping ratio is a zoning-plan (תב"ע) parameter by design in Israeli planning law - it varies per plan, per zone, per municipality on purpose. No national blanket percentage exists to search for; the file's own header already says this correctly. |
| Permeable area share | ≥ 15% of plot area | **Local** | Same reasoning - plan-specific. |
| Planting soil depth | ≥ 1.5 m | **Local** | A landscape-design guideline figure, not statute; no national source found. |
| Bicycle/stroller storage room | ≥ 0.5 m²/unit | Unconfirmed | A real national regulation governs "sizes, ventilation and lighting of building parts" (תקנות התכנון והבניה (בקשה להיתר, תנאיו ואגרות), תוספת שניה) and could plausibly set a room-size minimum here, but the specific figure was not confirmed against that text - kept local pending that check. |
| Development within plot boundary | boolean | **Local** (trivial) | Not a sourceable "regulation number" - a structural constraint, not a statute citation. |
| Municipal drainage setback | ≥ 2.0 m from an existing line | **Local** | Infrastructure protection distances are set per the specific drainage authority/infrastructure plan, not a national statute - correctly project-specific. |

## Setbacks / building line (קו בניין)

**Local by the nature of the law, not a research gap.** A building line is
always defined by the specific statutory plan (תב"ע) governing that parcel -
there is no national blanket setback distance to look up. This one was not
searched further because the premise of searching for a "national setback
number" is itself wrong; every setback constraint in this system correctly
comes from a comment, a project's own zoning plan reference, or an
authority profile, never from a core default - and that should stay true.

## Not yet surveyed

Curb height, sidewalk width/slope bounds (beyond the accessibility ramp
figure above), and road width (`archagent.site.roads`) were not researched
in this pass - named here explicitly so the gap is visible rather than
silently absent. Each `validate_*` function in `archagent.site.roads`
already takes its threshold as a caller-supplied parameter with no default,
the same pattern this whole survey has been checking - a follow-up pass
should cover them the same way.

---

## Method and its limits

Every citation above came from public web search snippets (nevo.co.il,
Wikisource, government and professional sites), not from opening and reading
the full regulation text directly - this session's WebFetch tool is
restricted to a small allowlisted domain set (see `PUBLIC_PERMIT_SOURCES.md`
for the exact mechanics of that restriction) and could not fetch nevo.co.il
or gov.il directly to verify a citation's exact wording. Every number wired
into `national_standards.py` came from a search result concrete enough to
trust (an explicit number attached to the regulation's name), and every
"unconfirmed" verdict above is unconfirmed specifically because the search
snippets described a relevant regulation's *existence* without giving the
exact figure - not because no source was looked for. Treat every "wired"
number as worth a second, direct-text verification once a session with
broader web access is available (see the "freeruner" environment discussion
elsewhere in this conversation), and treat every "unconfirmed"/"not
surveyed" row as this pass's honest boundary, not a claim that no national
standard exists.
