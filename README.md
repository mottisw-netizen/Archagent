# archagent

An implementation of the **AI Municipal Permit Drawing Review and Correction Agent**
specified in [`.claude/skills/municipal-permit-review/SKILL.md`](.claude/skills/municipal-permit-review/SKILL.md).

It takes municipal permit comments plus a drawing, works out what each comment
demands, finds the elements it refers to, computes the minimum change that
satisfies it without breaking anything else, applies that change through a
drawing-editing API, and proves the result by measuring it.

**Hebrew is a first-class language, in and out.** Israeli permit comments
(הערות רישוי) are read natively, and the report, open items, consultation
questions and previews come back in Hebrew, right-to-left.

**Claude does the reading.** The model interprets every comment; the drawing
measures every number. That boundary is enforced in code, not just documented.

```
comment → interpretation → elements → constraints → dependencies
        → solution → simulation → consultation → execution → validation → report
```

## Install and run

```bash
pip install -e ".[dev]"                 # add ".[llm]" for the Anthropic SDK
export ANTHROPIC_API_KEY=...            # or: ant auth login

# Hebrew project - comments in, Hebrew report out
archagent comments examples/project_he
archagent run examples/project_he --answers examples/answers_he.json

# English project
archagent run examples/project --answers examples/answers.json
archagent run examples/project --mode autonomous

archagent validate examples/project/source/project.json examples/project/constraints/zoning_plan.md
```

Claude is used automatically when credentials are present. Useful flags:

| Flag | Effect |
| --- | --- |
| `--llm` | require Claude; fail rather than fall back |
| `--no-llm` | deterministic parser only (no API calls) |
| `--model`, `--effort` | default `claude-opus-5` at `high` effort |
| `--llm-cache DIR` | cache answers on disk, so a re-run costs nothing |
| `--lang he\|en\|auto` | report language; `auto` follows the comments |
| `--source REF` | a file, or a live CAD host (`revit://127.0.0.1:8735`); repeatable |

Without installing: `PYTHONPATH=src python3 -m archagent.cli run examples/project_he`.

The example run produces, under `examples/project/`:

| Path | What it is |
| --- | --- |
| `versions/v1/`, `versions/v2/` | immutable model versions, each with `version.json` and `audit.jsonl` |
| `versions/project_original.json` | the untouched original |
| `output/<run>/correction_report.md` | the correction report (SKILL.md 15) |
| `output/<run>/compare_before_after.html` | before/after slider with a change table |
| `output/<run>/preview_v2_changes.svg` | highlighted change map (colour **and** text tag) |
| `output/<run>/change_set.json` | the Diff / Change Set: what changed, by host element id |
| `output/<run>/validation_report.json` | measured constraint and comment validation |
| `output/<run>/project_context.json` | the full run state, resumable and auditable |

## The web application

```bash
pip install -e ".[dev]"        # or ".[web,llm,claude-code]"
archagent-web                  # http://127.0.0.1:8000
```

A Hebrew, right-to-left workspace over the same agent:

- **Projects** - the bundled examples, or drag your own comments, zoning
  documents and model onto the page; files are sorted into roles on upload.
- **A run you can watch** - the pipeline streams its steps over SSE: comments
  parsed, elements mapped, plans simulated, changes applied, versions written.
- **Consultation that actually blocks.** When a correction needs an architect's
  decision, the run *stops*. The question appears with the comment, the
  proposal, the measured consequences and the alternatives; the pipeline waits
  on that answer before it touches the model.
- **A live drawing, optionally.** Leave the CAD field blank to work on the
  model inside the project, or enter `revit://127.0.0.1:8735` to work on the
  document the architect has open in Revit. **Check connection** answers with
  the open document's own name, the Revit version and the element count - the
  proof it is the right file before anything is edited.
- **Results** - KPI tiles, a status bar in the reserved status palette (every
  segment labelled - colour never carries the meaning alone), per-comment cards
  with the measured evidence and a confidence meter against the threshold, the
  constraint table, an interactive plan viewer, the full report, and every
  artefact for download.
