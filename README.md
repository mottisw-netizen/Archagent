# archagent

An implementation of the **AI Municipal Permit Drawing Review and Correction Agent**
specified in [`.claude/skills/municipal-permit-review/SKILL.md`](.claude/skills/municipal-permit-review/SKILL.md).

It takes municipal permit comments plus a drawing, works out what each comment
demands, finds the elements it refers to, computes the minimum change that
satisfies it without breaking anything else, applies that change through a
drawing-editing API, and proves the result by measuring it.

```
comment → interpretation → elements → constraints → dependencies
        → solution → simulation → consultation → execution → validation → report
```

## Install and run

```bash
pip install -e ".[dev]"

archagent comments examples/project                     # how each comment is read
archagent run examples/project --answers examples/answers.json
archagent run examples/project --mode autonomous
archagent validate examples/project/source/project.json examples/project/constraints/zoning_plan.md
```

Without installing: `PYTHONPATH=src python3 -m archagent.cli run examples/project`.

The example run produces, under `examples/project/`:

| Path | What it is |
| --- | --- |
| `versions/v1/`, `versions/v2/` | immutable model versions, each with `version.json` and `audit.jsonl` |
| `versions/project_original.json` | the untouched original |
| `output/<run>/correction_report.md` | the correction report (SKILL.md 15) |
| `output/<run>/compare_before_after.html` | before/after slider with a change table |
| `output/<run>/preview_v2_changes.svg` | highlighted change map (colour **and** text tag) |
| `output/<run>/validation_report.json` | measured constraint and comment validation |
| `output/<run>/project_context.json` | the full run state, resumable and auditable |

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
| 13 Preview and highlights | `archagent/preview.py` |
| 14 Validation | `archagent/validate.py` |
| 15 Correction report | `archagent/report.py` |
| 16 Safety, versioning, audit | `archagent/versioning.py`, `archagent/audit.py` |
| 20 Confidence model | `archagent/models.py` (`Confidence`) |
| 22 Units and rounding | `archagent/units.py` |
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
  re-verified at the end of every run.
- **Ambiguity is never resolved silently** - it consults or escalates.

## Connecting a real CAD/BIM model

`JSONModelDriver` is a reference implementation over a plain JSON plan model
(axis-aligned geometry, sheets, schedules) so the pipeline runs and is testable
without a CAD seat. To drive Revit/AutoCAD/IFC, implement
`archagent.drawing.api.DrawingDriver` against the host API and pass it in;
nothing above the driver layer changes. The contract each method must honour -
including the `before`/`after` change record and the measurement basis - is
documented in `api.py`.

PDF comment text is read via `pdftotext` if present, or a hook you register at
`archagent.ingest.PDF_TEXT_EXTRACTOR`. If neither is available, the file is
reported as unreadable and listed as an open item - the agent never guesses
what a comment said.

## Tests

```bash
python3 -m pytest -q      # 82 tests
```

## Scope

Output is a proposal. It requires review and approval by the responsible
licensed professional before submission to any authority; every generated
report carries that sign-off block.
