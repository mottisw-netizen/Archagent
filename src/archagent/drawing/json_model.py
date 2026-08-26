"""Reference drawing driver backed by a plain JSON model.

This is a real, fully working implementation of :class:`DrawingDriver` for a
simplified plan model: axis-aligned elements on a plot, sheets, and schedules
derived from elements.  It exists so the whole pipeline - mapping, planning,
simulation, execution, validation, previews - can run and be tested end to end
without a CAD seat.

A DWG/RVT/IFC adapter replaces this module and nothing else.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from ..models import ChangeRecord, Measurement
from . import geometry as geo
from .api import (
    AmbiguousElement,
    DrawingDriver,
    ElementNotFound,
    MeasurementError,
    UnsupportedOperation,
)

SUPPORTED_METRICS = (
    "width",
    "length",
    "height",
    "area",
    "count",
    "setback",
    "clear_width",
    "clear_distance",
    "floor_area",
    "text",
)


class JSONModelDriver(DrawingDriver):
    """Drawing driver over a JSON document."""

    name = "json_model"

    def __init__(self, model: dict, path: Path | None = None):
        super().__init__()
        self.model = copy.deepcopy(model)
        self.path = Path(path) if path else None
        self.model.setdefault("elements", [])
        self.model.setdefault("schedules", {})
        self.model.setdefault("sheets", [])
        self.model.setdefault("site", {})

    # ------------------------------------------------------------------
    # construction
    # ------------------------------------------------------------------
    @classmethod
    def load(cls, path) -> "JSONModelDriver":
        path = Path(path)
        with open(path, encoding="utf-8") as handle:
            return cls(json.load(handle), path=path)

    def sandbox(self) -> "JSONModelDriver":
        return JSONModelDriver(copy.deepcopy(self.model), path=self.path)

    def snapshot(self) -> dict:
        return copy.deepcopy(self.model)

    def restore(self, snapshot: dict) -> None:
        self.model = copy.deepcopy(snapshot)

    def save_as(self, path) -> str:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(self.model, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        return str(path)

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------
    def _element(self, element_id: str) -> dict:
        for element in self.model["elements"]:
            if element["id"] == element_id:
                return element
        raise ElementNotFound(f"element not found: {element_id!r}")

    def _box(self, element: dict) -> geo.Box:
        return geo.box_from_dict(element["geometry"])

    def _plot(self) -> geo.Box:
        plot = self.model.get("site", {}).get("plot")
        if not plot:
            raise MeasurementError("model has no site plot; setbacks cannot be measured")
        return geo.box_from_dict(plot)

    @staticmethod
    def _axes(element: dict) -> tuple[str, str]:
        props = element.get("properties", {})
        width_axis = props.get("width_axis", "x")
        length_axis = "y" if width_axis == "x" else "x"
        return width_axis, props.get("length_axis", length_axis)

    def _extent(self, element: dict, axis: str) -> float:
        box = self._box(element)
        return box.w if axis == "x" else box.h

    def _dimension(self, element: dict, parameter: str) -> float:
        width_axis, length_axis = self._axes(element)
        if parameter == "width":
            return self._extent(element, width_axis)
        if parameter == "length":
            return self._extent(element, length_axis)
        if parameter == "height":
            value = element.get("properties", {}).get("height")
            if value is None:
                raise MeasurementError(f"{element['id']} has no height property")
            return float(value)
        raise UnsupportedOperation(f"unsupported dimension: {parameter!r}")

    # ------------------------------------------------------------------
    # query
    # ------------------------------------------------------------------
    def find_element(self, **filters: Any) -> list[str]:
        filters = {k: v for k, v in filters.items() if v not in (None, "", [])}
        found: list[str] = []
        for element in self.model["elements"]:
            props = element.get("properties", {})
            if not all(self._matches(element, props, key, value) for key, value in filters.items()):
                continue
            found.append(element["id"])
        self.log("find_element", filters, found)
        return found

    @staticmethod
    def _matches(element: dict, props: dict, key: str, value: Any) -> bool:
        if key in ("id", "element_id"):
            return element["id"] == value
        if key == "label":
            return str(element.get("label", "")).casefold() == str(value).casefold()
        if key == "label_contains":
            return str(value).casefold() in str(element.get("label", "")).casefold()
        if key in element:
            return str(element[key]).casefold() == str(value).casefold()
        if key in props:
            return str(props[key]).casefold() == str(value).casefold()
        return False

    def resolve_one(self, **filters: Any) -> str:
        found = self.find_element(**filters)
        if not found:
            raise ElementNotFound(f"no element matches {filters}")
        if len(found) > 1:
            raise AmbiguousElement(f"{len(found)} elements match {filters}", found)
        return found[0]

    def get_element(self, element_id: str) -> dict:
        return copy.deepcopy(self._element(element_id))

    def get_element_geometry(self, element_id: str) -> dict:
        element = self._element(element_id)
        box = self._box(element)
        width_axis, length_axis = self._axes(element)
        return {
            "bbox": box.to_dict(),
            "area": box.area,
            "centre": box.centre,
            "width": self._extent(element, width_axis),
            "length": self._extent(element, length_axis),
            "level": element.get("level", ""),
        }

    def get_element_properties(self, element_id: str) -> dict:
        return copy.deepcopy(self._element(element_id).get("properties", {}))

    def sheets(self) -> list[dict]:
        return copy.deepcopy(self.model.get("sheets", []))

    def elements(self) -> list[dict]:
        return copy.deepcopy(self.model["elements"])

    def schedules(self) -> dict:
        return copy.deepcopy(self.model.get("schedules", {}))

    # ------------------------------------------------------------------
    # measurement
    # ------------------------------------------------------------------
    def measure(self, subject: dict, metric: str, basis: str = "clear") -> Measurement:
        if metric not in SUPPORTED_METRICS:
            raise UnsupportedOperation(f"unsupported metric: {metric!r}")
        handler = getattr(self, f"_measure_{metric}")
        measurement = handler(subject, basis)
        self.log("measure", {"subject": subject, "metric": metric}, measurement.value)
        return measurement

    def _subject_elements(self, subject: dict) -> list[str]:
        if subject.get("element_id"):
            self._element(subject["element_id"])  # raises if missing
            return [subject["element_id"]]
        selector = subject.get("selector")
        if selector:
            return self.find_element(**selector)
        raise MeasurementError(f"subject names neither an element nor a selector: {subject}")

    def _single(self, subject: dict) -> dict:
        ids = self._subject_elements(subject)
        if not ids:
            raise ElementNotFound(f"no element for subject {subject}")
        if len(ids) > 1:
            raise AmbiguousElement(f"subject matches {len(ids)} elements", ids)
        return self._element(ids[0])

    def _measure_width(self, subject: dict, basis: str) -> Measurement:
        element = self._single(subject)
        return Measurement("width", self._dimension(element, "width"), "m", basis,
                           "get_element_geometry", subject)

    def _measure_length(self, subject: dict, basis: str) -> Measurement:
        element = self._single(subject)
        return Measurement("length", self._dimension(element, "length"), "m", basis,
                           "get_element_geometry", subject)

    def _measure_height(self, subject: dict, basis: str) -> Measurement:
        element = self._single(subject)
        return Measurement("height", self._dimension(element, "height"), "m", basis,
                           "get_element_properties", subject)

    def _measure_area(self, subject: dict, basis: str) -> Measurement:
        ids = self._subject_elements(subject)
        total = sum(self._box(self._element(i)).area for i in ids)
        return Measurement("area", total, "m2", basis, "calculate_area", subject,
                           {"elements": ids})

    def _measure_floor_area(self, subject: dict, basis: str) -> Measurement:
        selector = subject.get("selector") or {"counts_as_floor_area": True}
        ids = self.find_element(**selector)
        total = 0.0
        breakdown = {}
        for element_id in ids:
            element = self._element(element_id)
            factor = float(element.get("properties", {}).get("floor_area_factor", 1.0))
            area = self._box(element).area * factor
            breakdown[element_id] = round(area, 3)
            total += area
        return Measurement("floor_area", total, "m2", basis, "calculate_area", subject,
                           {"breakdown": breakdown})

    def _measure_count(self, subject: dict, basis: str) -> Measurement:
        ids = self._subject_elements(subject)
        return Measurement("count", float(len(ids)), "count", basis, "find_element", subject,
                           {"elements": ids})

    def _measure_setback(self, subject: dict, basis: str) -> Measurement:
        element = self._single(subject)
        edge = subject.get("edge")
        if edge not in geo.DIRECTIONS:
            raise MeasurementError(f"setback needs an edge (north/south/east/west), got {edge!r}")
        value = geo.setback(self._box(element), self._plot(), edge)
        return Measurement("setback", value, "m", basis or "to plot line", "calculate_distance",
                           subject, {"edge": edge, "element": element["id"]})

    def _measure_clear_distance(self, subject: dict, basis: str) -> Measurement:
        element = self._single(subject)
        against = subject.get("against") or {}
        others = self.find_element(**against) if against else [
            e["id"] for e in self.model["elements"] if e["id"] != element["id"]
        ]
        others = [o for o in others if o != element["id"]]
        if not others:
            raise MeasurementError(f"no elements to measure {element['id']} against")
        box = self._box(element)
        gaps = {o: geo.clear_gap(box, self._box(self._element(o))) for o in others}
        nearest = min(gaps, key=gaps.get)
        return Measurement("clear_distance", gaps[nearest], "m", "clear", "check_clearance",
                           subject, {"nearest": nearest, "gaps": {k: round(v, 3) for k, v in gaps.items()}})

    def _measure_clear_width(self, subject: dict, basis: str) -> Measurement:
        """Largest free width across an element after intrusions are removed."""
        element = self._single(subject)
        box = self._box(element)
        width_axis, _ = self._axes(element)
        low, high = (box.x, box.x_max) if width_axis == "x" else (box.y, box.y_max)
        ignore = set(subject.get("ignore", []))
        ignore_types = set(subject.get("ignore_types", []))
        intrusions: list[tuple[float, float]] = []
        for other in self.model["elements"]:
            if other["id"] == element["id"] or other["id"] in ignore:
                continue
            if other.get("type") in ignore_types or other.get("type") in {"dimension", "text"}:
                continue
            other_box = self._box(other)
            if geo.overlap(box, other_box) <= 0:
                continue
            if width_axis == "x":
                intrusions.append((max(low, other_box.x), min(high, other_box.x_max)))
            else:
                intrusions.append((max(low, other_box.y), min(high, other_box.y_max)))
        free = _largest_free_interval(low, high, intrusions)
        return Measurement("clear_width", free, "m", "clear", "check_clearance", subject,
                           {"span": [low, high], "intrusions": [list(i) for i in intrusions]})

    def _measure_text(self, subject: dict, basis: str) -> Measurement:
        element = self._single(subject)
        text = element.get("text", element.get("label", ""))
        return Measurement("text", float(len(text)), "count", basis, "get_element", subject,
                           {"text": text})

    def calculate_distance(self, a: str, b: str, mode: str = "clear") -> float:
        box_a, box_b = self._box(self._element(a)), self._box(self._element(b))
        if mode == "centre":
            value = geo.centre_distance(box_a, box_b)
        elif mode in ("clear", "edge"):
            value = geo.clear_gap(box_a, box_b)
        else:
            raise UnsupportedOperation(f"unsupported distance mode: {mode!r}")
        self.log("calculate_distance", {"a": a, "b": b, "mode": mode}, value)
        return value

    def calculate_area(self, element_id: str) -> float:
        value = self._box(self._element(element_id)).area
        self.log("calculate_area", {"element_id": element_id}, value)
        return value

    def check_overlap(self, a: str, b: str) -> dict:
        area = geo.overlap(self._box(self._element(a)), self._box(self._element(b)))
        result = {"overlaps": area > 0, "area": area}
        self.log("check_overlap", {"a": a, "b": b}, result)
        return result

    def check_clearance(self, element_id: str, against: list[str], required: float) -> dict:
        box = self._box(self._element(element_id))
        gaps = {o: geo.clear_gap(box, self._box(self._element(o))) for o in against}
        minimum = min(gaps.values()) if gaps else float("inf")
        result = {"min": minimum, "passes": minimum >= required, "gaps": gaps}
        self.log("check_clearance", {"element_id": element_id, "required": required}, result)
        return result

    # ------------------------------------------------------------------
    # mutation
    # ------------------------------------------------------------------
    def _record(self, element: dict, prop: str, before: Any, after: Any, tool: str,
                kind: str = "modified") -> ChangeRecord:
        return ChangeRecord(
            element_id=element.get("id", ""),
            property=prop,
            before=before,
            after=after,
            plan_id=self._plan_id or "",
            tool=tool,
            sheet=element.get("sheet", ""),
            kind=kind,
        )

    def move_element(self, element_id: str, distance: float, direction: str) -> ChangeRecord:
        self._require_authorisation("move_element")
        if direction not in geo.DIRECTIONS:
            raise UnsupportedOperation(f"unknown direction: {direction!r}")
        element = self._element(element_id)
        box = self._box(element)
        dx, dy = geo.DIRECTIONS[direction]
        moved = box.moved(dx * distance, dy * distance)
        element["geometry"] = moved.to_dict()
        record = self._record(element, "position", box.to_dict(), moved.to_dict(), "move_element")
        self.log("move_element", {"element_id": element_id, "distance": distance, "direction": direction})
        return record

    def resize_element(self, element_id: str, parameter: str, value: float, anchor: str = "") -> ChangeRecord:
        self._require_authorisation("resize_element")
        element = self._element(element_id)
        before = self._dimension(element, parameter)
        width_axis, length_axis = self._axes(element)
        axis = width_axis if parameter == "width" else length_axis
        anchor = anchor or element.get("properties", {}).get("anchor", "south_west")
        box = self._box(element)
        new_box = box.resized(w=value, anchor=anchor) if axis == "x" else box.resized(h=value, anchor=anchor)
        if parameter == "height":
            element.setdefault("properties", {})["height"] = value
        else:
            element["geometry"] = new_box.to_dict()
        after = self._dimension(element, parameter)
        record = self._record(element, parameter, before, after, "resize_element")
        self.log("resize_element", {"element_id": element_id, "parameter": parameter, "value": value})
        return record

    def rotate_element(self, element_id: str, angle: float, pivot: str = "centre") -> ChangeRecord:
        self._require_authorisation("rotate_element")
        if abs(angle % 90.0) > 1e-9:
            raise UnsupportedOperation(
                "the reference driver rotates axis-aligned geometry in 90 degree steps only"
            )
        element = self._element(element_id)
        box = self._box(element)
        cx, cy = box.centre
        rotated = geo.Box(cx - box.h / 2, cy - box.w / 2, box.h, box.w) if int(angle / 90) % 2 else box
        element["geometry"] = rotated.to_dict()
        props = element.setdefault("properties", {})
        props["rotation"] = (float(props.get("rotation", 0.0)) + angle) % 360
        record = self._record(element, "rotation", box.to_dict(), rotated.to_dict(), "rotate_element")
        self.log("rotate_element", {"element_id": element_id, "angle": angle, "pivot": pivot})
        return record

    def delete_element(self, element_id: str) -> ChangeRecord:
        self._require_authorisation("delete_element")
        element = self._element(element_id)
        self.model["elements"] = [e for e in self.model["elements"] if e["id"] != element_id]
        record = self._record(element, "existence", "present", "removed", "delete_element", "removed")
        self.log("delete_element", {"element_id": element_id})
        return record

    def create_element(self, element_type: str, geometry: dict, properties: dict) -> ChangeRecord:
        self._require_authorisation("create_element")
        properties = dict(properties or {})
        element_id = properties.pop("id", None) or f"{element_type}_{len(self.model['elements']) + 1}"
        if any(e["id"] == element_id for e in self.model["elements"]):
            raise UnsupportedOperation(f"element id already exists: {element_id}")
        element = {
            "id": element_id,
            "type": element_type,
            "label": properties.pop("label", element_id),
            "layer": properties.pop("layer", ""),
            "level": properties.pop("level", ""),
            "sheet": properties.pop("sheet", ""),
            "text": properties.pop("text", ""),
            "geometry": geometry,
            "properties": properties,
        }
        self.model["elements"].append(element)
        record = self._record(element, "existence", "absent", "created", "create_element", "created")
        self.log("create_element", {"type": element_type, "id": element_id})
        return record

    def update_text(self, element_id: str, text: str) -> ChangeRecord:
        self._require_authorisation("update_text")
        element = self._element(element_id)
        before = element.get("text", element.get("label", ""))
        element["text"] = text
        record = self._record(element, "text", before, text, "update_text")
        self.log("update_text", {"element_id": element_id, "text": text})
        return record

    def update_dimension(self, dimension_id: str, value: float | None = None,
                         recompute: bool = False) -> ChangeRecord:
        self._require_authorisation("update_dimension")
        element = self._element(dimension_id)
        props = element.setdefault("properties", {})
        before = props.get("value")
        if recompute:
            measures = props.get("measures")
            if not measures:
                raise UnsupportedOperation(f"{dimension_id} has no 'measures' link to recompute from")
            target = self._element(measures["element_id"])
            value = self._dimension(target, measures.get("parameter", "width"))
        if value is None:
            raise UnsupportedOperation("update_dimension needs either a value or recompute=True")
        props["value"] = value
        element["text"] = f"{value:.2f}"
        record = self._record(element, "value", before, value, "update_dimension")
        self.log("update_dimension", {"dimension_id": dimension_id, "value": value})
        return record

    def update_schedule(self, schedule_id: str, recompute: bool = True) -> ChangeRecord:
        self._require_authorisation("update_schedule")
        schedule = self.model.get("schedules", {}).get(schedule_id)
        if schedule is None:
            raise ElementNotFound(f"schedule not found: {schedule_id!r}")
        before = copy.deepcopy(schedule.get("rows", []))
        if not recompute:
            raise UnsupportedOperation("manual schedule rows are not supported; use recompute=True")
        rows = []
        for element_id in self.find_element(**schedule.get("source", {})):
            element = self._element(element_id)
            row = {}
            for column, spec in schedule.get("fields", {}).items():
                row[column] = self._schedule_value(element, spec)
            rows.append(row)
        schedule["rows"] = rows
        schedule["total"] = len(rows)
        record = ChangeRecord(
            element_id=schedule_id, property="rows", before=before, after=copy.deepcopy(rows),
            plan_id=self._plan_id or "", tool="update_schedule",
            sheet=schedule.get("sheet", ""), kind="schedule",
        )
        self.log("update_schedule", {"schedule_id": schedule_id})
        return record

    def _schedule_value(self, element: dict, spec: str) -> Any:
        if spec in ("width", "length", "height"):
            return round(self._dimension(element, spec), 2)
        if spec == "area":
            return round(self._box(element).area, 2)
        if spec in element:
            return element[spec]
        return element.get("properties", {}).get(spec, "")


def _largest_free_interval(low: float, high: float, intrusions: list[tuple[float, float]]) -> float:
    """Largest gap in ``[low, high]`` once the intrusion intervals are removed."""
    blocked = sorted((max(low, a), min(high, b)) for a, b in intrusions if b > low and a < high)
    merged: list[list[float]] = []
    for start, end in blocked:
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    best = 0.0
    cursor = low
    for start, end in merged:
        best = max(best, start - cursor)
        cursor = max(cursor, end)
    return max(best, high - cursor)