- **A live plan, not a picture of one.** The "before/after" tab is a pannable,
  zoomable `<canvas>` reading the run's own `before_model.json`/`after_model.json`
  - wheel to zoom, drag to pan, click any element for its before/after values
  and which comment demanded them. Changed elements carry a dashed accent
  outline and a small badge; a toggle swaps the whole view between the two
  versions. No plugin, no native viewer - it runs in any browser, which is the
  point for a reviewer on Linux with nothing else installed.

### Two engines behind the same screen

| Engine | What runs | Consultation |
| --- | --- | --- |
| `pipeline` | The agent in the web server's own process | live - the run stops and asks you |
| `claude-code` | **Claude Code drives the run** through the Claude Agent SDK | deferred to open items |

The `claude-code` engine is the literal thing: Claude reads the project, decides
what to do, runs the pipeline through its command line, reads the report it
produced and writes the architect a summary in Hebrew. What makes that safe is
`ClaudeCodeEngine.guard_for()` - the `can_use_tool` callback the SDK consults
before every tool call:

- `Bash` is allowed only when the command matches `archagent` / `python -m archagent`;
- `Read`, `Glob` and `Grep` are allowed only for paths inside the project or the
  repository;
- `Write`, `Edit`, `WebFetch`, `WebSearch` and everything else are denied.

**`allowed_tools` must stay empty for this to hold.** An entry there
auto-approves the whole tool *before* the callback runs - the SDK warns about it
(`CanUseToolShadowedWarning`), and a test asserts the list stays empty. The
deterministic pipeline remains the only thing that edits a drawing.

### Connecting to the Claude service

The server uses `ANTHROPIC_API_KEY`, or an `ant auth login` profile, or a key
pasted into the connection dialog (kept in the server process only, never
written to disk). With no credentials the app still runs - on the deterministic
parser, and it says so on screen.

## Hebrew

`examples/project_he/` is the same site with Israeli comments. It parses the
forms permit comments actually use:

| Comment | Read as |
| --- | --- |
| `יש להגדיל את רוחב מקום חניה P12 ל-2.50 מ'.` | `P12 width >= 2.50 m` |
| `קו בניין צפוני לא יפחת מ-3.00 מ'.` | `building north setback >= 3.00 m` |
| `שטח הבנייה הכולל לא יעלה על 1,850 מ"ר.` | `floor_area <= 1850 m²` (not 1.85!) |
| `יש להקצות לפחות 34 מקומות חניה.` | `count(parking) >= 34` |
| `יש להרחיב את שביל הגישה ל-3.00 מטר.` | `driveway width >= 3.00 m` - the verb carries the metric |
| `נרשם.` | no action demanded |

Bounds (`לפחות`, `לא יפחת מ-`, `לא יעלה על`), the `ל-` value marker, prefixed
letters (`הרוחב`, `ברוחב`, `לרוחב`), gershayim (`מ״ר`) and construct forms
(`חניית`) are all handled. The comment text itself is never translated - it is
quoted verbatim in the report, and the drawing keeps its own language.

The report comes back like this:

```
# דוח תיקון הערות רישוי

טופלו אוטומטית: 2
טופלו לאחר התייעצות עם המשתמש: 1
דורשות בדיקה אנושית: 3

| הערה | מחלקה | סטטוס | ביטחון |
| C-001 | תנועה | טופל | 93% |
...
אימות:
טופל. נמדד 2.50 מ' >= 2.50 מ' הנדרש (get_element_geometry, בסיס מדידה: clear).
```

## Claude in the loop

Claude reads every comment and returns a validated object - department,
requirement, subject, confidence, and any ambiguity it noticed. Around that:

- **Validation before action.** A metric no driver can measure, a bad operator,
  a negative value, a setback with no edge - rejected, and the comment goes to a
  human. The model never reaches the drawing directly.
- **Two readings, one requirement.** The deterministic parser reads every
  comment too. Agreement raises confidence; disagreement drops it below the
  consultation threshold and records *both* readings, so a divergence becomes a
  question rather than a silent pick.
- **Disambiguation with a leash.** When several elements match, Claude chooses -
  but only from the candidate list, never above 0.9 confidence, and it may
  answer "I cannot tell", which sends the comment to a human.
