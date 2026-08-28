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

## Verified against primary source text (direct document fetch)

This section supersedes the "Method and its limits" caveat below wherever the
two disagree: this pass fetched the primary documents directly (WebFetch,
with `curl` as a fallback that turned out to be IP-blocked by nevo.co.il —
see the note at the end of this section) instead of relying on search-result
snippets. Five sources were checked. Findings are reported plainly: confirmed
figures with their clause, wrong figures named as wrong, and unconfirmed
items with the specific reason they stayed unconfirmed.

### 1. תקנות למניעת מפגעים (רעש בלתי סביר), תש"ן-1990 (noise)

**Confirmed, text-based:**
- Day = 06:00–22:00, night = 22:00 (22:01)–06:00 (05:59), per the definitions
  in סעיף 1 (regulation 1).
- Five building-use categories are defined in סעיף 1 / תוספת ראשונה: מבנה א'
  (hospital, convalescent home, school), ב' (building in a residential zone),
  ג' (building in a mixed residential/commercial area), ד' (residential unit
  in an industrial/commercial zone), ה' (industrial/commercial building in an
  industrial zone).

**Genuinely unconfirmed — figure not present as text:** the actual dB(A)
limits per category, per day/night, live in the תוספת ראשונה table, and that
table is embedded as a scanned image (`image004.gif`) with no text
alternative in the published HTML. This is not a fetch failure — the page
itself loaded and its surrounding structure (column headers "יום"/"לילה",
the five category rows) is confirmed above — it is a genuine "the number
is not present as extractable text" situation. No dB figure is recorded in
`national_standards.py` for this parameter, consistent with the "not wired"
verdict already in this document; this pass adds nothing to change that
verdict, only firmer confirmation of why.

### 2. תקנות התכנון והבניה (התקנת מקומות חניה), תשמ"ג-1983 (parking)

**Correction — the existing citation for the width/length figures is
wrong.** This document's own table above (Parking section) cites "תקנה 2"
of this regulation as the source for the 2.30/2.55/2.80 m width and
4.25/4.75/5.00 m length figures in `national_standards.py`. Direct fetch of
the full regulation text — תקנה 2 itself, חלק א' (general provisions) and
חלק ב' (vehicle parking) of the תוספת — found **no width or length
dimensions anywhere in this document**. What the text actually contains:
- תקנה 2: only governs a planning institution's authority to set a different
  space *count* than the תוספת prescribes, under conditions — not dimensions.
- חלק א', סעיף 1 of the תוספת defines "parking space" only as an *area*
  absent a detailed layout plan: 25 m² for a private car, 60 m² for a truck,
  100 m² for a bus — no width/length breakdown, and no obstruction-dependent
  variation.
- חלק ב' of the תוספת contains only parking-ratio-by-land-use tables (e.g.
  "1 space per 50 m²" for offices, commerce, industry, etc.), not space
  dimensions.
- חלק ג' and חלק ד' cover bicycle and motorcycle parking minimums
  respectively — also not the source of the 2.30–2.80 m / 4.25–5.00 m car
  space figures.

  The 2.30/2.55/2.80 m and 4.25/4.75/5.00 m figures are real, sensible
  numbers for Israeli parking-space design and are not being called
  fabricated — but this specific regulation and this specific clause are the
  wrong citation for them. The most likely actual source is ת"י 1918 (the
  Israel Standard already flagged elsewhere in this document as real but
  paywalled/unverifiable), not a freely-published planning regulation.
  `national_standards.py` and this document's citation for those two rows
  should be corrected to remove the "תקנה 2" attribution — the figures stay
  wired as a working default, but their sourcing claim needs to change from
  "confirmed against this regulation's text" to "plausible ת"י 1918 origin,
  unconfirmed" until ת"י 1918 itself can be read.

**Confirmed:** accessible parking space count/ratio is not a flat number in
this regulation — Part A, §8 cross-references "פרטים 8.110 ו-8.271 בתוספת
השנייה" (items 8.110/8.271 of the Second Appendix to the general Planning
and Building regulations, a separate document). This matches the existing
"not implemented — set by a schedule, not a flat percentage" verdict above;
this pass just confirms the cross-reference wording directly rather than via
search snippet.

