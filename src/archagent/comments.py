"""Step 2 - Municipal comment analysis (SKILL.md 5.2).

A deterministic, lexicon-driven parser turns comment text into testable
requirements.  The language is decided by the text itself, so a Hebrew comment
set with Latin element marks ("מקום חניה P12") needs no configuration.

The parser is intentionally conservative: a sentence it cannot parse becomes a
comment with low interpretation confidence that is routed to human review
(SKILL.md 21), never a guessed requirement.  An LLM can be plugged in through
the ``llm`` hook to handle free prose the patterns miss; its output is
validated into the same :class:`Requirement` schema and marked as inferred.
"""

from __future__ import annotations

import re
from typing import Callable

from . import lang
from .lang import Lexicon, clean, parse_number
from .llm.client import LLMClient, LLMError
from .llm.interpret import (
    Interpretation,
    LLMCommentInterpreter,
    describe_disagreement,
    requirements_agree,
)
from .models import Confidence, MunicipalComment, Requirement

DEPARTMENTS = [
    "Planning", "Architecture", "Licensing", "Traffic", "Parking", "Accessibility",
    "Fire Safety", "Sanitation", "Water", "Drainage", "Landscaping", "Environment",
    "Infrastructure", "Engineering",
]

#: Metrics whose subject is the project as a whole, not one element.
PROJECT_METRICS = {"floor_area"}

_QUOTED = re.compile(r"[\"'](?P<text>[^\"']{2,120})[\"']")
_BULLET = ("-", "*", "•", "–", "‣", "·")


