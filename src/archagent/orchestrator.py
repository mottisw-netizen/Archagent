"""The orchestrator (SKILL.md 2, 5, 19).

Runs the fixed pipeline: ingest, analyse comments, extract constraints,
analyse the drawing, map comments to elements, build the dependency graph,
plan, simulate, consult, execute, validate, preview, report.  No step is
skipped and the drawing is never modified straight after reading a comment.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from . import lang
from . import changeset
from . import preview as preview_module
from .audit import AuditLog
from .comments import CommentAnalyzer
from .constraints import (
    ConstraintLedger,
    constraints_from_comments,
    constraints_from_document,
    derive_implicit_constraints,
    find_conflicts,
)
from .consult import ConsultationAgent, Responder, apply_decision, auto_approve, defer
from .drawing.api import DrawingAPIError, DrawingDriver
from .execute import ExecutionAgent
from .graph import build_graph, impact_set, merge_graphs
from .adapters import AdapterRegistry, OpenSource, Router, Routing, SourceRef, Workspace, default_registry
from .ingest import Ingestor
from .lang.messages import Messages
from .llm.client import LLMClient
from .llm.disambiguate import ElementDisambiguator
from .llm.interpret import LLMCommentInterpreter, inventory_from_driver
from .llm.summarise import RunSummariser, facts_for
from .mapping import ElementMapper
from .models import (
    ChangeRecord,
    CommentStatus,
    CommentValidation,
    CorrectionPlan,
    Decision,
    Mode,
    ProjectContext,
    ValidationResult,
    VersionManifest,
    new_id,
)
from .payload import run_payload
from .planner import PlanProposal, Planner
from .report import build_report
from .simulate import baseline_status
from .validate import ValidationAgent
from .versioning import VersionStore, verify_original

#: Changes that autonomous mode never makes without a human (SKILL.md 4.3).
HARD_ESCALATION = ("floor_area", "count")


@dataclass
class RunResult:
    context: ProjectContext
    validation: ValidationResult | None = None
    changes: list[ChangeRecord] = field(default_factory=list)
    plans: list[CorrectionPlan] = field(default_factory=list)
    decisions: list[Decision] = field(default_factory=list)
    version: str = ""
    parent_version: str = ""
    files: dict[str, str] = field(default_factory=dict)
    graph: dict = field(default_factory=dict)
    impact: list[str] = field(default_factory=list)
    #: The Diff / Change Set: what changed, by the host's own element ids.
    change_set: dict = field(default_factory=dict)
    definition_of_done: list[tuple[str, bool]] = field(default_factory=list)
    report: str = ""
    consulted: set[str] = field(default_factory=set)
    language: str = "en"
    llm: dict = field(default_factory=dict)

    @property
    def complete(self) -> bool:
        return all(ok for _text, ok in self.definition_of_done)


class Orchestrator:
    def __init__(self, project_dir, mode: str = Mode.CONSULTATION.value,
                 responder: Responder | None = None, threshold: float = 0.85,
                 output_dir=None, analyzer: CommentAnalyzer | None = None,
                 llm: LLMClient | None = None, language: str = "auto",
                 effort: str | None = None, on_event=None,
                 sources: list | None = None,
                 registry: AdapterRegistry | None = None):
        self.project_dir = Path(project_dir)
        self.mode = Mode(mode)
        self.threshold = threshold
        self.llm = llm
        self.effort = effort
        self.language = language
        #: Report language; replaced once the comments have been read.
        self.m = Messages("en" if language == "auto" else language)
        self.analyzer = analyzer or CommentAnalyzer()
        self.responder = responder or (auto_approve if self.mode is Mode.AUTONOMOUS else defer)
        self.run_id = new_id("RUN")
        self.output_dir = Path(output_dir) if output_dir else self.project_dir / "output" / self.run_id
        self.versions = VersionStore(self.project_dir / "versions")
        self.audit = AuditLog(self.output_dir / "audit.jsonl", listener=on_event)
        self.ledger = ConstraintLedger()
        self.consultation = ConsultationAgent(self.responder, self.m)
        self.driver: DrawingDriver | None = None
        #: Every drawing of the package, opened through its adapter.
        self.registry = registry or default_registry()
        self.workspace = Workspace(self.registry)
        self.router = Router(self.workspace)
        self.sources = [source if isinstance(source, SourceRef) else SourceRef.parse(str(source))
                        for source in (sources or [])]
        self._simulated: set[str] = set()

    # ------------------------------------------------------------------
    def run(self) -> RunResult:
        context = self._ingest()
        result = RunResult(context=context)
        if context.execution_mode == "markup_only":
            return self._finish_markup_only(result)

        assert self.driver is not None
        parent = self._store_parent_version(context)
        result.parent_version = parent

        self._analyze_comments(context)
        self._build_ledger(context)

        routings = self._route(context)
        scopes = self._editable_scopes(routings)
        for scope in scopes:
            derive_implicit_constraints(scope.driver, self.ledger, self.m)

        graphs = []
        validations = []
        merged_baseline: dict[str, str] = {}
        primary = self._primary_scope()
        for scope in scopes:
            comment_ids = {cid for cid, routing in routings.items() if routing.source is scope}
            if not comment_ids and scope is not primary:
                # Nothing was routed here; opening it cost nothing and it has
                # nothing to contribute to this run.
                continue

            baseline = baseline_status(scope.driver, self.ledger)
            for constraint_id, status in baseline.items():
                merged_baseline.setdefault(constraint_id, status)
            if scope is primary:
                self.audit.write("orchestrator", "baseline", result=baseline)

            self._map_comments(context, scope, comment_ids)
            proposals = self._plan(context, scope, comment_ids, baseline)
            scope_plans = [proposal.plan for proposal in proposals.values() if proposal.plan]
            result.plans.extend(scope_plans)

            changes, decisions, consulted = self._decide_and_execute(
                context, scope, proposals, baseline)
            result.changes.extend(changes)
            result.decisions.extend(decisions)
            result.consulted |= consulted

            graphs.append(build_graph(scope_plans, self.ledger.all, scope.driver))

            applied = {change.comment_id for change in result.changes if change.comment_id}
            comments_here = [context.comment(cid) for cid in comment_ids]
            validator = ValidationAgent(scope.driver, self.ledger, baseline, self.m)
            validations.append((scope, validator.validate(
                self.versions.next_version(), comments_here, applied)))

        graph = merge_graphs(graphs)
        for cycle in graph.cycles():
            context.add_open_item(" -> ".join(cycle), self.m.t("r_cycle"),
                                  self.m.t("n_precedence"))
        result.graph = graph.to_dict()
        result.impact = impact_set(graph, result.plans)

        result.validation = self._merge_validations(context, validations, routings)
        self.audit.write("validation_agent", "validation_result",
                         result=result.validation.result)

        self._record_open_items(context, result)
        result.version = self._store_new_version(context, result, parent, scopes)
        result.files = self._write_artefacts(context, result, parent, scopes, merged_baseline)
        result.definition_of_done = self._definition_of_done(context, result)
        narrative = self._narrative(context, result)
        result.report = build_report(
            context, result.validation, result.changes, result.plans, result.decisions,
            result.version, parent, result.files, result.definition_of_done,
            result.consulted, self.m, narrative)
        report_path = self.output_dir / "correction_report.md"
        report_path.write_text(result.report, encoding="utf-8")
        result.files["correction_report"] = str(report_path)
        result.language = self.m.code
        result.llm = self._llm_summary()
        if result.llm:
            self.audit.write("orchestrator", "llm_usage", result=result.llm)
        payload_path = self.output_dir / "run_payload.json"
        payload_path.write_text(
            json.dumps(run_payload(result, self.m), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8")
        result.files["run_payload"] = str(payload_path)
        self.audit.write("orchestrator", "run_complete", result=result.validation.result)
        return result

    # ------------------------------------------------------------------
    # step 1
    # ------------------------------------------------------------------
    def _ingest(self) -> ProjectContext:
        self.ingestor = Ingestor(self.project_dir)
        manifest = self.ingestor.scan()
        context = ProjectContext(
            project_id=self.project_dir.name,
            run_id=self.run_id,
            input_manifest=manifest,
            operating_mode=self.mode.value,
            confidence_threshold=self.threshold,
        )
        self.audit.write("orchestrator", "ingest", result=f"{len(manifest)} files")
        self._set_language(context)
        models = [entry for entry in manifest
                  if entry.role == "source_model" and entry.read_status == "ok"
                  and entry.file.endswith(".json")]
        # A model inside /source wins over a stray JSON file elsewhere.
        models.sort(key=lambda entry: (f"{Path(entry.file).parent.name}" != "source",
                                       entry.file))
        for entry in manifest:
            if entry.read_status != "ok":
                context.add_open_item(entry.file,
                                      self.m.t("r_file_unreadable", notes=entry.notes),
                                      self.m.t("n_readable_copy"))
        sources = list(self.sources)
        if not sources and models:
            sources = [SourceRef.parse(models[0].file)]
        for source in sources:
            entry = self.workspace.add(source)
            self.audit.write("orchestrator", "source_opened",
                             params=source.to_dict(),
                             result=entry.adapter_name if entry.available else entry.error)
            if not entry.available:
                context.add_open_item(Path(source.location).name or source.location,
                                      entry.error or self.m.t("r_no_model"),
                                      self.m.t("n_driver"))
        context.sources = self.workspace.to_dict()

        self.driver = self.workspace.primary()
        self._source_entry = models[0] if models else None
        if self.driver is not None:
            first = next(entry for entry in self.workspace.opened if entry.driver is self.driver)
            context.source_format = first.adapter_name.upper()
            context.drawing_elements = getattr(self.driver, "elements", list)()
            if first.source.kind == "host":
                # A live host owns the document; the run edits it in place and
                # versions by exporting, so there is no ingest checksum to hold.
                self._source_entry = None
        else:
            context.execution_mode = "markup_only"
            context.source_format = "PDF_ONLY"
            context.add_open_item("source model", self.m.t("r_no_model"),
                                  self.m.t("n_driver"))
        self._attach_interpreter()
        return context

    def _narrative(self, context: ProjectContext, result: RunResult):
        """An opening paragraph, drawn only from measured results."""
        if self.llm is None or result.validation is None:
            return None
        facts = facts_for(context, result.validation, result.changes, self.m)
        summary, attention = RunSummariser(self.llm, self.effort).summarise(
            {"he": "Hebrew", "en": "English"}.get(self.m.code, "English"), facts)
        if summary:
            self.audit.write("orchestrator", "narrative", result="written")
        return (summary, attention) if summary else None

    def _llm_summary(self) -> dict:
        if self.llm is None:
            return {}
        summary = {
            "model": getattr(self.llm, "model", "unknown"),
            "calls": getattr(self.llm, "calls", 0),
            "usage": dict(getattr(self.llm, "usage", {}) or {}),
            "failures": list(self.analyzer.failures),
        }
        if hasattr(self.llm, "hits"):
            summary["cache_hits"] = self.llm.hits
            summary["cache_misses"] = self.llm.misses
        return summary

    def _set_language(self, context: ProjectContext) -> None:
        """The report speaks the language the comments were written in."""
        if self.language != "auto":
            code = self.language
        else:
            sample = " ".join(
                self.ingestor.text_of(entry)[:4000] for entry in context.input_manifest
                if entry.role == "municipal_comments")
            code = lang.detect_script(sample) if sample.strip() else "en"
            code = code if code in ("he", "en") else "en"
        self.m = Messages(code)
        self.consultation.m = self.m
        context.units = context.units or "m"
        self.audit.write("orchestrator", "language", result=code)

    def _attach_interpreter(self) -> None:
        """Claude reads the comments; the rule parser cross-checks it."""
        if self.llm is None or self.analyzer.interpreter is not None:
            return
        inventory = inventory_from_driver(self.driver) if self.driver is not None else []
        self.analyzer.interpreter = LLMCommentInterpreter(
            self.llm, inventory=inventory, effort=self.effort)
        self.audit.write("orchestrator", "llm_enabled",
                         result=getattr(self.llm, "model", "unknown"),
                         params={"inventory": len(inventory)})

    # ------------------------------------------------------------------
    # steps 2-3
    # ------------------------------------------------------------------
    def _analyze_comments(self, context: ProjectContext) -> None:
        index = 1
        for entry in context.input_manifest:
            if entry.role != "municipal_comments":
                continue
            text = self.ingestor.text_of(entry)
            if not text:
                continue
            comments = self.analyzer.analyze_document(
                text, source_ref=Path(entry.file).name, start_index=index)
            context.municipal_comments.extend(comments)
            index += len(comments)
        context.municipal_comments.sort(key=lambda comment: comment.comment_id)
        for comment in context.municipal_comments:
            self.audit.write("comment_analyzer", "comment_extracted",
                             params={"comment_id": comment.comment_id},
                             result=comment.normalized_requirement or comment.required_action)

    def _build_ledger(self, context: ProjectContext) -> None:
        for entry in context.input_manifest:
            if entry.role != "constraint":
                continue
            text = self.ingestor.text_of(entry)
            if not text:
                continue
            source = ("Zoning Plan" if "zoning" in Path(entry.file).name.casefold()
                      else "Project Requirement")
            constraints_from_document(text, source, Path(entry.file).name, self.ledger,
                                      self.analyzer, self.m)
        constraints_from_comments(context.municipal_comments, self.ledger, self.m)
        if self.driver is not None:
            derive_implicit_constraints(self.driver, self.ledger, self.m)
        context.planning_constraints = self.ledger.all
        for conflict in find_conflicts(self.ledger):
            self.audit.write("constraint_engine", "conflict", result=conflict)
            if conflict["requires_human"]:
                context.add_open_item(
                    " / ".join(conflict["constraints"]),
                    self.m.t("r_equal_conflict", rules=" / ".join(conflict["rules"])),
                    self.m.t("n_which_governs"))

    # ------------------------------------------------------------------
    # steps 4-7
    # ------------------------------------------------------------------
    def _route(self, context: ProjectContext) -> dict[str, Routing]:
        """Decide which adapter each comment belongs to (SKILL.md 2.1).

        A comment for a discipline whose adapter is unavailable - traffic on a
        consultant DWG, for instance - is not planned and not silently dropped:
        it becomes an open item naming the adapter and what it needs. Every
        comment gets a routing, whether or not it resolved to a source, so the
        caller can tell "worked here" from "worked nowhere" without re-asking.
        """
        routings: dict[str, Routing] = {}
        for comment in context.municipal_comments:
            routing = self.router.route(comment)
            routings[comment.comment_id] = routing
            context.routing.append(routing.to_dict())
            self.audit.write("orchestrator", "routed",
                             params={"comment_id": comment.comment_id,
                                     "discipline": routing.discipline},
                             result=routing.source.adapter_name if routing.routed
                             else routing.reason)
            if not routing.routed and routing.reason:
                context.add_open_item(comment.comment_id, routing.reason,
                                      routing.needed or self.m.t("n_human_decision"))
        return routings

    def _primary_scope(self) -> OpenSource | None:
        return next((entry for entry in self.workspace.opened if entry.driver is self.driver),
                   None)

    def _editable_scopes(self, routings: dict[str, Routing]) -> list[OpenSource]:
        """Every open source a plan can actually be written to this run.

        The primary architectural source is always first, even with no
        comments of its own this run, because parent/version bookkeeping and
        the spatial preview are keyed to it. Every other source that at least
        one comment was routed to, and that can edit, joins it - one run,
        every connected tool that has work.
        """
        scopes: list[OpenSource] = []
        primary = self._primary_scope()
        if primary is not None:
            scopes.append(primary)
        for routing in routings.values():
            source = routing.source
            if source is not None and source.can_edit() and not any(s is source for s in scopes):
                scopes.append(source)
        return scopes

    def _map_comments(self, context: ProjectContext, scope: OpenSource,
                      comment_ids: set[str]) -> None:
        disambiguator = (ElementDisambiguator(self.llm, self.effort)
                         if self.llm is not None else None)
        mapper = ElementMapper(scope.driver, self.m, disambiguator)
        for comment in context.municipal_comments:
            if comment.comment_id not in comment_ids:
                continue
            mapping = mapper.map_comment(comment)
            context.mappings.append(mapping)
            comment.affected_elements = list(mapping.selected)
            self.audit.write("drawing_analyzer", "mapping",
                             params={"comment_id": comment.comment_id, "adapter": scope.adapter_name},
                             result=mapping.resolution.value)

    def _plan(self, context: ProjectContext, scope: OpenSource, comment_ids: set[str],
              baseline: dict[str, str]) -> dict[str, PlanProposal]:
        planner = Planner(scope.driver, self.ledger, baseline, self.threshold, self.m)
        proposals: dict[str, PlanProposal] = {}
        for comment in context.municipal_comments:
            if comment.comment_id not in comment_ids:
                continue
            mapping = context.mapping(comment.comment_id)
            proposal = planner.plan_for(comment, mapping)
            proposals[comment.comment_id] = proposal
            if proposal.plan is not None:
                context.plans.append(proposal.plan)
                self._simulated.add(proposal.plan.plan_id)
                self.audit.write("orchestrator", "plan_generated",
                                 plan_id=proposal.plan.plan_id,
                                 result=proposal.plan.strategy)
            elif comment.required_action == "none":
                self.audit.write("orchestrator", "no_action_required",
                                 params={"comment_id": comment.comment_id})
            else:
                reason = "; ".join(proposal.reasons) or "no plan could be generated"
                needed = proposal.proposal_text or self.m.t("n_human_decision")
                context.add_open_item(comment.comment_id, reason, needed)
                self.audit.write("orchestrator", "plan_escalated",
                                 params={"comment_id": comment.comment_id}, result=reason)
        return proposals

    # ------------------------------------------------------------------
    # steps 9-10
    # ------------------------------------------------------------------
    def _decide_and_execute(self, context: ProjectContext, scope: OpenSource,
                            proposals: dict[str, PlanProposal], baseline: dict[str, str]):
        executor = ExecutionAgent(scope.driver, self.audit)
        changes: list[ChangeRecord] = []
        decisions: list[Decision] = []
        consulted: set[str] = set()

        for comment_id in self._execution_order(proposals):
            proposal = proposals[comment_id]
            plan = proposal.plan
            comment = context.comment(comment_id)
            if plan is None or plan.status == "already_compliant":
                continue
            mapping = context.mapping(comment_id)

            if plan.confidence.value < 0.60:
                context.add_open_item(
                    comment_id,
                    self.m.t("r_below_floor", value=f"{plan.confidence.value:.2f}",
                             component=plan.confidence.limiting_component),
                    self.m.t("n_review_interpretation"))
                plan.status = "escalated"
                continue

            if self._needs_consultation(plan):
                if self.mode is Mode.AUTONOMOUS:
                    blocked = self._autonomous_block_reason(plan)
                    if blocked:
                        context.add_open_item(comment_id, blocked,
                                              self.m.t("n_architect_decision"))
                        plan.status = "escalated"
                        continue
                else:
                    decision = self.consultation.consult(comment, plan, mapping,
                                                         proposal.simulation)
                    decisions.append(decision)
                    context.decisions.append(decision)
                    consulted.add(comment_id)
                    outcome, plan = apply_decision(decision, plan)
                    self.audit.write("consultation_agent", "decision_recorded",
                                     plan_id=plan.plan_id, result=outcome)
                    if outcome == "reject":
                        context.add_open_item(comment_id, self.m.t("r_rejected"),
                                              self.m.t("n_other_correction"))
                        continue
                    if outcome == "alternative":
                        index = ord(decision.user_choice.split(":")[1].strip().upper()) - ord("B")
                        if 0 <= index < len(proposal.alternative_plans):
                            plan = proposal.alternative_plans[index][0]
                            plan.plan_id = decision.resulting_plan_id or plan.plan_id
                            self._simulated.add(plan.plan_id)
                            context.plans.append(plan)
                    elif outcome in ("question", "modify"):
                        why = (self.m.t("r_modify", note=decision.user_note)
                               if outcome == "modify" else self.m.t("r_unanswered"))
                        context.add_open_item(comment_id, why, self.m.t("n_answer"))
                        plan.status = "awaiting_user"
                        continue

            result = executor.execute(plan)
            if not result.ok:
                plan.status = "failed"
                context.add_open_item(comment_id,
                                      self.m.t("r_execution_failed", error=result.error),
                                      self.m.t("n_investigate_api"))
                continue
            plan.status = "applied"
            for change in result.changes:
                change.comment_id = comment_id
                change.adapter = scope.adapter_name
            changes.extend(result.changes)
        return changes, decisions, consulted

    def _execution_order(self, proposals: dict[str, PlanProposal]) -> list[str]:
        """Order plans so a change never runs before one it depends on."""
        modified: dict[str, str] = {}
        for comment_id, proposal in proposals.items():
            if proposal.plan:
                for action in proposal.plan.plan:
                    modified.setdefault(action.element, comment_id)
        ordered = list(proposals)
        for comment_id, proposal in proposals.items():
            if not proposal.plan:
                continue
            for effect in proposal.plan.expected_effects:
                owner = modified.get(effect.element)
                if owner and owner != comment_id:
                    if ordered.index(owner) > ordered.index(comment_id):
                        ordered.remove(owner)
                        ordered.insert(ordered.index(comment_id), owner)
        return ordered

    def _needs_consultation(self, plan: CorrectionPlan) -> bool:
        if plan.deterministic and plan.confidence.value >= 0.95:
            return False
        return plan.requires_consultation or plan.confidence.value < self.threshold

    def _autonomous_block_reason(self, plan: CorrectionPlan) -> str:
        """SKILL.md 4.3: escalations autonomous mode never skips."""
        for effect in plan.expected_effects:
            constraint = self.ledger.get(effect.constraint_id)
            metric = constraint.test.metric if constraint and constraint.test else ""
            if metric in HARD_ESCALATION:
                return f"the change alters {metric}, which always needs human approval"
        hard_words = ("structural", "another consultant", "building footprint")
        for reason in plan.consultation_reasons:
            if any(word in reason for word in hard_words):
                return reason
        if plan.confidence.value < self.threshold:
            if plan.risk != "low" or any(v for v in plan.expected_effects if not v.still_compliant):
                return (f"confidence {plan.confidence.value:.2f} with {plan.risk} risk; "
                        "autonomous mode only applies minimal, reversible changes below the threshold")
        return ""

    # ------------------------------------------------------------------
    def _merge_validations(self, context: ProjectContext,
                          validations: list[tuple[OpenSource, ValidationResult]],
                          routings: dict[str, Routing]) -> ValidationResult:
        """One validation result for the whole run, from one per source.

        Each source validated only the comments routed to it, against its own
        driver - so a comment answered in a DWG is never marked unresolved
        because it could not be measured through Revit. Constraints and
        drawing checks are unioned across sources; a comment nobody could
        reach (no adapter available, or no source at all) still gets an
        honest entry instead of silently vanishing from the count.
        """
        merged = ValidationResult(version=validations[0][1].version if validations
                                  else self.versions.next_version())
        covered: set[str] = set()
        constraints_by_id: dict[str, object] = {}
        for scope, partial in validations:
            merged.comments.extend(partial.comments)
            covered.update(item.comment_id for item in partial.comments)
            for constraint in partial.constraints:
                existing = constraints_by_id.get(constraint.constraint_id)
                if existing is None or (existing.status == "not_evaluated"
                                        and constraint.status != "not_evaluated"):
                    constraints_by_id[constraint.constraint_id] = constraint
            prefix = f"{scope.adapter_name}: " if len(validations) > 1 else ""
            merged.drawing_checks.extend(
                {**check, "check": prefix + check["check"]} for check in partial.drawing_checks)
            merged.regressions.extend(partial.regressions)
        merged.constraints = list(constraints_by_id.values())
        for comment in context.municipal_comments:
            if comment.comment_id in covered:
                continue
            merged.comments.append(self._unroutable_comment_validation(
                comment, routings.get(comment.comment_id)))
        merged.result = ValidationAgent._verdict(merged)
        return merged

    def _unroutable_comment_validation(self, comment, routing: Routing | None) -> CommentValidation:
        """A comment no open, editable source could ever measure."""
        if comment.required_action == "none":
            return CommentValidation(comment.comment_id, CommentStatus.NOT_APPLICABLE,
                                     note=self.m.t("v_statement_only"))
        reason = (routing.reason if routing and routing.reason else self.m.t("r_no_model"))
        return CommentValidation(comment.comment_id, CommentStatus.REQUIRES_HUMAN_REVIEW,
                                 note=reason)

    # ------------------------------------------------------------------
    # versioning and artefacts
    # ------------------------------------------------------------------
    def _store_parent_version(self, context: ProjectContext) -> str:
        existing = self.versions.versions()
        if existing:
            return existing[-1]
        version = self.versions.next_version()
        manifest = VersionManifest(
            version=version, parent_version="original", run_id=self.run_id,
            operating_mode=self.mode.value,
            source_sha256=self._source_entry.sha256 if self._source_entry else "",
            validation_result="not_evaluated",
        )
        record = self.versions.create(self.driver, manifest)
        original = self.versions.root / "project_original.json"
        if not original.exists() and self._source_entry:
            shutil.copy2(self._source_entry.file, original)
        self.audit.write("orchestrator", "version_written", result=record.version)
        return version

    def _store_new_version(self, context: ProjectContext, result: RunResult, parent: str,
                           scopes: list[OpenSource] | None = None) -> str:
        version = self.versions.next_version()
        secondary_sources = []
        for scope in scopes or []:
            if scope.driver is self.driver:
                continue  # the primary is versioned authoritatively, below
            try:
                model = scope.driver.plan_model()
            except DrawingAPIError:
                continue
            secondary_sources.append(self.versions.snapshot_secondary(
                version, scope.adapter_name, model))
        manifest = VersionManifest(
            version=version,
            parent_version=parent,
            run_id=self.run_id,
            operating_mode=self.mode.value,
            validation_result=result.validation.result if result.validation else "not_evaluated",
            source_sha256=self._source_entry.sha256 if self._source_entry else "",
            comment_ids=[c.comment_id for c in context.municipal_comments],
            decisions=[d.decision_id for d in result.decisions],
            secondary_sources=secondary_sources,
        )
        record = self.versions.create(self.driver, manifest, result.changes)
        audit_copy = record.directory / "audit.jsonl"
        if self.audit.path and self.audit.path.exists():
            shutil.copy2(self.audit.path, audit_copy)
        self.audit.write("orchestrator", "version_written", result=version)
        return version

    def _write_artefacts(self, context: ProjectContext, result: RunResult, parent: str,
                         scopes: list[OpenSource] | None = None,
                         baseline: dict[str, str] | None = None) -> dict[str, str]:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        change_map = preview_module.build_change_map(result.changes, result.impact,
                                                     result.validation)
        before_model = json.loads(self.versions.model_path(parent).read_text(encoding="utf-8"))
        after_model = self.driver.plan_model()
        files = preview_module.write_previews(self.output_dir, before_model, after_model,
                                              change_map, result.version, self.m)
        touched_names = {scope.adapter_name for scope in (scopes or []) if scope.driver is not None}
        sources = [entry for entry in context.sources
                  if entry.get("adapter") in touched_names] or context.sources[:1]
        result.change_set = changeset.build(
            result.changes, before_model, after_model, result.version or "", parent,
            context.municipal_comments, result.validation, run_id=self.run_id,
            sources=sources, baseline=baseline, messages=self.m)
        files["change_set"] = str(changeset.write(self.output_dir, result.change_set))
        self._highlight(result.change_set["highlight_by_source"], scopes or [])
        context_path = self.output_dir / "project_context.json"
        context_path.write_text(context.to_json() + "\n", encoding="utf-8")
        files["project_context"] = str(context_path)
        validation_path = self.output_dir / "validation_report.json"
        validation_path.write_text(result.validation.to_json() + "\n", encoding="utf-8")
        files["validation_report"] = str(validation_path)
        graph_path = self.output_dir / "dependency_graph.json"
        graph_path.write_text(json.dumps(result.graph, indent=2) + "\n", encoding="utf-8")
        files["dependency_graph"] = str(graph_path)
        if self.consultation.transcript:
            transcript = self.output_dir / "consultation.md"
            transcript.write_text(
                "\n\n".join(f"{item['question']}\n\n**Answer:** {item['answer']}"
                            for item in self.consultation.transcript), encoding="utf-8")
            files["consultation"] = str(transcript)
        return files

    def _highlight(self, highlight_by_source: dict[str, list[str]],
                   scopes: list[OpenSource]) -> None:
        """Ask every live host that changed to select what changed in it.

        One call per tool, each with only the ids that are its own - a host
        must never be asked to select an id it did not report. A host that
        cannot do it says so and the run carries on: highlighting is a
        courtesy, and the change set is the artefact that matters.
        """
        for scope in scopes:
            element_ids = highlight_by_source.get(scope.adapter_name)
            if not element_ids or not hasattr(scope.driver, "highlight"):
                continue
            try:
                scope.driver.highlight(element_ids)
            except DrawingAPIError as error:
                self.audit.write("orchestrator", "highlight_skipped",
                                 params={"adapter": scope.adapter_name}, result=str(error))

    def _record_open_items(self, context: ProjectContext, result: RunResult) -> None:
        validation = result.validation
        if validation is None:
            return
        for item in validation.comments:
            if item.status in (CommentStatus.RESOLVED, CommentStatus.NOT_APPLICABLE):
                continue
            if any(existing["ref"] == item.comment_id for existing in context.open_items):
                continue
            context.add_open_item(item.comment_id,
                                  item.note or self.m.status(item.status),
                                  self.m.t("n_human_review"))
        for constraint in validation.constraints:
            if constraint.status == "not_evaluated":
                context.add_open_item(constraint.constraint_id,
                                      constraint.note or self.m.t("r_not_measured"),
                                      self.m.t("n_missing_reference"))
        for regression in validation.regressions:
            context.add_open_item(regression["constraint_id"],
                                  self.m.t("r_regression", rule=regression["rule"]),
                                  self.m.t("n_rollback"))

    # ------------------------------------------------------------------
    def _definition_of_done(self, context: ProjectContext, result: RunResult) -> list[tuple[str, bool]]:
        validation = result.validation
        comments = context.municipal_comments
        resolved_with_evidence = all(
            item.evidence for item in (validation.comments if validation else [])
            if item.status is CommentStatus.RESOLVED)
        traced = all(change.comment_id and change.plan_id for change in result.changes)
        simulated = all(plan.plan_id in self._simulated for plan in result.plans)
        original_intact = True
        if self._source_entry:
            original_intact = verify_original(Path(self._source_entry.file),
                                              self._source_entry.sha256)
        answered = all(
            decision.user_choice not in ("question", "") or
            any(item["ref"] for item in context.open_items)
            for decision in result.decisions)
        return [
            (self.m.t("dod_manifest"), bool(context.input_manifest)),
            (self.m.t("dod_comments"),
             bool(comments) and validation is not None
             and len(validation.comments) == len(comments)),
            (self.m.t("dod_evidence"), resolved_with_evidence),
            (self.m.t("dod_traceability"), traced),
            (self.m.t("dod_simulated"), simulated),
            (self.m.t("dod_ledger"), validation is not None and validation.result != "failed"),
            (self.m.t("dod_questions"), answered),
            (self.m.t("dod_original"), original_intact),
            (self.m.t("dod_version"), bool(result.version)),
            (self.m.t("dod_previews"),
             "comparison" in result.files and "change_map" in result.files),
            (self.m.t("dod_change_set"),
             "change_set" in result.files and all(
                 change["comment_id"] and change["plan_id"]
                 for element in result.change_set.get("elements", [])
                 for change in element["properties"])),
            (self.m.t("dod_routing"), all(
                routing["routed"] or (routing["reason"] and routing["needed"])
                for routing in context.routing)),
            (self.m.t("dod_open_items"),
             all(item["needed"] for item in context.open_items)),
        ]

    # ------------------------------------------------------------------
    def _finish_markup_only(self, result: RunResult) -> RunResult:
        """SKILL.md 3.3 - no editable model: produce instructions, edit nothing."""
        context = result.context
        self._analyze_comments(context)
        constraints_from_comments(context.municipal_comments, self.ledger)
        context.planning_constraints = self.ledger.all
        validation = ValidationResult(version="markup")
        for comment in context.municipal_comments:
            status = (CommentStatus.NOT_APPLICABLE if comment.required_action == "none"
                      else CommentStatus.REQUIRES_HUMAN_REVIEW)
            validation.comments.append(CommentValidation(
                comment.comment_id, status,
                note="markup-only run: no editable model, nothing was measured or changed"))
            context.add_open_item(
                comment.comment_id, self.m.t("r_markup_only"),
                comment.summary or comment.normalized_requirement or self.m.t("n_drafter"))
        validation.result = "passed_with_open_items"
        result.validation = validation
        result.definition_of_done = self._definition_of_done(context, result)
        result.language = self.m.code
        result.llm = self._llm_summary()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        result.report = build_report(context, validation, [], [], [], "markup", "original",
                                     {}, result.definition_of_done, set(), self.m)
        report_path = self.output_dir / "correction_report.md"
        report_path.write_text(result.report, encoding="utf-8")
        result.files["correction_report"] = str(report_path)
        self.audit.write("orchestrator", "run_complete", result="markup_only")
        return result