**Column/wall clearance to drive-aisle:** not covered by this regulation
either (consistent with it already being marked "Unconfirmed" against ת"י
1918, not this document). See source #4 below for a related, but distinct,
figure that direct fetch did surface.

### 3. תקנות שוויון זכויות לאנשים עם מוגבלות (התאמות נגישות למקום ציבורי שאינו בניין), תשע"ד-2013 (accessibility)

**Correction — three figures in this document's own Accessibility table are
not confirmed by this regulation's text, and are likely mis-cited.** Direct,
full-document search (including regulations 2–4, 7–13 and both appendices)
for "אבן שפה" (curb), "מונמכת" (dropped/lowered), and the 200 m/100 m
distance figures returned **zero matches outside the cemetery-specific
section (regulation 9)**. Specifically:
- **Dropped-curb max transition slope**: not found anywhere in this
  regulation's text. The existing "≤10%" figure is not confirmed here.
- **Curb height at an accessible bus stop**: not found in this regulation.
  "תחנת הסעה" (transit stop) is named once, in regulation 2(א)(2)(א), only
  as one of several nearby amenities a public-place entrance must connect
  to accessibly — no height figure is attached. See source #5 below, which
  *does* directly confirm a 15 cm figure, but sources it to a different
  regulation ("תקנות דרכים נגישות" — accessible-roads regulations, not this
  "non-building public place" regulation).
- **200 m / 100 m accessible-route distance**: the only distance caps in the
  entire document are cemetery-specific (regulation 9): route length ≤100 m,
  or ≤60 m where slope exceeds 5%; distance from a viewing point to a grave
  ≤25 m. No general 200 m/100 m figure exists in this regulation's text.

**What this regulation's text does confirm, not previously in this
document:** regulation 8(ד) (temporary/maintenance-period accessibility)
sets a maximum slope of 12% for a temporary ramp segment ≤2.5 m long (with
uniform slope required between landings), minimum clear width 90 cm, and
minimum load capacity 350 kg — this is for temporary ramps during renovation
work, not the general permanent-ramp figure the existing "8%" row describes.
The document repeatedly defers detailed technical figures to "הנחיות טכניות
של הממונה" (regulation 7, Commissioner's technical instructions) and to ת"י
1918 — consistent with this document's existing framing that the paywalled
Standard, not this regulation's own text, likely carries the actual
permanent-ramp slope, dropped-curb, and distance figures. The "8%"
ramp-slope default already in this document should be treated as unconfirmed
against this specific regulation's text (it may still be correct — it is
consistent with common Israeli accessible-design practice and with ת"י
1918 as reported elsewhere — but this regulation's own text is not where it
comes from).

### 4. Ministry parking design guidelines PDF (gov.il, `parking_planning_guidelines`)

This PDF fetched successfully via direct download (WebFetch's own HTML
fetch failed on the raw PDF; downloading and extracting text locally with
`pypdf` worked — 84 pages, Hebrew RTL text, tables partially garbled by
extraction but numerically legible). Findings, each with its own page/section:

- **Minimum outer turning diameter** — טבלה 1 ("מידות רכב לתכנון", design
  vehicle dimensions, p. 5–6): 14.0 m for the ramp-design vehicle, 11.0 m
  for the aisle-width-design vehicle. This is the design vehicle's own
  turning diameter (the basis other dimensions are derived from), not a
  single simple "required maneuvering radius" — but it is the closest,
  directly-cited figure to what was asked.
- **Minimum inner turning radius at a road curve/intersection** within a
  parking facility: 3.00 m (p. 61, section "רדיוסים בפניות").
- **Column/wall setback from the turning-radius line**: 0.5 m / 50 cm, same
  section, same page — a genuinely new, directly-confirmed figure. Note
  this is scoped specifically to clearance from a *turning-radius curve*,
  not a general drive-aisle edge, so it does not fully resolve the
  "Unconfirmed" column/wall clearance row in the Parking table above (which
  is about a straight drive-path edge) — but it is a real, citable,
  closely-related number this pass did not have before.
- **Minimum curb radius at a parking-lot/street connection acting as an
  intersection**: 6.0 m (p. 62, section 14.2, "החיבור עם הרחוב").