- **It never measures.** Dimensions, areas, counts and compliance come from the
  drawing driver. The prompt deliberately withholds current dimensions so a
  reading cannot be anchored on them.
- **Graceful degradation.** No credentials, a rate limit, a network failure: the
  run continues on the deterministic parser at reduced confidence - which sends
  more comments to consultation - and says so in the report.

Model answers can be cached to disk (`--llm-cache`), making re-runs free and
deterministic.

## What the example demonstrates

Eight comments against a small site model, and the agent does something
different - and defensible - with each:

| Comment | What happens |
| --- | --- |
| `C-001` widen parking P12 to 2.50 m | applied; the planner picks the *east* anchor because growing west would overlap P13, and pulls the dimension and the parking schedule along |
| `C-002` update the parking schedule | applied; marked *Addressed - requires confirmation*, never *Resolved*, because the demand is not measurable |
| `C-003` "increase the parking space width" | refused: three parking spaces match and nothing in the comment separates them |
| `C-004` drive aisle ≥ 5.50 m | already compliant; measured and reported, nothing changed |
| `C-005` northern setback ≥ 3.0 m | consultation (it moves the building footprint); applied on approval, escalated in autonomous mode |
| `C-006` provide 34 parking spaces | escalated with a proposal: a program change is a design decision, not a correction |
| `C-007` "improve the facade composition" | no testable requirement; routed to human review with low confidence |
| `C-008` "Noted." | recorded as *Not applicable* |

In autonomous mode the run ends `failed` with an unmet definition-of-done item,
because the CRITICAL setback stays unresolved. That is the intended behaviour:
the report says so rather than padding the result.

## How the code maps to the specification

| SKILL.md | Module |
| --- | --- |
| 3 Required input, 3.2 manifest | `archagent/ingest.py` |
| 5.2 Comment analysis | `archagent/comments.py` |
| 6 Dependency graph | `archagent/graph.py` |
| 7.1 Comment → element mapping | `archagent/mapping.py` |
| 8 Constraint engine, 8.3 conflicts | `archagent/constraints.py` |
| 9 Correction plan | `archagent/planner.py` |
| 9.1 Simulation and pre-validation | `archagent/simulate.py` |
| 10 Consultation | `archagent/consult.py` |
| 11 Execution | `archagent/execute.py` |
| 12 Tool interface | `archagent/drawing/api.py`, `archagent/drawing/json_model.py` |
| 12 Live CAD host, wire contract | `archagent/drawing/protocol.py`, `drawing/revit.py`, `drawing/mock_host.py`, `revit-addin/` |
| 12 Multi-discipline routing | `archagent/adapters/` |
| 13 Preview and highlights | `archagent/preview.py` |
| 13.2, 16 Diff / Change Set | `archagent/changeset.py` |
| 14 Validation | `archagent/validate.py` |
| 15 Correction report | `archagent/report.py` |
| 16 Safety, versioning, audit | `archagent/versioning.py`, `archagent/audit.py` |
| 20 Confidence model | `archagent/models.py` (`Confidence`) |
| 20.4 Model / rules cross-check | `archagent/comments.py` |
| 2.2 Model boundary, interpretation | `archagent/llm/` |
| Web application, run streaming, engines | `archagent/web/` |
| 22 Units, rounding, language | `archagent/units.py`, `archagent/lang/` |
| 2, 5, 19 Orchestration | `archagent/orchestrator.py` |

## Rules the code enforces, not just documents

- **Only the execution agent writes.** Every mutating call goes through
  `DrawingDriver.authorised(plan_id)`; a mutation outside an approved plan
  raises `NotAuthorised`.
- **Nothing reaches the model unsimulated.** Plans are applied to an isolated
  sandbox first and the whole constraint ledger is re-measured there.
- **A pre-existing failure is not blamed on a plan** - only new violations,
  new spatial conflicts and regressions block it.
- **Rounding never flatters a requirement**: a `>=` value rounds down, a `<=`
  value rounds up, and 2.4996 m does not satisfy 2.50 m.
- **`Resolved` requires evidence** - a measurement from a measurement tool,
  recorded with the required value and the comparison.
- **The original file is never opened for write**, and its checksum is
  re-verified at the end of every run. Against a live host, `save_as` refuses a
  path equal to the open document - a version is always a new file.
