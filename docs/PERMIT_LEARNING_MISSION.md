# Archagent — Deep Permit Learning & Real-World Validation Mission

> Charter document. Given verbatim by the project owner (2026-08-27) as the
> mission that supersedes "add more capabilities" as the agent's default
> mode. Kept here, not just in chat history, so any future session (human or
> agent) can re-read it before deciding what to build next. See
> `ARCHITECTURE_MAP.md` in this directory for the Phase 0 output this
> charter required before any further implementation.

## Mission

You are no longer working only as a software implementation agent.

Your mission is to evolve Archagent using real-world permit processes, municipal requirements, actual permit comments, planning documents, drawings, and approved project artifacts.

The goal is to make the system understand how a real building permit progresses from:

Municipal comment
→ requirement
→ affected discipline
→ affected drawing/model/document
→ required correction
→ validation
→ professional approval
→ resubmission

Do not guess what the permit domain requires.

Learn from real permit cases and use the findings to improve the existing system.

---

## PHASE 0 — FIRST UNDERSTAND THE CURRENT SYSTEM

Before adding major functionality:

1. Inspect the complete current repository.
2. Understand the existing architecture.
3. Identify what already exists.
4. Identify partially implemented features.
5. Identify assumptions in the current code.
6. Do not rewrite existing working components.

Create an internal map of:

- permit parsing
- municipal comments
- semantic model
- constraints
- requirements
- geometry
- measurement
- planning
- ChangeSet
- simulation
- validation
- evidence
- professional approvals
- adapters
- Web Editor
- multi-source orchestration
- Revit
- DXF/DWG
- PDF/document analysis

The first objective is understanding before implementation.

---

## PHASE 1 — REAL PERMIT INTELLIGENCE

Build a research layer around real permits.

Use only:

- publicly available permit information
- public municipal planning portals
- public planning documents
- public regulatory documents
- documents explicitly provided or authorized by the user

Do not bypass authentication.
Do not access private permit data without authorization.
Do not circumvent access controls.

For each real permit source, determine:

1. What authority is involved?
2. What type of project is it?
3. What permit stage is visible?
4. What disciplines are involved?
5. What comments were issued?
6. Which comments are measurable?
7. Which comments require geometry changes?
8. Which comments require documents?
9. Which comments require professional approval?
10. Which comments are conditional?
11. Which comments depend on another discipline?

The goal is to extract structure, not merely store raw text.

---

## PHASE 2 — CONNECT TO PUBLIC PERMIT SOURCES

Research whether the following sources can be accessed through official public interfaces:

- municipal permit portals
- planning authority systems
- public planning document repositories
- iPlan / planning information where relevant
- municipal GIS portals
- public objection/approval records
- published permit decisions
- public regulatory databases

For each source, document:

```text
Source
Authority
Public URL
Access method
Authentication required?
Document types available
Data freshness
Legal/technical restrictions
Potential Archagent use
```

Do not build a scraper blindly.

First determine whether:

1. an official API exists
2. an official export exists
3. structured data exists
4. public documents can be downloaded
5. the source should be integrated manually rather than automatically

Prefer official APIs and official public datasets.

---

## PHASE 3 — BUILD A PERMIT CASE CORPUS

Create a normalized internal corpus.

Conceptually:

```text
PermitCase
├── Authority
├── ProjectMetadata
├── PermitStage
├── ReviewRound[]
├── Requirement[]
├── Document[]
├── ModelSource[]
├── Evidence[]
├── Approval[]
├── Change[]
└── Outcome
```

Each requirement should contain:

```text
requirement_id
source
source_text
normalized_requirement
discipline
subdiscipline
type
stage
affected_elements
affected_documents
condition
constraint
measurement
unit
status
evidence_required
approval_required
resolution_method
validation_method
confidence
```

Never discard the original wording.

The normalized structure must always retain provenance.

---

## PHASE 4 — LEARN FROM REAL COMMENTS

For every collected municipal comment:

