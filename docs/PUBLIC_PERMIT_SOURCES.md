# Phase 2 — Public Israeli Permit/Planning Sources

Research done per `PERMIT_LEARNING_MISSION.md` Phase 2: for each candidate
public source, whether an official API/export exists before any thought of
building an integration. Done via web search only (see **Session
limitation** below) — every entry needs a second, deeper pass once the
question in the final section is answered, before any code is written
against it.

**Session limitation, stated plainly:** this sandbox's network egress proxy
blocked direct `WebFetch` to `data.gov.il` and `petah-tikva.muni.il` outright
(`EGRESS_BLOCKED`) — search-engine results still came through, so every row
below is built from search snippets, not from reading the sites' own
interface/API documentation first-hand. Nothing here should be treated as
verified until someone (this agent from a less restricted session, or the
project owner) actually opens these URLs and confirms.

---

## רישוי זמין (the national building-permit licensing system)

```
Source:        רישוי זמין ("Licensing Ready")
Authority:     Israeli government (established 2006, "accessible government"
               initiative), operated per-municipality
Public URL:    reachable via gov.il; exact login portal not confirmed this
               session (see limitation above)
Access method: web application; a submitter (architect/engineer/owner of
               record) logs in to track *their own* permit file
Auth required: yes - this is exactly the authentication the mission
               instructs not to bypass
Document types: the permit application itself, the full review-comment
               history per department, decisions, uploaded drawings/reports
Data freshness: live, per active case
Restrictions:  no evidence of a public read API found; access is scoped to
               the case's own submitter/professional, by design
Archagent use: THIS is the actual source of the thing Archagent processes -
               real, department-issued review comments, per real case, with
               a real outcome. It is also the one source in this list that
               cannot be reached without being a party to a real permit
               file. Not integratable as "public research"; only usable
               through documents a user with legitimate access explicitly
               supplies (Phase 1's third allowed source).
```

## מידע תכנוני / MAVAT (mavat.iplan.gov.il) - Planning Administration

```
Source:        אתר מידע תכנוני (Planning Information Site), Planning
               Administration (מנהל התכנון)
Authority:     national (Israel Ministry of Finance / Planning
               Administration)
Public URL:    https://mavat.iplan.gov.il/
Access method: web search UI over statutory plans (תב"ע), objections,
               planning-committee meetings (agendas/protocols/decisions)
Auth required: browsing/search appears public; submitting an objection to
               a deposited plan requires identification
Document types: plan documents, meeting protocols and decisions, deposited-
               plan objection records
Data freshness: live, updated as committees act
Restrictions:  this is statutory/zoning-plan level (city-wide or district
               master plans, changes to permitted use/coverage/height) -
               not individual building-permit review comments. A real
               project's applicable zoning constraints (what feeds
               archagent's authority-profile "regulatory parameters", not
               its comment corpus) could legitimately come from here.
Archagent use: candidate source for zoning/constraint *parameters* (plot
               coverage, setback, height limits for a given plan number) -
               not for Phase 3's PermitCase/ReviewRound/comment corpus.
```

## Xplan (ags.iplan.gov.il/xplan) - approved plans / blue lines

```
Source:        Xplan - "קווים כחולים" (approved-plan boundary layer)
Authority:     Planning Administration
Public URL:    https://ags.iplan.gov.il/xplan/
Access method: GIS map service (ArcGIS Server pattern, per the URL shape)
Auth required: appears public for viewing
Document types: geometric plan boundaries, not text requirements
Restrictions:  GIS geometry, not requirement text
Archagent use: potential source of real site/plot geometry (the `site`
               boundary a project's semantic model needs), not requirements
               or comments.
```

## GovMap (govmap.gov.il) - national plan locator

```
Source:        GovMap, "איתור תוכניות בניין עיר" (locate city-building plans)
Authority:     Survey of Israel / national government mapping
Public URL:    https://www.govmap.gov.il/?app=app07
Access method: public web map application
Auth required: no, for viewing/searching
Document types: plan lookup by address/parcel, links out to the plan
               documents themselves (likely hosted on MAVAT)
Archagent use: a way to find *which* statutory plan governs a given real
               address, as a starting point before pulling that plan's
               actual constraints from MAVAT.
```

## data.gov.il - national open-data portal

```
Source:        data.gov.il, "מינהל התכנון" (Planning Administration)
               organization page
Authority:     Israeli government open-data initiative
Public URL:    https://data.gov.il/he/organizations/iplan (dataset example
               seen: https://data.gov.il/dataset/iplan-itur-tochnit)
Access method: CKAN (the same open-source data-portal platform data.gov and
               data.gov.ie run) - CKAN's own documented REST API
               (`/api/3/action/package_list`, `package_show`, etc.) returns
               dataset *metadata*; actual resource files are separate
               downloads (CSV/GIS formats are typical for a CKAN "plan
               location" dataset, but which formats this specific dataset
               offers was not confirmed - see limitation above)
Auth required: no, for public datasets
Restrictions:  metadata-only via the API; the real content is whatever
               format the resource file itself is - needs to actually be
               downloaded and opened to know what it usefully contains
Archagent use: the most promising *scriptable* public source for
               zoning/plan-location data - genuinely worth a real,
               unrestricted-session pass (fetch `package_show` for the
               iplan datasets, look at what resources they actually list).
```

## Petah Tikva municipality - engineering/GIS portal

```
Source:        עיריית פתח תקווה, אגף הנדסה - "תיק מידע להיתר" (permit
               information file) and "איתור מידע" (information lookup)
Authority:     Petah Tikva municipality (the one authority profile this
               repo already has)
Public URL:    https://www.petah-tikva.muni.il/engineering/...
Access method: web pages describing the process; the actual information
               file itself is requested and paid for through the online
               licensing system (i.e. רישוי זמין, municipality-scoped)
Auth required: requesting the file itself requires being a licensed
               engineer/technician/architect ("only submitted by a licensed
               [professional] with a valid license", per the page's own
               description) plus a fee
Document types: the file covers spatial/zoning info for the specific plot,
               permitted uses, licensing-authority data (sanitation,
               traffic) and other bodies (electric company, antiquities
               authority, KKL) - this is the *pre-submission* context
               package, not the review-round comment history
Archagent use: same shape as רישוי זמין above - real and specific to this
               repo's one authority profile, but gated behind a
               professional credential, not scrapeable as "public research".
```

---

## What Phase 2 actually concludes

Public, no-login sources (MAVAT, Xplan, GovMap, data.gov.il) carry real,
authoritative **zoning/plan-level** data - genuinely useful for grounding an
authority profile's regulatory parameters in a real, citable plan number
instead of a spec document's worked example. None of them carry the thing
Phase 3's corpus actually needs: real, department-issued **review comments**
on a real submitted permit, with a real resolution and outcome. That data
structurally lives inside רישוי זמין, scoped to the professional/owner of
record on that specific case - by design, not by an accident of missing
public tooling.

This means Phase 3 (build a real `PermitCase` corpus) cannot proceed by
scraping; it needs either (a) real permit files the project owner has
legitimate access to and can supply directly - the explicitly-allowed third
source in Phase 1 - or (b) published, anonymized case studies / research
datasets, if any exist, which is a distinct and much smaller search than
"government portals" and hasn't been done yet. Recommending (a) as the next
concrete step rather than continuing (b) speculatively.