- **A live plan is atomic.** The host applies the whole action list in one
  transaction group or rolls all of it back; a half-applied plan cannot exist.
- **Ambiguity is never resolved silently** - it consults or escalates.
- **The model never produces a number.** Everything it returns is validated
  against what the drawing layer can measure before it is used.

## Live CAD: Revit first, adapters underneath

A permit package is never one file. The architectural model is Revit; traffic,
roads and drainage arrive as consultant DWGs; the environmental appendix is a
document. So the agent does not talk to Revit - it talks to **adapters**, and
one municipal comment is routed to whichever adapter holds the element it names.

```
                     ┌──────────────┐
   comment ─────────▶│    Router    │──▶ discipline + the source that holds it
                     └──────┬───────┘
              ┌─────────────┼──────────────┬───────────────┐
        RevitAdapter   JsonAdapter     DwgAdapter      PdfAdapter
        live, edits    reference      live, edits      read + markup
        the document   model          the drawing      never edits
```

| Adapter | Disciplines | Can | State |
| --- | --- | --- | --- |
| `revit` | architecture, structure, accessibility, fire | read, measure, edit, preview, version | live, over the add-in |
| `json` | architecture, traffic | read, measure, edit, preview, version | the reference driver |
| `dwg` | traffic, roads, drainage, landscape | read, measure, edit, preview, version | live over the add-in, **or** headless over a plain `.dxf` file - no CAD seat needed either way |
| `pdf` | documents, environment | read, markup | never edits a document |

An adapter that cannot serve a source says exactly what is missing, and the
comments routed to it become **open items with a reason** - they do not fall
through to the architectural model and they do not disappear.

### One run, every connected tool - not just the primary

The router deciding *where* a comment belongs was not enough on its own: every
stage after it - mapping, planning, simulation, execution, validation - used to
run only against the primary architectural driver. Point Archagent at two live
sources today (`--source revit://... --source path/to/traffic.json`, or two
live hosts) and a single run now maps, plans, simulates and executes against
**each** source that has work routed to it, in the same run:

```bash
archagent run project --source revit://127.0.0.1:8735 --source project/traffic.json
```

* Each source is validated against **its own driver** - a comment answered in
  the traffic file is never marked unresolved because it cannot be measured
  through Revit, and vice versa.
* The dependency graph, the constraint ledger and the change set are merged
  across sources into one report; a comment no open, editable source can reach
  still gets an honest `requires_human_review`, never a silent drop.
* Versioning stays authoritative for the primary source (`save_as`, SKILL.md
  16); every other source touched gets a reference JSON snapshot in the same
  version directory - Archagent does not manage that tool's own file saving.
* The change set gains `sources` (every tool touched), `multi_source`, and
  `highlight_by_source` - a live host is only ever asked to select the
  elements that are actually its own.

### Revit