```text
Raw Comment
    ↓
Semantic Interpretation
    ↓
Requirement Type
    ↓
Discipline
    ↓
Affected Object
    ↓
Constraint
    ↓
Required Evidence
    ↓
Required Approval
    ↓
Resolution Method
    ↓
Validation Method
```

Example:

```text
Raw:
"להגדיל את רוחב החניה"

Normalized:
discipline = traffic
object = parking_space
type = geometry + measurement

Constraint:
width >= required_width

Resolution:
resize parking geometry

Validation:
deterministic measurement
```

Another example:

```text
Raw:
"יש להגיש דו״ח אקוסטי"

Normalized:
discipline = environment
type = document

Resolution:
request evidence

Validation:
document presence + metadata + professional approval
```

The system must learn that these are fundamentally different task types.

---

## PHASE 5 — DISCOVER SEMANTIC OBJECTS FROM REAL DATA

Do not invent the complete semantic model in advance.

Analyze real permits to discover recurring objects.

For example:

```text
Architecture
- building
- floor
- wall
- room
- balcony
- facade

Traffic
- parking_space
- accessible_parking
- drive_aisle
- ramp
- turning_area

Roads
- road
- sidewalk
- curb
- crossing

Drainage
- drainage_line
- pipe
- chamber
- catch_basin
- overflow

Landscape
- tree
- planting_area
- permeable_area

Documents
- acoustic_report
- hydrologic_report
- tree_survey
```

Add semantics only when:

1. they recur in real permit requirements
2. they enable deterministic validation
3. they enable meaningful cross-discipline reasoning

Avoid creating hundreds of unused semantic classes.

---

## PHASE 6 — BUILD A REQUIREMENT LIBRARY

Create a reusable requirement library.

Example:

```text
RequirementTemplate

id:
parking.minimum_width

discipline:
traffic

semantic_object:
ParkingSpace

constraint:
width >= threshold

parameters:
threshold
location
parking_type

resolution_methods:
- resize
- reposition
- redesign_layout

validation:
geometry_measurement

evidence:
optional

professional_approval:
traffic_engineer
```

Requirements must be parameterized.

Do not hardcode municipality-specific numbers directly into the core engine.

Use:

```text
Core Requirement Engine
        +
Authority Profile
        +
Project Context
        +
Regulatory Parameters
```

---

## PHASE 7 — AUTHORITY PROFILES

Build municipality profiles from evidence.

For example:

```text
PetahTikvaProfile
├── terminology
├── departments
├── review stages
├── common requirement patterns
├── document requirements
├── routing rules
└── known workflow gates
```

The system must distinguish between:

```text
Universal rule
Authority-specific rule
Project-specific requirement
Professional judgement
```

Never promote a single municipal comment into a universal engineering rule.

---

## PHASE 8 — REAL-WORLD VALIDATION LOOP

For every new capability:

```text
Real Permit Case
      ↓
Archagent Interpretation
      ↓
Expected Requirement
      ↓
Expected Discipline
      ↓
Expected Resolution Type
      ↓
Validation
```

Measure:

```text
comment classification accuracy
discipline routing accuracy
element mapping accuracy
constraint extraction accuracy
false positive rate
false negative rate
successful resolution rate
validation accuracy
```

Create regression tests from anonymized or public real cases.

The goal is empirical improvement.

---

## PHASE 9 — GAP DISCOVERY

Use real permit cases to discover missing capabilities.

For every requirement Archagent cannot handle, classify why:

```text
MISSING_SEMANTIC_OBJECT
MISSING_PARSER
MISSING_CONSTRAINT
MISSING_GEOMETRY_OPERATION
MISSING_VALIDATOR
MISSING_DOCUMENT_ANALYSIS
MISSING_EVIDENCE_MODEL
MISSING_APPROVAL_WORKFLOW
MISSING_EXTERNAL_INTEGRATION
REQUIRES_PROFESSIONAL_JUDGEMENT
```

