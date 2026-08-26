"""Step 2 - Municipal comment analysis (SKILL.md 5.2).

A deterministic parser turns comment text into testable requirements.  It is
intentionally conservative: a sentence it cannot parse becomes a comment with
low interpretation confidence that is routed to human review (SKILL.md 21),
never a guessed requirement.

An LLM can be plugged in through the ``llm`` hook to handle free prose that the
patterns miss; its output is validated into the same :class:`Requirement`
schema and is marked as inferred.
"""

from __future__ import annotations

import re
from typing import Callable

from .models import Confidence, MunicipalComment, Requirement

DEPARTMENTS = [
    "Planning", "Architecture", "Licensing", "Traffic", "Parking", "Accessibility",
    "Fire Safety", "Sanitation", "Water", "Drainage", "Landscaping", "Environment",
    "Infrastructure", "Engineering",
]

_DEPARTMENT_LOOKUP = {d.casefold(): d for d in DEPARTMENTS}
_DEPARTMENT_LOOKUP.update({"fire": "Fire Safety", "transportation": "Traffic", "roads": "Traffic"})

NUMBER = r"(?P<value>\d+(?:[.,]\d+)?)"
UNIT = r"\s*(?P<unit>m²|m2|sqm|m\b|meters?\b|metres?\b|cm\b|mm\b)?"

DIRECTIONS = ("north", "south", "east", "west", "northern", "southern", "eastern", "western")
DIRECTION_CANON = {
    "north": "north", "northern": "north", "south": "south", "southern": "south",
    "east": "east", "eastern": "east", "west": "west", "western": "west",
}

METRIC_WORDS = {
    "width": "width",
    "clear width": "clear_width",
    "length": "length",
    "depth": "length",
    "height": "height",
    "area": "area",
    "floor area": "floor_area",
    "setback": "setback",
    "distance": "clear_distance",
    "clearance": "clear_distance",
}

ELEMENT_WORDS = {
    "parking space": "parking",
    "parking bay": "parking",
    "parking": "parking",
    "driveway": "driveway",
    "drive aisle": "driveway",
    "aisle": "driveway",
    "building": "building",
    "balcony": "balcony",
    "room": "room",
    "corridor": "corridor",
    "ramp": "ramp",
    "window": "window",
    "wall": "wall",
    "road": "road",
    "sidewalk": "sidewalk",
}

ANNOTATION_ACTIONS = {
    "label": "update_text",
    "title": "update_text",
    "text": "update_text",
    "note": "update_text",
    "dimension": "update_dimension",
    "schedule": "update_schedule",
    "table": "update_schedule",
}

AT_LEAST = r"(?:at least|no less than|not less than|minimum(?: of)?|min\.?|>=)"
AT_MOST = r"(?:at most|no more than|not exceed|not more than|maximum(?: of)?|max\.?|<=)"

_COMMENT_ID = re.compile(r"^\s*(?:(?P<full>[A-Z]{1,3}-\d{1,4})|(?P<num>\d{1,3}))\s*[.):\-]\s*(?P<body>.+)$")
_DEPARTMENT_LINE = re.compile(r"^\s*(?:department|discipline|section)\s*[:\-]\s*(?P<name>.+?)\s*$", re.I)
_LABEL = re.compile(r"\b(?P<label>[A-Z]{1,3}[-_ ]?\d{1,3})\b")


def _num(text: str) -> float:
    return float(text.replace(",", "."))


def _unit(raw: str | None) -> str:
    if not raw:
        return "m"
    raw = raw.strip().casefold()
    if raw in ("m²", "m2", "sqm"):
        return "m2"
    if raw.startswith("cm"):
        return "cm"
    if raw.startswith("mm"):
        return "mm"
    return "m"