class CommentAnalyzer:
    """Turns municipal comment text into structured comment objects."""

    def __init__(self, llm: Callable[[str], dict] | None = None,
                 lexicon: Lexicon | None = None,
                 client: LLMClient | None = None,
                 interpreter: LLMCommentInterpreter | None = None,
                 inventory: list[dict] | None = None):
        #: Legacy hook: a plain callable consulted only when the rules miss.
        self.llm = llm
        #: When set, forces one language; otherwise it is detected per comment.
        self.lexicon = lexicon
        #: When set, Claude is the primary reader and the rules cross-check it.
        self.interpreter = interpreter or (
            LLMCommentInterpreter(client, inventory=inventory) if client else None)
        self.failures: list[str] = []

    def lexicon_for(self, text: str) -> Lexicon:
        return self.lexicon or lang.for_text(text)

    # ------------------------------------------------------------------
    # documents
    # ------------------------------------------------------------------
    def analyze_document(self, text: str, source_ref: str = "",
                         default_department: str = "Planning",
                         start_index: int = 1) -> list[MunicipalComment]:
        comments: list[MunicipalComment] = []
        department = default_department
        index = start_index
        document_lexicon = self.lexicon or lang.for_text(text)
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            lexicon = self.lexicon or lang.for_text(line) or document_lexicon
            if lexicon.code == "en" and document_lexicon.code != "en":
                # A short line of Latin text inside a Hebrew document (a mark,
                # a sheet number) belongs to the document's language.
                lexicon = document_lexicon

            header = lexicon.compile(lexicon.department_line).match(line)
            if header:
                department = lexicon.department_of(header.group("name")) or department
                continue
            bare = lexicon.department_of(line, strict=True)
            if bare and len(line) < 40:
                department = bare
                continue

            comment_id, body = self._split_id(lexicon, line, index)
            if comment_id is None:
                continue
            comments.append(self.analyze_comment(comment_id, body, department, source_ref))
            index += 1
        return comments

    @staticmethod
    def _split_id(lexicon: Lexicon, line: str, index: int) -> tuple[str | None, str]:
        for pattern in lexicon.comment_id_patterns:
            match = lexicon.compile(pattern).match(line)
            if not match:
                continue
            groups = match.groupdict()
            comment_id = groups.get("full") or f"C-{int(groups['num']):03d}"
            return comment_id, match.group("body").strip()
        if line.startswith(_BULLET):
            return f"C-{index:03d}", line.lstrip("".join(_BULLET) + " ").strip()
        return None, ""

    @staticmethod
    def normalise_department(name: str, strict: bool = False) -> str | None:
        for lexicon in lang.LEXICONS.values():
            found = lexicon.department_of(name, strict=True)
            if found:
                return found
        if strict:
            return None
        for lexicon in lang.LEXICONS.values():
            found = lexicon.department_of(name)
            if found:
                return found
        return name.strip().title()

    # ------------------------------------------------------------------
    # a single comment
    # ------------------------------------------------------------------
    def analyze_comment(self, comment_id: str, text: str, department: str = "Planning",
                        source_ref: str = "") -> MunicipalComment:
        if self.interpreter is not None:
            return self._analyze_with_model(comment_id, text, department, source_ref)
        return self._analyze_with_rules(comment_id, text, department, source_ref)

    # ------------------------------------------------------------------
    def _analyze_with_model(self, comment_id: str, text: str, department: str,
                            source_ref: str) -> MunicipalComment:
        """Claude reads the comment; the rule parser checks the reading.

        Agreement raises confidence, disagreement lowers it and records both
        readings - so a divergence becomes a consultation, never a silent pick.
        """
        try:
            reading = self.interpreter.interpret(comment_id, text, department, source_ref)
        except LLMError as error:
            self.failures.append(f"{comment_id}: {error}")
            comment = self._analyze_with_rules(comment_id, text, department, source_ref)
            comment.parse_notes.append(f"the model could not be reached ({error}); "
                                       "the rule parser was used instead")
            comment.confidence = comment.confidence.with_(
                interpretation=min(comment.confidence.interpretation, 0.75))
            return comment

        lexicon = self.lexicon_for(text)
        rule_requirement, rule_action, rule_notes, rule_confidence = self.parse(text)
        comment = MunicipalComment(
            comment_id=comment_id,
            department=self._department(reading, department),
            original_text=text,          # verbatim, in its own language
            source_ref=source_ref,
            language=reading.language or lexicon.code,
            summary=reading.summary,
            interpretation_source="llm",
        )
        comment.affected_discipline = _discipline_for(comment.department)
        comment.parse_notes.extend(reading.ambiguities)
        comment.parse_notes.extend(f"rejected by validation: {item}"
                                   for item in reading.rejected)
        interpretation = reading.interpretation

        if reading.kind == "measurable" and reading.requirement is not None:
            comment.requirement = reading.requirement
            comment.normalized_requirement = reading.requirement.describe()
            comment.required_action = "modify_geometry"
            if rule_requirement is not None:
                if requirements_agree(reading.requirement, rule_requirement):
                    comment.interpretation_source = "llm+rules"
                    interpretation = max(interpretation, rule_confidence)
                    comment.parse_notes.append("confirmed by the deterministic parser")
                else:
                    comment.interpretation_source = "llm+rules"
                    interpretation = min(interpretation, 0.55)
                    comment.parse_notes.append(
                        "the two readings disagree: "
                        + describe_disagreement(reading.requirement, rule_requirement))
            else:
                comment.parse_notes.append(
                    "the deterministic parser found no testable requirement here")
        elif reading.kind == "annotation" and reading.annotation_action:
            comment.required_action = reading.annotation_action
            comment.normalized_requirement = (
                f"{reading.annotation_action}: {reading.summary or clean(text)}")
        elif reading.kind == "statement":
            comment.required_action = "none"
            interpretation = max(interpretation, 0.9)
        else:
            # The model could not interpret it. If the rules found something
            # testable, use that rather than throwing the comment away.
            if rule_requirement is not None:
                comment.requirement = rule_requirement
                comment.normalized_requirement = rule_requirement.describe()
                comment.required_action = "modify_geometry"
                comment.interpretation_source = "rules"
                comment.parse_notes.extend(rule_notes)
                comment.parse_notes.append(
                    "the model could not interpret the comment; the deterministic "
                    "parser was used")
                interpretation = min(rule_confidence, 0.7)
            elif rule_action:
                comment.required_action = rule_action
                comment.interpretation_source = "rules"
                interpretation = min(rule_confidence, 0.7)
            else:
                comment.required_action = "unparsed"
                interpretation = min(interpretation, 0.4)
        comment.confidence = Confidence(
            extraction=reading.extraction,
            interpretation=interpretation,
        )
        return comment

    @staticmethod
    def _department(reading: Interpretation, hint: str) -> str:
        if reading.department and reading.department != "Unknown":
            return reading.department
        return hint or "Planning"

    # ------------------------------------------------------------------
    def _analyze_with_rules(self, comment_id: str, text: str, department: str,
                            source_ref: str) -> MunicipalComment:
        lexicon = self.lexicon_for(text)
        comment = MunicipalComment(
            comment_id=comment_id,
            department=department,
            original_text=text,          # verbatim, in its own language
            source_ref=source_ref,
            language=lexicon.code,
            interpretation_source="rules",
        )
        comment.confidence = Confidence(extraction=1.0 if text.strip() else 0.2)
        requirement, action, notes, interpretation = self.parse(text)
        comment.parse_notes.extend(notes)
        if requirement is not None:
            comment.requirement = requirement
            comment.normalized_requirement = requirement.describe()
            comment.required_action = action
        elif action:
            comment.required_action = action
            comment.normalized_requirement = f"{action}: {clean(text)}"
        else:
            comment.required_action = "none" if lexicon.is_statement(text) else "unparsed"
            comment.normalized_requirement = ""
        if comment.required_action == "none":
            interpretation = max(interpretation, 0.9)
        comment.confidence = comment.confidence.with_(interpretation=interpretation)
        comment.affected_discipline = _discipline_for(department)
        return comment

    # ------------------------------------------------------------------
    def parse(self, text: str) -> tuple[Requirement | None, str, list[str], float]:
        """Return ``(requirement, action, notes, interpretation_confidence)``."""
        lexicon = self.lexicon_for(text)
        cleaned = clean(text)
        for parser in (self._parse_setback, self._parse_dimension_to,
                       self._parse_bound, self._parse_implied_dimension,
                       self._parse_count):
            result = parser(lexicon, cleaned)
            if result:
                requirement, confidence, notes = result
                return requirement, "modify_geometry", notes, confidence
        annotation = self._parse_annotation(lexicon, cleaned)
        if annotation:
            return None, annotation, ["annotation-only correction"], 0.9
        if self.llm is not None:
            inferred = self._parse_with_llm(cleaned)
            if inferred:
                return inferred, "modify_geometry", ["requirement inferred by language model"], 0.7
        return None, "", ["no testable requirement could be extracted"], 0.35

    # ------------------------------------------------------------------
    # parsers
    # ------------------------------------------------------------------
    def _parse_setback(self, lexicon: Lexicon, text: str):
        setbacks = {surface: metric for surface, metric in lexicon.metrics.items()
                    if metric == "setback"}
        if not setbacks:
            return None
        setback_alt = "|".join(f"(?:{lexicon.prefix}{surface})" for surface in
                               sorted(setbacks, key=len, reverse=True))
        directions = lexicon.direction_alternation()
        number, unit = lexicon.number_pattern, lexicon.unit_pattern
        bounds = f"(?:{lexicon.at_least}|{lexicon.at_most}|{lexicon.to_marker})?"
        orders = []
        if lexicon.setback_order in ("direction_first", "both"):
            orders.append(rf"(?P<dir>{directions})\s*(?:side\s+)?(?P<metric>{setback_alt})"
                          rf"[^0-9]{{0,40}}?{bounds}\s*{number}{unit}")
        if lexicon.setback_order in ("metric_first", "both"):
            orders.append(rf"(?P<metric>{setback_alt})\s*(?P<dir>{directions})"
                          rf"[^0-9]{{0,40}}?{bounds}\s*{number}{unit}")
        orders.append(rf"(?P<metric>{setback_alt})[^0-9]{{0,30}}?(?P<dir>{directions})"
                      rf"[^0-9]{{0,30}}?{bounds}\s*{number}{unit}")
        match = None
        for pattern in orders:
            match = lexicon.compile(pattern).search(text)
            if match:
                break
        if not match:
            return None
        direction = lexicon.direction_of(match.group("dir"))
        if direction is None:
            return None
        subject = self._setback_subject(lexicon, text, direction)
        requirement = Requirement(
            subject=subject, metric="setback", op=self._op_from(lexicon, text),
            value=parse_number(match.group("value")), unit=lexicon.unit_of(match.group("unit")),
            basis="to plot line")
        return requirement, 0.92, []

    def _parse_dimension_to(self, lexicon: Lexicon, text: str):
        metrics = lexicon.metric_alternation()
        number, unit = lexicon.number_pattern, lexicon.unit_pattern
        verbs = (rf"(?P<verb>{lexicon.increase_verbs}|{lexicon.decrease_verbs}"
                 rf"|{lexicon.set_verbs})")
        patterns = (
            rf"{verbs}(?P<middle>.{{0,80}}?)(?P<metric>{metrics})"
            rf"(?P<tail>.{{0,40}}?)(?:{lexicon.to_marker})\s*{number}{unit}",
            rf"(?P<metric>{metrics})(?P<middle>.{{0,40}}?){verbs}?"
            rf"(?P<tail>.{{0,20}}?)(?:{lexicon.to_marker})\s*{number}{unit}",
        )
        for pattern in patterns:
            match = lexicon.compile(pattern).search(text)
            if not match:
                continue
            metric = lexicon.metric_of(match.group("metric"))
            if metric is None:
                continue
            verb = (match.groupdict().get("verb") or "")
            op = ">="
            if verb and lexicon.compile(lexicon.decrease_verbs).fullmatch(verb):
                op = "<="
            elif verb and lexicon.compile(lexicon.set_verbs).fullmatch(verb):
                op = "=="
            elif not verb:
                op = self._op_from(lexicon, text)
            context = f"{match.groupdict().get('middle') or ''} {match.groupdict().get('tail') or ''} {text}"
            subject = self._subject_from(lexicon, context, metric)
            requirement = Requirement(subject=subject, metric=metric, op=op,
                                      value=parse_number(match.group("value")),
                                      unit=lexicon.unit_of(match.group("unit")))
            has_label = lexicon.find_label(context) is not None
            notes = [] if has_label else ["no element label in the comment; matched by type"]
            return requirement, 0.93 if has_label else 0.8, notes
        return None

    def _parse_bound(self, lexicon: Lexicon, text: str):
        metrics = lexicon.metric_alternation()
        number, unit = lexicon.number_pattern, lexicon.unit_pattern
        pattern = (rf"(?P<metric>{metrics})(?P<middle>.{{0,40}}?)"
                   rf"(?:must|shall|should|has to)?\s*(?:be\s*)?"
                   rf"(?P<bound>{lexicon.at_least}|{lexicon.at_most})\s*{number}{unit}")
        match = lexicon.compile(pattern).search(text)
        if not match:
            return None
        metric = lexicon.metric_of(match.group("metric"))
        if metric is None:
            return None
        op = "<=" if lexicon.compile(lexicon.at_most).fullmatch(match.group("bound").strip()) else ">="
        context = f"{match.group('middle') or ''} {text}"
        subject = self._subject_from(lexicon, context, metric)
        requirement = Requirement(subject=subject, metric=metric, op=op,
                                  value=parse_number(match.group("value")),
                                  unit=lexicon.unit_of(match.group("unit")))
        if metric in PROJECT_METRICS:
            return requirement, 0.85, []
        has_label = lexicon.find_label(context) is not None
        return requirement, 0.9 if has_label else 0.78, []

    def _parse_implied_dimension(self, lexicon: Lexicon, text: str):
        """"Widen the driveway to 3.00 m" - the verb names the metric."""
        number, unit = lexicon.number_pattern, lexicon.unit_pattern
        for verbs, metric, op in lexicon.implied_metrics:
            pattern = (rf"(?P<verb>{lexicon.prefix}(?:{verbs}))(?P<middle>.{{0,60}}?)"
                       rf"(?:{lexicon.to_marker}|{lexicon.at_least}|{lexicon.at_most})"
                       rf"\s*{number}{unit}")
            match = lexicon.compile(pattern).search(text)
            if not match:
                continue
            if lexicon.compile(lexicon.at_most).search(text):
                op = "<="
            context = f"{match.group('middle') or ''} {text}"
            subject = self._subject_from(lexicon, context, metric)
            requirement = Requirement(subject=subject, metric=metric, op=op,
                                      value=parse_number(match.group("value")),
                                      unit=lexicon.unit_of(match.group("unit")))
            has_label = lexicon.find_label(context) is not None
            notes = [f"metric inferred from the verb {clean(match.group('verb'))!r}"]
            if not has_label:
                notes.append("no element label in the comment; matched by type")
            return requirement, 0.85 if has_label else 0.75, notes
        return None

    def _parse_count(self, lexicon: Lexicon, text: str):
        nouns = "|".join(f"(?:{surface})" for surface, _selector in lexicon.count_nouns)
        pattern = (rf"(?:{lexicon.at_least}|{lexicon.at_most})?\s*{lexicon.number_pattern}"
                   rf"\s*(?P<what>{nouns})")
        match = lexicon.compile(pattern).search(text)
        if not match:
            return None
        what = clean(match.group("what")).casefold()
        selector = {"type": "parking"}
        for surface, candidate in lexicon.count_nouns:
            if re.fullmatch(surface, what, re.I) or re.match(surface, what, re.I):
                selector = dict(candidate)
                break
        requirement = Requirement(subject={"selector": selector}, metric="count",
                                  op=self._op_from(lexicon, text),
                                  value=parse_number(match.group("value")), unit="count")
        return requirement, 0.88, []

    def _parse_annotation(self, lexicon: Lexicon, text: str) -> str:
        pattern = (rf"{lexicon.annotation_verbs}.{{0,30}}?"
                   rf"(?P<what>{lexicon.annotation_alternation()})")
        match = lexicon.compile(pattern).search(text)
        if not match:
            return ""
        return lexicon.annotation_of(match.group("what")) or ""

    def _parse_with_llm(self, text: str) -> Requirement | None:
        try:
            data = self.llm(text) or {}
        except Exception:
            return None
        try:
            return Requirement(
                subject=data["subject"], metric=data["metric"], op=data["op"],
                value=float(data["value"]), unit=data.get("unit", "m"),
                basis=data.get("basis", "clear"),
            )
        except (KeyError, TypeError, ValueError):
            return None

    # ------------------------------------------------------------------
    # subjects
    # ------------------------------------------------------------------
    @staticmethod
    def _op_from(lexicon: Lexicon, text: str) -> str:
        if lexicon.compile(lexicon.at_most).search(text):
            return "<="
        return ">="

    @staticmethod
    def _subject_from(lexicon: Lexicon, context: str, metric: str) -> dict:
        if metric in PROJECT_METRICS:
            return {"selector": {"counts_as_floor_area": True}, "label": "floor area"}
        label = lexicon.find_label(context)
        element_type = lexicon.element_of(context)
        subject: dict = {}
        if label:
            subject = {"selector": {"label": label}, "label": label}
            if element_type:
                subject["selector"]["type"] = element_type
        elif element_type:
            subject = {"selector": {"type": element_type}, "label": element_type}
        else:
            subject = {"selector": {}}
        return subject

    @staticmethod
    def _setback_subject(lexicon: Lexicon, text: str, direction: str) -> dict:
        label = lexicon.find_label(text)
        element_type = lexicon.element_of(text)
        if label:
            return {"selector": {"label": label}, "label": label, "edge": direction}
        if element_type and element_type != "building":
            return {"selector": {"type": element_type}, "label": element_type,
                    "edge": direction}
        return {"element_id": "building", "label": "building", "edge": direction}


def _discipline_for(department: str) -> str:
    return {
        "Traffic": "traffic", "Parking": "traffic", "Fire Safety": "fire",
        "Accessibility": "accessibility", "Landscaping": "landscape",
        "Drainage": "civil", "Water": "civil", "Infrastructure": "civil",
        "Engineering": "structure",
    }.get(department, "architecture")
