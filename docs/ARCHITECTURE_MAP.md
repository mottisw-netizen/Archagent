# Archagent — Phase 0 Architecture Map

Produced against commit `9a188a2` (2026-08-27) in response to
`PERMIT_LEARNING_MISSION.md` §Phase 0: understand the system completely
before any further implementation. Read that file first for why this exists.

**How to read this document.** Every section below separates three things
that the mission explicitly asks not to conflate:

- **What exists** — the real, tested mechanism, with its file(s).
- **How it was built** — what the current logic is actually derived from.
- **The gap** — what Phase 1+ (real permit cases) would have to supply that
  isn't there today.

The single most important finding, true across almost every section: **the
system's domain knowledge is derived entirely from one document** — the
Petah Tikva Municipal Permit Review Completion Plan the project owner
supplied as a spec — **plus a synthetic test corpus written to match that
document's own examples**, not from real, adjudicated permit case files. The
architecture is real and tested against that corpus; the domain knowledge it
encodes has never been checked against an actual case with a real outcome.
Nothing below should be read as "already learned from real permits" — it is
"correctly implements what one spec document described."

---

## Permit parsing / ingest

- `ingest.py` — Step 1: scans a project directory into an `InputManifest`
  (source model, municipal comments, constraints documents), classifying
  each file's read status. Real, general-purpose, format-agnostic.
- `comments.py` — Step 2: turns comment text into `MunicipalComment` /
  `Requirement` objects (department, subject, verb, measurable value, unit).
- **How it was built**: `comments.py`'s parser is a deterministic
  keyword/regex layer per language (`lang/hebrew.py`, `lang/english.py`),
  extended repeatedly to match new example sentences from the spec and from
  the 40-comment synthetic corpus (`tests/fixtures/petah_tikva/comments_he.jsonl`).
  There is also an optional LLM path (`llm/interpret.py`) that asks Claude to
  do the same extraction when an API key is configured — the two paths are
  meant to agree, but only the deterministic one is exercised in tests
  without a live key.
- **The gap**: every regex was written by reading spec sentences, not by
  measuring what phrasing actually recurs across many real comments from
  Petah Tikva (or any other authority). Phase 1/4's "raw comment → normalized
  requirement" pipeline in the mission is this module, but today's pattern
  set has an n of ~40 hand-written examples, not a real corpus.

## Municipal comments / requirement-type classification

- `models.py: RequirementType` + `lang/requirement_types.py` — classifies a
  comment into one of ~10 types (GEOMETRIC, DOCUMENT, EVIDENCE, APPROVAL,
  COMPLETION_CONDITION, INSPECTION, WORKFLOW_GATE, DESIGN_DECISION,
  CALCULATION, ...) independently of whether it also parses to a measurable
  `Requirement`.
- **How it was built**: an ordered list of Hebrew/English regexes, most
  specific first (e.g. "תעודת גמר" must match COMPLETION_CONDITION before
  the more general APPROVAL pattern can steal it). Every pattern traces to a
  spec §3 example.
- **The gap**: the ordering and specificity rules are correct *engineering*
  (first-match-wins over a hand-authored table is a defensible design) but
  the *coverage* of that table has never been measured against real
  comment volume — Phase 8's "comment classification accuracy" metric has no
  real denominator to compute against yet.

## Semantic model

Per-discipline typed objects, each with its own module:

- `architecture.py` (facade/envelope, landscape ratio)
- `traffic/*` (parking, turning radius, ramps, clearance)
- `site/*` (topology, roads/curbs/pipes, drainage, elevations, trees, surfaces)
- `environment/*` (acoustic/hydrologic/tree-survey evidence + validators)
- `sheets/*` (plan/sheet + revision tracking)
- `infrastructure.py` (external infra requirements)

- **How it was built**: each object and its validators were added because a
  spec section named it (e.g. spec §9-14 → `site/*`), not because a survey
  of real drawings showed these were the recurring elements. The mission's
  Phase 5 explicitly asks for the reverse order: discover objects from real
  cases, add semantics only when they recur *and* enable deterministic
  validation. Structurally the code already supports that discipline (each
  module is small, typed, and independently testable) — what's missing is
  evidence that these are the right ~40 objects and not, say, 10 that matter
  and 30 that have never appeared in a real permit.

## Constraints / requirements engine

- `constraints.py` — `ConstraintLedger`, `evaluate_constraint`,
  `constraints_from_comments`, `constraints_from_document`,
  `derive_implicit_constraints`, `find_conflicts`/`resolve_conflict`
  (priority-based conflict resolution between comment-derived and
  document-derived constraints).
- `conditional.py` — structured `ConditionalRequirement` logic
  (if/then gates spanning stages or disciplines).
- **How it was built**: the conflict-priority rules (`priority_for`) and the
  conditional-logic grammar were designed against spec examples of
  conflicting requirements, not against a real case where two departments'
  comments actually contradicted each other.