`revit-addin/` is a Revit 2024 add-in (C#) that exposes the **active document**
over a small loopback HTTP protocol; `archagent.drawing.revit.RevitDriver` is
the client half. See [`revit-addin/README.md`](revit-addin/README.md) for the
build, the install path, and an explicit account of what is and is not verified.

```bash
# in Revit: Archagent tab → Start host
archagent run examples/project_he --source revit://127.0.0.1:8735
```

Three things the Revit API forces, which the design absorbs so nothing above
the driver has to know about them:

* **A plan is applied as one batch.** Revit cannot hold a transaction between
  API calls, so `authorised(plan_id)` buffers the plan and sends it in one
  `/apply`; the host commits it as one transaction group - one undo step for the
  architect - or rolls the whole group back. A half-applied plan cannot exist.
* **Simulation never touches the open document.** The driver snapshots the
  model and simulates locally; the live document is written once, after the plan
  has been simulated and (in consultation mode) approved.
* **Ids are `UniqueId`,** and every length crosses the wire in metres. Revit's
  decimal feet stop inside the add-in.

`archagent.drawing.protocol` is the single definition of that wire contract, and
`archagent.drawing.mock_host` implements it over a JSON model - both the test
double and the executable specification the C# is written against:

```bash
archagent-host examples/project_he/source/project.json --port 8735
archagent run examples/project_he --source revit://127.0.0.1:8735
```

A full pipeline run against that live host produces results identical to the
file-based run; the tests assert it.

### AutoCAD and Civil 3D

`autocad-addin/` is the equivalent add-in for a consultant's DWG - the traffic,
roads and drainage disciplines Revit does not cover. It speaks the *identical*
protocol (that is the point of `protocol.py`), so the Python side needed almost
nothing new: `DwgDriver` is a two-line subclass of `RevitDriver`. See
[`autocad-addin/README.md`](autocad-addin/README.md) for the build, the
XDATA/layer-name convention a drawing needs to participate, and what is and is
not verified - including the Civil 3D-specific objects (alignments, corridors)
this phase does not read.

```bash
archagent run project --source revit://127.0.0.1:8735 --source autocad://127.0.0.1:8736
```

A single run against two live mock hosts, addressed as `revit://` and
`autocad://`, edits both and merges the result; the tests assert it too.

### DWG/DXF with no CAD seat at all

`DwgAdapter` also opens a **plain file**, no AutoCAD or add-in running
anywhere - the path for a reviewer on Linux with a consultant's DXF and
nothing else:

```bash
pip install -e ".[dxf]"          # ezdxf - MIT licence, pure Python
archagent run project --source project/traffic.dxf
```

A `.dxf` needs nothing beyond that. A `.dwg` needs converting to DXF first,
with the free [ODA File Converter](https://www.opendesign.com/guestfiles/oda_file_converter)
on `PATH` - run as a separate process and never bundled, the same posture as
calling `pdftotext` for PDF comment text; without it a `.dwg` source is
reported as unavailable with that exact reason, not silently degraded.
`archagent.drawing.dxf_model.DxfModelDriver` parses the file into the same
model shape `JSONModelDriver` already uses and then *is* one - every query,
measurement and mutation is the reference implementation, unchanged; only
parsing the file in and writing the result back out as real DXF entities is
new. A `.dwf`/`.dwfx` stays declared: it is Autodesk's fixed publish/view
format, with no live document behind it to edit.

**GPL note.** LibreDWG (GPL) was the obvious first choice for this and was
deliberately not used: linking a GPL library into a paid product forces the
whole codebase under GPL. ezdxf (MIT) plus the ODA File Converter as an
external, unbundled process avoids that entirely.

### The Diff / Change Set

Every run writes `output/<run>/change_set.json`: each element the run touched,
by the id the *host* uses, with before/after per property, the comment that
demanded it, the plan that produced it, the geometry delta, and the constraints
the run moved. It is what a CAD tool consumes - and against a live host the
agent also asks the host to **select those elements**, so the architect sees the
diff highlighted in Revit itself, not only in the rendered preview.

### Another CAD tool

Implement `archagent.adapters.base.BaseAdapter` (and, for a live tool, the host
protocol) and register it. Nothing above the adapter layer changes. The contract
each driver method must honour - including the `before`/`after` change record
and the measurement basis - is documented in `drawing/api.py`; `JsonAdapter` is
the worked example. `DwgAdapter` is the worked example for a *second* live
host reusing the same protocol client (`RevitDriver`/`DwgDriver`); `PdfAdapter`
shows how to declare an adapter that is deliberately never live, and its own
history shows how to declare one that is not implemented yet without
pretending otherwise.

PDF comment text is read via `pdftotext` if present, or a hook you register at
`archagent.ingest.PDF_TEXT_EXTRACTOR`. If neither is available, the file is
reported as unreadable and listed as an open item - the agent never guesses
what a comment said.

## Tests

```bash
python3 -m pytest -q      # 209 tests, no network access required
```

The Claude paths are covered with scripted clients: invalid readings, the
cross-check outcomes, disambiguation limits, and a full Hebrew run with the
model in the loop and another with it unavailable. The live-CAD path runs
against a real HTTP host on loopback, so the driver, the batching and the error
mapping are exercised, not mocked - and two tests read the C# sources to fail
when the add-in and `protocol.py` drift apart.

## Scope

Output is a proposal. It requires review and approval by the responsible
licensed professional before submission to any authority; every generated
report carries that sign-off block.