class CommentAnalyzer:
    """Turns municipal comment text into structured comment objects."""

    def __init__(self, llm: Callable[[str], dict] | None = None):
        self.llm = llm

    # ------------------------------------------------------------------
    def analyze_document(self, text: str, source_ref: str = "", default_department: str = "Planning",
                         start_index: int = 1) -> list[MunicipalComment]:
        comments: list[MunicipalComment] = []
        department = default_department
        index = start_index
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            header = _DEPARTMENT_LINE.match(line)
            if header:
                department = self.normalise_department(header.group("name"))
                continue
            bare = self.normalise_department(line, strict=True)
            if bare and len(line) < 40:
                department = bare
                continue
            match = _COMMENT_ID.match(line)
            if match:
                comment_id = match.group("full") or f"C-{int(match.group('num')):03d}"
                body = match.group("body").strip()
            elif line.startswith(("-", "*", "•")):
                comment_id = f"C-{index:03d}"
                body = line.lstrip("-*• ").strip()
            else:
                continue
            comments.append(self.analyze_comment(comment_id, body, department, source_ref))
            index += 1
        return comments

    @staticmethod
    def normalise_department(name: str, strict: bool = False) -> str | None:
        key = name.strip().strip(":").casefold()
        if key in _DEPARTMENT_LOOKUP:
            return _DEPARTMENT_LOOKUP[key]
        if strict:
            return None
        for word, canonical in _DEPARTMENT_LOOKUP.items():
            if word in key:
                return canonical
        return name.strip().title()

    # ------------------------------------------------------------------
    def analyze_comment(self, comment_id: str, text: str, department: str = "Planning",
                        source_ref: str = "") -> MunicipalComment:
        comment = MunicipalComment(
            comment_id=comment_id,
            department=department,
            original_text=text,
            source_ref=source_ref,
            language=_detect_language(text),
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
            comment.normalized_requirement = f"{action}: {text.strip()}"
        else:
            comment.required_action = "none" if _is_statement(text) else "unparsed"
            comment.normalized_requirement = ""
        if comment.required_action == "none":
            interpretation = max(interpretation, 0.9)
        comment.confidence = comment.confidence.with_(interpretation=interpretation)
        comment.affected_discipline = _discipline_for(department)
        return comment

    # ------------------------------------------------------------------
    def parse(self, text: str) -> tuple[Requirement | None, str, list[str], float]:
        """Return ``(requirement, action, notes, interpretation_confidence)``."""
        cleaned = " ".join(text.split())
        lowered = cleaned.casefold()
        for parser in (
            self._parse_setback,
            self._parse_dimension_to,
            self._parse_area_bound,
            self._parse_dimension_bound,
            self._parse_count,
        ):
            result = parser(cleaned, lowered)
            if result:
                requirement, confidence, notes = result
                return requirement, "modify_geometry", notes, confidence
        annotation = self._parse_annotation(lowered)
        if annotation:
            return None, annotation, ["annotation-only correction"], 0.9
        if self.llm is not None:
            inferred = self._parse_with_llm(cleaned)
            if inferred:
                return inferred, "modify_geometry", ["requirement inferred by language model"], 0.7
        return None, "", ["no testable requirement could be extracted"], 0.35

    # ------------------------------------------------------------------
    def _parse_setback(self, text: str, lowered: str):
        pattern = re.compile(
            rf"(?P<dir>{'|'.join(DIRECTIONS)})\s+(?:side\s+)?setback[^0-9]*?"
            rf"(?:{AT_LEAST}|to|of)?\s*{NUMBER}{UNIT}", re.I)
        match = pattern.search(text)
        if not match:
            pattern = re.compile(
                rf"setback\s+(?:from|to)\s+the\s+(?P<dir>{'|'.join(DIRECTIONS)})[^0-9]*?{NUMBER}{UNIT}", re.I)
            match = pattern.search(text)
        if not match:
            return None
        direction = DIRECTION_CANON[match.group("dir").casefold()]
        op = "<=" if re.search(AT_MOST, lowered) else ">="
        subject = {"element_id": _subject_id(lowered) or "building", "edge": direction,
                   "label": _label_of(text) or "building"}
        requirement = Requirement(subject=subject, metric="setback", op=op,
                                  value=_num(match.group("value")), unit=_unit(match.group("unit")),
                                  basis="to plot line")
        return requirement, 0.92, []

    def _parse_dimension_to(self, text: str, lowered: str):
        metric_alt = "|".join(sorted(METRIC_WORDS, key=len, reverse=True))
        pattern = re.compile(
            rf"(?P<verb>increase|widen|enlarge|extend|reduce|narrow|decrease|change|adjust|set)\b"
            rf"(?P<middle>.{{0,80}}?)\b(?P<metric>{metric_alt})\b"
            rf"(?:[^0-9]{{0,20}}?)(?:to|=)\s*{NUMBER}{UNIT}", re.I)
        match = pattern.search(text)
        if not match:
            pattern = re.compile(
                rf"(?P<metric>{metric_alt})\s+of\s+(?P<middle>.{{0,40}}?)\s*(?:to|=)\s*{NUMBER}{UNIT}", re.I)
            match = pattern.search(text)
            if not match:
                return None
        verb = (match.groupdict().get("verb") or "").casefold()
        metric = METRIC_WORDS[match.group("metric").casefold()]
        op = "<=" if verb in ("reduce", "narrow", "decrease") else ">="
        if verb in ("change", "adjust", "set"):
            op = "=="
        context = f"{match.group('middle') or ''} {text}"
        requirement = Requirement(
            subject=_subject_from(context, metric), metric=metric, op=op,
            value=_num(match.group("value")), unit=_unit(match.group("unit")),
        )
        confidence = 0.93 if _label_of(context) else 0.8
        notes = [] if _label_of(context) else ["no element label in the comment; matched by type"]
        return requirement, confidence, notes

    def _parse_dimension_bound(self, text: str, lowered: str):
        metric_alt = "|".join(sorted(METRIC_WORDS, key=len, reverse=True))
        pattern = re.compile(
            rf"(?P<metric>{metric_alt})\b(?P<middle>.{{0,40}}?)\b(?:must|shall|should|has to|to)?\s*"
            rf"(?:be\s*)?(?P<bound>{AT_LEAST}|{AT_MOST})\s*{NUMBER}{UNIT}", re.I)
        match = pattern.search(text)
        if not match:
            return None
        metric = METRIC_WORDS[match.group("metric").casefold()]
        op = "<=" if re.fullmatch(AT_MOST, match.group("bound").strip(), re.I) else ">="
        context = f"{match.group('middle') or ''} {text}"
        requirement = Requirement(
            subject=_subject_from(context, metric), metric=metric, op=op,
            value=_num(match.group("value")), unit=_unit(match.group("unit")),
        )
        return requirement, 0.9 if _label_of(context) else 0.78, []

    def _parse_count(self, text: str, lowered: str):
        pattern = re.compile(
            rf"(?:provide|supply|add|show|include)?\s*(?:{AT_LEAST}\s*)?{NUMBER}\s*"
            r"(?P<what>parking spaces?|parking bays?|accessible parking spaces?|bicycle spaces?)", re.I)
        match = pattern.search(text)
        if not match:
            return None
        selector = {"type": "parking"}
        if "accessible" in match.group("what").casefold():
            selector["category"] = "accessible"
        elif "bicycle" in match.group("what").casefold():
            selector = {"type": "bicycle_parking"}
        op = "<=" if re.search(AT_MOST, lowered) else ">="
        requirement = Requirement(subject={"selector": selector}, metric="count", op=op,
                                  value=_num(match.group("value")), unit="count")
        return requirement, 0.88, []

    def _parse_area_bound(self, text: str, lowered: str):
        pattern = re.compile(
            rf"(?:total\s+)?(?P<metric>floor area|built area|area)\b.{{0,30}}?"
            rf"(?P<bound>{AT_LEAST}|{AT_MOST})\s*{NUMBER}\s*(?P<unit>m²|m2|sqm)", re.I)
        match = pattern.search(text)
        if not match:
            return None
        op = "<=" if re.fullmatch(AT_MOST, match.group("bound").strip(), re.I) else ">="
        requirement = Requirement(subject={"selector": {"counts_as_floor_area": True}},
                                  metric="floor_area", op=op, value=_num(match.group("value")),
                                  unit="m2")
        return requirement, 0.85, []

    def _parse_annotation(self, lowered: str) -> str:
        for word, action in ANNOTATION_ACTIONS.items():
            if re.search(rf"\b(add|update|correct|revise|fix|amend|complete)\b.{{0,30}}\b{word}s?\b", lowered):
                return action
        return ""

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


def _subject_from(context: str, metric: str) -> dict:
    label = _label_of(context)
    element_type = _type_of(context)
    subject: dict = {}
    if label:
        subject["selector"] = {"label": label}
        subject["label"] = label
    elif element_type:
        subject["selector"] = {"type": element_type}
        subject["label"] = element_type
    else:
        subject["selector"] = {}
    if element_type and "selector" in subject and "type" not in subject["selector"]:
        subject["selector"]["type"] = element_type
    if metric == "setback":
        subject.setdefault("edge", "north")
    return subject


def _subject_id(lowered: str) -> str | None:
    return "building" if "building" in lowered else None


def _label_of(text: str) -> str | None:
    for match in _LABEL.finditer(text):
        label = match.group("label").replace(" ", "").replace("_", "-")
        if label.casefold() in ("a-101", "a-001"):
            continue
        if re.fullmatch(r"[A-Z]{1,3}-?\d{1,3}", label):
            return label.replace("-", "") if len(label) <= 5 and "-" in label else label
    return None


def _type_of(text: str) -> str | None:
    lowered = text.casefold()
    for word in sorted(ELEMENT_WORDS, key=len, reverse=True):
        if word in lowered:
            return ELEMENT_WORDS[word]
    return None


def _is_statement(text: str) -> bool:
    lowered = text.casefold().strip()
    return any(lowered.startswith(word) for word in ("noted", "no comment", "for information", "acknowledged"))


def _detect_language(text: str) -> str:
    if any("֐" <= ch <= "׿" for ch in text):
        return "he"
    if any("؀" <= ch <= "ۿ" for ch in text):
        return "ar"
    return "en"


def _discipline_for(department: str) -> str:
    return {
        "Traffic": "traffic", "Parking": "traffic", "Fire Safety": "fire",
        "Accessibility": "accessibility", "Landscaping": "landscape",
        "Drainage": "civil", "Water": "civil", "Infrastructure": "civil",
        "Engineering": "structure",
    }.get(department, "architecture")