- **The gap**: this is the clearest candidate for Phase 6's "Requirement
  Library" — right now a `Requirement`/`Constraint` is created ad hoc per
  comment at parse time. There is no persisted, reusable
  `RequirementTemplate` catalogue (id, discipline, semantic object,
  parameterized constraint, resolution methods, validation method,
  evidence/approval need) that authority profiles instantiate. The pieces
  needed to build one already exist (`RequirementType`, `Constraint`,
  authority YAML) but they are not assembled into that single artifact yet.

## Authority profiles

- `authority/base.py` + `authority/petah_tikva.py` load a YAML pack from
  `.claude/skills/municipal-permit-review/authorities/petah-tikva/`:
  `authority.yaml` (departments, terminology), `disciplines.yaml`,
  `stages.yaml`, `comment_patterns.yaml`, `geometry_rules.yaml` (numeric
  thresholds, each tagged with its spec source), `evidence_requirements.yaml`.
- **How it was built**: this is already structurally exactly what mission
  Phase 7 asks for — data-driven, not hardcoded into the core engine, and
  every number in `geometry_rules.yaml` is commented with its own caveat:
  *"These are NOT universal Israeli planning rules... sourced to the
  supplied municipal record for one specific project"*. That self-aware
  caveat was written before this mission existed, so the architecture
  already respects the mission's "never promote a single comment into a
  universal rule" instruction.
- **The gap**: there is exactly one authority profile, and its evidence base
  is the one spec document, not multiple real cases from Petah Tikva or any
  other municipality. "Built from evidence" today means "built from one
  provided document," which the mission's Phase 1-2 would need to widen.

## Geometry / measurement

- `drawing/geometry.py` — axis-aligned box geometry, `clear_gap` (edge-to-edge
  distance, not centroid-to-centroid), used by every distance/clearance
  check in the codebase (including the new `cross_source.py`).
- `units.py` — unit conversion and conservative rounding (a measurement never
  rounds in the direction that would hide a violation).
- **How it was built**: general-purpose computational geometry, not
  domain-specific. This layer is not spec-derived and needs no real-permit
  validation beyond "is the arithmetic correct" (it is, and is unit-tested).
- **The gap**: none functionally; the open question is only which
  *measurements* real comments actually ask for (Phase 1 question 6:
  "which comments are measurable?") — the geometry primitives themselves
  already cover box distance/area/dimension, which has covered every
  example seen so far.

## Planning

- `planner.py` — Step 7: turns a `Requirement` + its mapped elements into a
  `CorrectionPlan` (strategy, alternatives, confidence, consultation
  reasons).
- `planning_alternatives.py` — multi-disciplinary alternative structures
  (spec §25/§45): when one discipline's fix would break another's
  constraint, plans carry ranked alternatives instead of a single answer.
- **The gap**: the alternatives structure was built to match the spec's
  worked examples of trade-offs (e.g. a parking-width fix that would
  encroach on a drainage easement). It has never been asked to resolve a
  trade-off from an actual pair of real, independently-issued departmental
  comments.

## ChangeSet / execution / simulation

- `changeset.py` — the diff format: exactly what changed, expressed in the
  CAD tool's own terms (not a generic geometry diff).
- `simulate.py` — Step 8: dry-runs a plan against a sandboxed driver copy
  before anything is written (`DrawingDriver.sandbox()`).
- `execute.py` — Step 10: the only code path allowed to call a mutating
  drawing-API method, always inside `driver.authorised(plan_id)`.
- **How it was built / gap**: this triad is pure safety mechanism, not
  domain knowledge — it is real, tested, and does not need real permit data
  to be correct. It is the layer every other phase's output eventually flows
  through, so it is also the layer Phase 1-9 work must never bypass (the
  mission's Phase 12 boundary — "propose/simulate/validate, never certify" —
  is enforced structurally here, not just by policy).

## Validation

- `validate.py` — Step 11: re-measures the post-change model and confirms
  the original requirement is now satisfied (never trusts the plan that
  produced the change).
- `evidence/checker.py` — document/professional-approval completeness
  checking (spec §28): is the required evidence present, current, and
  signed by an authorized role.
- `readiness.py` — the submission-readiness gate (spec §24/§47): rolls up
  every open requirement/evidence/approval into a single "ready to
  resubmit" verdict.