Then prioritize gaps by:

```text
frequency
impact
automation potential
implementation effort
cross-municipality reuse
```

Do not randomly add features.

Implement the highest-value gaps discovered from real permit cases.

---

## PHASE 10 — WEB EDITOR FEEDBACK LOOP

Use real requirements to improve the existing Web Editor.

The editor should expose:

```text
Requirement
↓
Affected semantic objects
↓
Measured values
↓
Violation
↓
Proposed change
↓
Before/After
↓
Validation result
```

The editor must not become a generic CAD clone.

Every major editing feature must answer:

"Which real permit workflow requires this capability?"

If no answer exists, deprioritize it.

---

## PHASE 11 — EXTERNAL CAD STRATEGY

For each requirement determine the minimum necessary CAD capability.

Classify:

```text
INTERNAL_ENGINE_SUFFICIENT

DXF_SUFFICIENT

REVIT_REQUIRED

CIVIL3D_REQUIRED

IFC_SUFFICIENT

PROFESSIONAL_REVIEW_REQUIRED
```

The objective is to maximize:

```text
INTERNAL_ENGINE_SUFFICIENT
```

without falsely claiming support for proprietary CAD semantics.

Do not require Revit if semantic geometry can be represented and validated internally.

---

## PHASE 12 — PROFESSIONAL BOUNDARIES

The system may:

* detect
* classify
* measure
* simulate
* propose
* validate modeled requirements
* request evidence
* track approvals

The system must not claim:

```text
municipal approval
engineering certification
professional sign-off
legal approval
```

unless such approval actually exists as evidence.

---

## PHASE 13 — IMPLEMENTATION PRIORITY

Priority order:

P0:

1. Real permit corpus
2. Public/authorized permit source research
3. Requirement normalization
4. Requirement library
5. Authority profiles
6. Real-world regression tests

P1:
7. Semantic gaps discovered from real permits
8. Deterministic validators
9. Cross-discipline dependencies
10. Evidence and approval tracking

P2:
11. New editor operations
12. Additional CAD integrations
13. Advanced 3D/Civil semantics

---

## PHASE 14 — CONTINUOUS LEARNING MODE

After every real permit case:

1. Preserve the raw evidence.
2. Normalize the requirements.
3. Compare with existing knowledge.
4. Detect duplicates.
5. Detect new patterns.
6. Detect new semantic objects.
7. Detect missing validators.
8. Add regression tests.
9. Update the requirement library.
10. Update authority profiles only when evidence supports it.

The system must become better from each case.

But never allow uncontrolled automatic learning directly into production rules.

All new rules must be:

```text
DISCOVERED
→
EVIDENCE_LINKED
→
REVIEWED
→
TESTED
→
APPROVED
→
ACTIVE
```

---

## SUCCESS CRITERIA

Success is NOT:

"More agents"
"More tools"
"More code"
"More CAD features"

Success is:

A real permit enters the system.

Archagent can:

1. Understand what the authority actually requires.
2. Identify the affected discipline.
3. Identify the affected model/document.
4. Determine whether the requirement is geometric, documentary, approval-based or conditional.
5. Propose a valid action.
6. Perform or prepare the action safely.
7. Validate what can be validated deterministically.
8. Request professional approval when required.
9. Preserve evidence.
10. Learn from the case through tested regression data.

The target architecture is:

```text
REAL PERMIT DATA
      ↓
PERMIT CASE CORPUS
      ↓
REQUIREMENT NORMALIZATION
      ↓
SEMANTIC MODEL
      ↓
DETERMINISTIC CONSTRAINTS
      ↓
MULTI-DISCIPLINE PLANNING
      ↓
SAFE MODEL EDITING
      ↓
INDEPENDENT VALIDATION
      ↓
EVIDENCE / APPROVAL
      ↓
REGRESSION LEARNING
```

Do not implement blindly.

First understand reality.
Then identify recurring patterns.
Then extend Archagent only where real evidence shows a capability gap.