- **Minimum drive-aisle width between two parking rows** (independent of
  angle): two-way (דו-סטרי) 5.80 m; one-way (חד-סטרי) 3.50 m — widen by
  0.30 m per side if the aisle runs parallel to a wall (p. 61, just before
  "רדיוסים בפניות").
- **Access road to a parking lot**: generally two-lane, two-way, 6.0 m wide
  (p. 62, §14.1); may be single-lane only under specific conditions (serves
  ≤40 spaces, access path <25 m long, full driver sightline the whole
  length) — a genuinely new figure, not previously in this document.

None of these were in `national_standards.py` or this document before this
pass; they are new candidates for a future wiring pass, not yet wired.

### 5. "Green Series" street planning guidelines PDF (gov.il)

The specific PDF at the given URL is the **"תנועת רכב מנועי" (motorized
vehicle movement) volume** of the multi-volume Green Series, dated update
October 2020 (this matters — see the gap noted below). WebFetch failed
outright (12.2 MB PDF over WebFetch's 10 MB content cap); downloading and
extracting locally with `pypdf` worked (125 pages).

- **Minimum/maximum lane width by street type** — טבלה 3.3 (p. 69–70), not
  overall road width: local street (רחוב מקומי) 2.50–3.0 m or 2.75–3.0 m
  per lane depending on sub-case; collector street (רחוב מאסף) 2.75–3.0 m
  or 3.0–3.25 m; arterial road (דרך עורקית) 3.25–3.50 m; traffic-calmed
  zone street 4.75–5.80 m total (up to 5.0 m where parking is perpendicular).
- **Curb height at bus stops**: **15 cm, explicitly confirmed**, "even on
  streets where the general sidewalk curb height is 10 cm... to comply with
  תקנות דרכים נגישות [accessible-roads regulations]" (p. 88, §3.8). This
  directly confirms the 15 cm figure already in this document's
  Accessibility table — but names a *different* regulation ("תקנות דרכים
  נגישות") as its source than the one this document currently cites
  (תשע"ד-2013, source #3 above) — see the correction in #3.
- **General sidewalk curb height** (not at bus stops): up to 10 cm on
  streets (רחובות), 15 cm on roads (דרכים) — §3.6.1, p. 84.
- **Planting/green strip width along a sidewalk edge** (not the sidewalk
  itself): 2.0 m on collector streets, 2.5 m on urban roads — p. 84.

**Genuinely unconfirmed — not present in this specific volume:** a simple
"minimum road width and minimum sidewalk width by street classification"
table, as asked for, does not exist in this PDF. This volume repeatedly
defers general sidewalk width, crossing and curb-drop guidance to a
*companion* volume in the same series, "ספר תנועת הולכי-רגל" (Pedestrian
Movement volume) — a different PDF this pass did not fetch. Overall road
cross-section width in this volume is composed from the lane-width table
above plus separately-specified medians, parking strips and sidewalks per
corridor, not published as one classification→width table. This is a real
gap in the source consulted, not a number this pass declined to report.

### Note on method for this section

`curl` from this session is IP-blocked by nevo.co.il itself (HTTP 403,
"כתובת IP חסומה" — unrelated to the outbound network policy discussed in
the "Method and its limits" note below, and confirmed by fetching the same
URLs successfully through WebFetch immediately afterward). WebFetch's own
first pass on each nevo.co.il page also under-reported — it returned a
partial summary rather than the full text — so each nevo.co.il source was
re-queried two to three times with progressively more targeted prompts
(asking for full verbatim clause text, appendix tables, and specific
keyword searches) before treating an absence as confirmed rather than as an
artifact of summarization. The gov.il PDFs required a local download and
`pypdf` text extraction (WebFetch could not process either the corrupted
in-tool PDF rendering for the parking guidelines, or the 12 MB size of the
Green Series PDF, directly).

---

## Parking

| Parameter | Current value | Verdict | Source |
|---|---|---|---|
| Parking space min width | 2.30 / 2.55 / 2.80 m (by obstruction) | **Wired, source unconfirmed** (`confirmed=False`) | Direct fetch proved the original "תקנה 2" citation wrong - see "Verified against primary source text" §2 above. Still wired as `source="Reference"`/MEDIUM priority, not the CRITICAL a confirmed statute would get. |
| Accessible parking min width | 3.00 m | **Wired, source unconfirmed** (`confirmed=False`) | same correction |
| Parking space min length | 4.25 / 4.75 / 5.00 m (by end condition) | **Wired, source unconfirmed** (safe floor) | same correction - see the note below |
| Column/wall clearance to drive-path edge | 0.5 m / 0.75 m (service level 2) | Unconfirmed | ת"י 1918 (Israel Standard 1918) reportedly sets driving-lane widths, turning radii, max slopes and min height for parking facilities - but Israel Standards are sold by מכון התקנים (SII), not freely published online, so the exact clearance figure could not be verified against a public, citable text. The two numbers already in `geometry_rules.yaml` remain correctly scoped as Petah Tikva profile data, not promoted to core, until this is confirmed. |
| Turning radius (inner/outer) | none in code (caller-supplied only) | **National, confirmed (not wired)** | Ministry parking design guidelines PDF, p. 61 "רדיוסים בפניות": minimum inner turning radius at a road curve/intersection within a parking facility = 3.00 m; p. 62 §14.2: minimum curb radius at a parking-lot/street connection = 6.0 m. Design-vehicle outer turning diameter (p. 5-6, טבלה 1) = 14.0 m (ramp-design vehicle) / 11.0 m (aisle-width-design vehicle). Real, directly-confirmed figures from a ministry guideline document, not yet wired into `archagent.traffic.turning.validate_turning_path` (which has no code path constructing a real `TurningPath` from a project - see `ARCHITECTURE_MAP.md`). |
| Drive-aisle width (two parking rows) | none in code | **National, confirmed (not wired)** | Same PDF, p. 61: two-way 5.80 m, one-way 3.50 m; +0.30 m per side if parallel to a wall. Access road to a lot: generally 6.0 m (two-lane, two-way), narrower only under specific conditions (§14.1). |
| Column/wall setback from a turning-radius curve | 0.5 m already used for the general drive-path-edge case | **National, confirmed (narrower scope)** | Same PDF, p. 61: 0.5 m from the *turning-radius curve* specifically - confirms the existing 0.5 m figure in a closely related but distinct case; does not resolve the general drive-path-edge clearance row above, which remains unconfirmed. |
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

## Drainage / sanitation piping

| Parameter | Current value | Verdict | Source |
|---|---|---|---|
| Drainage pipe minimum slope | not implemented (`archagent.site.roads.pipe_slope` only derives a slope from invert levels; no default to check it against) | National, not wired | תקנות התכנון והבנייה (תכן הבנייה) (תברואה), תש"ף-2019 requires horizontal drains to slope enough for proper flow "per תקן ישראלי 1205"; ת"י 4397 (stormwater drainage systems) separately sets minimum slopes as a function of pipe diameter and internal roughness. Both are real, current regulations - but like ת"י 1918 for parking, the actual slope table lives inside a paid Standards Institution (SII) document, not the freely-published regulation text, so no specific number was fabricated here. |
| Sub-surface pipe installation generally | not implemented | National, not wired | ת"י 1205 Part 2 - same paywall situation |
| Municipal drainage line clearance | ≥ 2.0 m | **Local** (unchanged from before) | This is about keeping clear of an *existing* municipal line, not pipe design - no evidence found that this specific clearance distance is set nationally rather than per infrastructure authority/plan |

**Structural note, same as the traffic module**: even where a slope number
*is* eventually sourced, `Pipe`/`Curb`/`Sidewalk` in `archagent.site.roads`
have the identical gap already named in `ARCHITECTURE_MAP.md` for
`ParkingSpace`/`Ramp`/`TurningPath` - nothing in the real pipeline ever
constructs one from a project's actual drawing model, so wiring a national
default here needs that connection built first, not just the number.

## Accessibility (additional findings beyond the ramp-slope figure above)

| Parameter | Current value | Verdict | Source |
|---|---|---|---|
| Dropped curb (אבן שפה מונמכת) max transition slope | not implemented | Unconfirmed - **not found in the cited regulation** | A direct, full-text search of תקנות שוויון זכויות לאנשים עם מוגבלות (התאמות נגישות למקום ציבורי שאינו בניין), תשע"ד-2013 for "אבן שפה"/"מונמכת" found zero matches outside the cemetery-specific section. The "≤10%" figure is not confirmed against this regulation's text - see "Verified against primary source text" §3 above. |
| Curb height at an accessible bus-stop boarding point | not implemented | **National, confirmed - wrong regulation cited** | ≥ 15 cm is directly confirmed, but by the Green Series street guidelines (p. 88, §3.8, citing "תקנות דרכים נגישות") - not by the 2013 regulation this row previously cited. Still not wired: narrower in scope than `Curb.kind`'s current values, and Curb has no bus-stop-specific kind modelled. |
| Max distance, accessible parking/route to main entrance | not implemented | **Not found in the cited regulation** | Direct full-text search of the 2013 regulation found only cemetery-specific distance caps (route ≤100 m, or ≤60 m if slope >5%; viewing-point-to-grave ≤25 m) - no general 200 m/100 m figure exists in this document's text. The "200 m / 100 m" row is withdrawn as a citation to this regulation; if that figure is real, it comes from somewhere else not yet identified. |
| General accessible-route slope limits | 8% max already used for ramps (see above) | Unconfirmed against this regulation's own text | The 2013 regulation repeatedly defers technical figures to "הנחיות טכניות של הממונה" (regulation 7) and to ת"י 1918, rather than stating a general permanent-ramp slope itself. What its own text *does* confirm: a temporary/maintenance-period ramp (regulation 8(ד), ≤2.5 m long) may slope up to 12%, with 90 cm minimum clear width and 350 kg minimum load capacity - a different, narrower case than the general "8%" figure already wired. |

## Setbacks / building line (קו בניין)

**Local by the nature of the law, not a research gap.** A building line is
always defined by the specific statutory plan (תב"ע) governing that parcel -
there is no national blanket setback distance to look up. This one was not
searched further because the premise of searching for a "national setback
number" is itself wrong; every setback constraint in this system correctly
comes from a comment, a project's own zoning plan reference, or an
authority profile, never from a core default - and that should stay true.

## Environment - trees / forestry

| Parameter | Current value | Verdict | Source |
|---|---|---|---|
| "Mature tree" (עץ בוגר) trunk diameter, requiring a felling license | 10 cm (general), 20 cm (residential-zoned plot) | **National (wired)** | פקודת היערות (Forest Ordinance). `archagent.site.trees.requires_felling_license` checks this - trunk diameter only, since `Tree` has no height field and the Ordinance's full test is height >= 2 m *and* diameter over the threshold; returns `None` (unmeasured) rather than guessing when diameter is unknown, and never touches the separate, authority-sourced `preservation_status` field. |
| Mature/protected tree preservation radius | caller-supplied only, no default | **Local**, correctly | The Ordinance defines the *license trigger* (diameter), not a universal preservation *radius* - that comes from a forestry officer's own survey/license per tree, which is exactly why `Tree.preservation_status`/`preservation_radius` are never auto-set. |
| "Felling" definition (what counts as an act needing a license) | not modelled | National, not wired | The Ordinance's own definition is broad - main-trunk pruning, poisoning, bark removal, burning, root-cutting, *or building within the canopy diameter*, not just outright removal. `validate_preservation_radius` already checks "does a planned work point fall inside the radius", which is one instance of this broader definition, not the full test. |

## Environment - noise / acoustics

| Parameter | Current value | Verdict | Source |
|---|---|---|---|
| "Unreasonable noise" (רעש בלתי סביר) dB limits | not modelled at all - no acoustic dB semantic object exists in this codebase | National, not wired | תקנות למניעת מפגעים (רעש בלתי סביר), תש"ן-1990 and (מניעת רעש), תשנ"ג-1992 are real, in force, and define limits per building-use type with separate day (06:00-22:00) and night (22:00-06:00) thresholds - but the actual dB figures per category were not in the search snippets available this session (they explicitly exclude aircraft, vehicle/rail traffic and temporary construction-site noise, which is itself a useful fact - this system should never apply a blanket noise constraint to those sources). `archagent.environment.reports.py`'s own docstring already states its design intent correctly: "None of these invent a legal threshold - they check coverage" (is an acoustic report present/complete), not the report's actual numeric findings - so there is no existing threshold-checking code this would even wire into today. Implementing real dB limits is new semantic territory (`MISSING_SEMANTIC_OBJECT` per `ARCHITECTURE_MAP.md`'s gap taxonomy), not a missing default on existing code. |

## Traffic - EV charging infrastructure

| Parameter | Current value | Verdict | Source |
|---|---|---|---|
| Share of parking spaces requiring EV-charging infrastructure (conduit + panel capacity, not the charger itself) | not modelled at all | National, not wired | 20% of parking spaces in new residential buildings built as high-density (בנייה רוויה), in force since March 2023 - a 2022 amendment to the same 1983 parking regulations already wired for width/length. Panel capacity must be at least 3 kW × 20% of the space count. This is a strong, precise, freely-published figure - a genuinely good candidate for a small new module (an `EVChargingInfrastructure` semantic object plus a `derive_national_constraints`-style count check), not implemented in this pass because it is new territory, not an existing validator missing a default, and the project owner's "check every parameter" ask was answered by surveying, not by building new features unprompted (`PERMIT_LEARNING_MISSION.md`: "do not randomly add features"). |

## Roads

| Parameter | Current value | Verdict | Source |
|---|---|---|---|
| Minimum/maximum lane width by street type | caller-supplied only (`archagent.site.roads.Road`), no default | **National, confirmed (not wired)** | Green Series, "תנועת רכב מנועי" volume, טבלה 3.3 (p. 69-70): local street 2.50-3.0 m per lane; collector street 2.75-3.25 m; arterial road 3.25-3.50 m; traffic-calmed zone 4.75-5.80 m total. This is lane width, not a single "road width" figure - see the note below on why a flat road-width table does not exist. |
| General sidewalk curb height (not at a bus stop) | not implemented | **National, confirmed (not wired)** | Same volume, §3.6.1, p. 84: up to 10 cm on streets (רחובות), 15 cm on roads (דרכים). |
| Planting/green strip width along a sidewalk | not implemented | **National, confirmed (not wired)** | Same volume, p. 84: 2.0 m on collector streets, 2.5 m on urban roads. |
| General minimum sidewalk width (a flat classification table) | caller-supplied only (`archagent.site.roads.Sidewalk`), no default | **Confirmed as a real gap in the source, not just unresearched** | The "תנועת רכב מנועי" (motorized vehicle) Green Series volume this pass fetched does not contain sidewalk width - it explicitly defers that to a *companion* volume, "ספר תנועת הולכי-רגל" (Pedestrian Movement), not yet fetched. Road cross-section width is composed from the lane table above plus separately-specified medians/parking/sidewalks, not published as one classification→width table in this volume. |

## Architecture

No additional undiscovered numeric parameters beyond what earlier sections
already cover. `archagent.architecture`'s validators
(`validate_area_ratio`, `validate_soil_depth`, `validate_distance_to_plot_boundary`,
`validate_site_level_difference`) are all generic composite-math helpers
with no built-in thresholds of their own - every actual number they get
called with today comes from `geometry_rules.yaml` (landscaping ratio,
permeable area, soil depth - already covered above, correctly local) or a
municipal comment. Setback/building line is covered above too: local by the
nature of the law, not a research gap.

## Lighting

**Not modelled at all - a `MISSING_SEMANTIC_OBJECT` gap, not a
national-vs-local question yet.** `archagent.infrastructure` mentions
lighting only as one of several *coordination* items an external-utility
requirement can name (electricity, lighting, communication cabinets) - a
document/coordination check, not a semantic object with its own geometry or
numeric parameters (pole spacing, lux levels, etc.). There is no ת"י
1592-style lux/spacing figure wired anywhere because there is no lighting
object for it to attach to. Before researching a number, this needs Phase 5
(discover the object from real cases) - premature to wire a threshold onto
an object this codebase does not yet represent.

## Not yet surveyed

General (non-accessibility-specific) sidewalk width and road width
(`archagent.site.roads.Road`/`Sidewalk`) were still not researched in this
pass - named here explicitly so the gap is visible rather than silently
absent. Every `validate_*` function in `archagent.site.roads` already takes
its threshold as a caller-supplied parameter with no default, the same
pattern this whole survey has been checking - a follow-up pass should cover
these the same way. Drainage and the additional accessibility figures above
were added after the project owner pointed out drainage had been skipped
rather than actually searched - a fair correction, and a reminder that
"not yet surveyed" in this document means exactly that, not "checked and
found nothing."

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