- **How it was built**: same as constraints — logic is real and generically
  correct (it doesn't "know" Petah Tikva-specific facts, it re-measures
  whatever `Requirement`/`Evidence` objects it's given). Its correctness
  therefore rides entirely on Phase 1-6 supplying real requirements to
  validate against.

## Evidence / professional approvals

- `evidence/model.py`, `evidence/graph.py` — `Evidence`/`Approval` dataclasses
  with provenance and expiry (`EXPIRED` status added in an earlier pass),
  and a project-wide evidence dependency graph.
- `professionals/roles.py`, `professionals/approvals.py` — named professional
  roles (traffic engineer, acoustic consultant, etc.) and cross-project
  approval tracking.
- **The gap**: the same one as everywhere else — the *roles* and *evidence
  types* (acoustic report, hydrologic report, tree survey) are the ones the
  spec named. A real corpus would very likely surface more (or different)
  document/role types Phase 1-4 haven't seen yet, and might show some of
  these are rare enough to deprioritize per Phase 9's frequency/impact
  ranking.

## Adapters (multi-source orchestration)

- `adapters/{base,registry,json_model,dwg,pdf,revit}.py` — one `DrawingDriver`
  interface, multiple backends: the JSON reference driver (fully real, used
  by every example project), a headless DXF driver via `ezdxf` (real, tested
  against actual `.dxf` files), a live Revit/AutoCAD driver over a custom
  socket protocol (`drawing/protocol.py`, `drawing/mock_host.py` simulates
  the wire protocol without either CAD tool installed), and a PDF adapter for
  report/appendix ingestion (text-only, via `pdftotext`).
- `cross_source.py` — real geometric conflict detection between two
  independently-opened drivers sharing one site coordinate system (reuses
  `geometry.clear_gap`, does not duplicate measurement logic).
- **The gap most worth naming explicitly**: the Revit/AutoCAD *drivers*
  (`drawing/revit.py`, `drawing/dwg.py`) and the wire protocol have real,
  tested logic **against the mock host** — they have never been proven
  against an actual running Revit or AutoCAD session, because that requires
  Windows and licensed software this environment cannot provide. The
  `revit-addin/`, `autocad-addin/` C# projects (~3,460 lines) that would run
  *inside* those applications are written and internally consistent with the
  Python-side protocol, but have never been compiled or loaded into Revit/
  AutoCAD. This is a pre-existing, previously-disclosed limitation (see
  their own READMEs), not new to this audit — repeating it here because
  Phase 11's "CAD strategy" classification depends on knowing which drivers
  are proven-real vs. logically-complete-but-unverified.
- A minimal, dependency-free IFC (STEP/SPF) reader exists
  (`drawing/ifc_model.py`) but is deliberately **not** wired into
  `adapters/registry.py` as a live driver — entity type + GlobalId + Name
  only, no geometry, by its own docstring's scope statement.

## Web Editor

- `web/server.py`, `web/static/app.js` (`PlanViewer`, `ModelEditor`),
  `manual_edit.py` — a real browser UI: runs the full pipeline with live
  consultation, shows six result tabs, and (newer) lets a human directly
  select/move/resize/delete an element with the same versioning/audit
  guarantees as an AI-proposed correction.
- **How it was built / relation to the mission**: this already matches
  Phase 10's warning almost exactly — "must not become a generic CAD clone"
  was the explicit design constraint when manual editing was added (move/
  resize/delete only, snapped to existing elements, no free-drawing, no
  layer manager). No change needed here structurally; the open question is
  the same as elsewhere — which of its features actually get used once real
  permit cases start flowing through it, versus which were speculative.

## Multi-source orchestration

- `orchestrator.py` accepts `sources=[...]` (one or more adapters/files) and
  runs the same 11-step pipeline per source, then `cross_source.py` checks
  the results against each other. Proven end-to-end with two independent
  JSON files (a "civil" and an "architecture" drawing sharing site
  coordinates), not yet with a real pair of independently-authored
  discipline drawings from an actual project.

## PDF / document analysis

- `adapters/pdf.py` — shells out to `pdftotext` (Poppler) for text
  extraction; no layout/table/image understanding beyond that.
- `evidence/checker.py` treats a PDF's *presence and metadata* (is it there,
  is it current, is it signed off) as the checkable unit — it does not read
  a PDF's engineering content (e.g. it cannot verify an acoustic report's
  numbers are correct, only that the report exists and was approved by an
  authorized role). This is a stated scope boundary, not an oversight.

---

## Summary: what Phase 1 actually needs to change

Nothing above is broken, and the instruction not to rewrite working
components is easy to honor — the architecture (11-step pipeline, typed
semantic modules, YAML-driven authority profiles, safety-gated execution,
independent re-validation) is sound and was built to be data-driven exactly
where the mission wants it to be. What's missing is not code, it's **input**:
every requirement pattern, geometry threshold, semantic object, and evidence
type currently traces to one spec document plus a corpus I wrote to match
it. Phase 1 (real permit intelligence) and Phase 3 (a real `PermitCase`
corpus) are the actual next steps, not new engine code — and until real
cases exist, Phases 5-9 (discover objects, build the requirement library,
measure accuracy, find gaps) have nothing to run against.
