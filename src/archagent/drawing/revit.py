"""Driver for a live Revit document, over the Archagent host protocol.

The Revit API only runs on Revit's own thread inside Revit's own process, so
there is no way to "connect to Revit" from Python directly.  What connects is
an add-in that hosts this protocol inside Revit (``revit-addin/``); this class
is the client half.

What is deliberately different from the file-based driver:

* **A plan is one batch.** Revit only allows a transaction inside a single API
  context, so ``authorised(plan_id)`` collects the plan's actions and sends
  them in one call; the host applies them in one transaction group and commits,
  or rolls the group back. A half-applied plan cannot exist, and the add-in
  never has to hold a transaction open between HTTP requests.
* **Simulation runs on a snapshot, not on the user's model.** ``sandbox()``
  copies the host's current geometry and simulates locally, so nothing is
  written until a plan has been simulated and approved. Whatever the snapshot
  cannot capture is caught afterwards: validation re-measures through the host.
* **Measurement stays with the host** where it needs real geometry, and falls
  back to this side for the planning metrics the host does not implement.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from ..models import ChangeRecord, Measurement
from . import geometry as geo
from . import protocol
from .api import (
    AmbiguousElement,
    DrawingAPIError,
    DrawingDriver,
    ElementNotFound,
    MeasurementError,
    NotAuthorised,
    UnsupportedOperation,
)

ERROR_CLASSES = {
    protocol.ERR_NOT_FOUND: ElementNotFound,
    protocol.ERR_AMBIGUOUS: AmbiguousElement,
    protocol.ERR_UNSUPPORTED: UnsupportedOperation,
    protocol.ERR_NO_TRANSACTION: NotAuthorised,
    protocol.ERR_READ_ONLY: NotAuthorised,
    protocol.ERR_MEASUREMENT: MeasurementError,
}

#: Metrics this side can compute from bounding boxes when a host does not.
LOCAL_METRICS = {"setback", "clear_width", "clear_distance", "count", "area", "floor_area"}


class HostUnavailable(DrawingAPIError):
    """The CAD host is not reachable - Revit closed, add-in not loaded."""


class RevitDriver(DrawingDriver):
    """A live Revit document, reached through the Archagent add-in."""

    name = "revit"

    def __init__(self, base_url: str = "http://127.0.0.1:8735", timeout: float = 120.0,
                 token: str = "", session: "RevitDriver | None" = None):
        super().__init__()
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.token = token
        self._transaction: str | None = None
        self._pending: list[dict] = []
        self._records: list[ChangeRecord] = []
        self._simulating = bool(session)
        self._info: protocol.HostInfo | None = None
        self._plot: geo.Box | None = None
        self._element_cache: dict[str, dict] = {}

    # ------------------------------------------------------------------
    # transport
    # ------------------------------------------------------------------
    def _call(self, endpoint: str, payload: dict | None = None) -> dict:
        body = json.dumps(payload or {}).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}{endpoint}", data=body, method="POST",
            headers={"Content-Type": "application/json",
                     **({"X-Archagent-Token": self.token} if self.token else {})})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                data = json.loads(response.read().decode("utf-8") or "{}")
        except urllib.error.HTTPError as error:
            data = _read_error(error)
        except urllib.error.URLError as error:
            raise HostUnavailable(
                f"the Revit host at {self.base_url} did not answer ({error.reason}). "
                "Is Revit open with the Archagent add-in loaded?") from error
        except TimeoutError as error:
            raise HostUnavailable(f"the Revit host timed out after {self.timeout}s") from error
        if isinstance(data, dict) and data.get("error"):
            raise _to_exception(data)
        return data if isinstance(data, dict) else {"value": data}

    # ------------------------------------------------------------------
    # host
    # ------------------------------------------------------------------
    def info(self, refresh: bool = False) -> protocol.HostInfo:
        if self._info is None or refresh:
            self._info = protocol.HostInfo.from_dict(self._call(protocol.HEALTH))
            if not self._info.compatible():
                raise DrawingAPIError(
                    f"the host speaks protocol {self._info.protocol}, this client speaks "
                    f"{protocol.PROTOCOL_VERSION}")
        return self._info

    @property
    def read_only(self) -> bool:  # type: ignore[override]
        try:
            return self.info().read_only
        except DrawingAPIError:
            return False

    @read_only.setter
    def read_only(self, value: bool) -> None:
        # DrawingDriver.__init__ sets the class attribute; the host owns it here.
        pass

    # ------------------------------------------------------------------
    # transactions
    # ------------------------------------------------------------------
    def authorised(self, plan_id: str):  # type: ignore[override]
        """Collect the plan's actions and send them to the host as one batch.

        Nothing is sent while the block runs: if an action raises, or the caller
        aborts, the host never hears about the plan at all.  On a clean exit the
        whole list goes in one request, the host applies it inside a single
        transaction group, and the change records come back filled in.
        """
        driver = self

        class _Batch:
            def __enter__(self_inner):
                if not plan_id:
                    raise NotAuthorised("a plan id is required to mutate the model")
                if driver.read_only:
                    raise NotAuthorised("the host opened the document read-only")
                driver._plan_id = plan_id
                driver._pending = []
                driver._records = []
                return driver

            def __exit__(self_inner, exc_type, exc, traceback):
                pending, driver._pending = driver._pending, []
                records, driver._records = driver._records, []
                driver._plan_id = None
                driver._element_cache.clear()
                if exc_type is not None or not pending:
                    return False
                driver._flush(plan_id, pending, records)
                return False

        return _Batch()

    def _flush(self, plan_id: str, actions: list[dict], records: list[ChangeRecord]) -> None:
        """Send the whole plan; fill in the records the caller already holds."""
        data = self._call(protocol.APPLY, {"plan_id": plan_id, "actions": actions})
        applied = data.get("changes", [])
        if len(applied) != len(records):
            raise DrawingAPIError(
                f"the host applied {len(applied)} of {len(records)} actions; "
                f"the transaction was rolled back: {data.get('message', '')}".strip())
        for record, change in zip(records, applied):
            record.element_id = change.get("element_id", record.element_id)
            record.property = change.get("property", record.property)
            record.before = change.get("before")
            record.after = change.get("after")
            record.sheet = change.get("sheet", "")
            record.kind = change.get("kind", "modified")
            if record.before is None and record.after is None:
                raise DrawingAPIError(
                    f"{record.tool}: the host reported no before/after value")

    def _require_transaction(self, tool: str) -> str:
        if not self._transaction:
            raise NotAuthorised(f"{tool}: mutation attempted outside an approved plan")
        return self._transaction

    # ------------------------------------------------------------------
    # query
    # ------------------------------------------------------------------
    def find_element(self, **filters: Any) -> list[str]:
        filters = {key: value for key, value in filters.items() if value not in (None, "", [])}
        found = self._call(protocol.FIND, {"filter": filters}).get("elements", [])
        self.log("find_element", filters, found)
        return [str(item) for item in found]

    def get_element(self, element_id: str) -> dict:
        """An element in the shape the pipeline speaks, not the host's.

        Translating here is the driver's job: everything above this layer -
        planner, graph, validator, previews - reads one element shape, whichever
        CAD it came from.
        """
        return _as_json_element(self.host_element(element_id))

    def host_element(self, element_id: str) -> dict:
        """The host's own document for an element, untranslated."""
        if element_id in self._element_cache:
            return dict(self._element_cache[element_id])
        element = self._call(protocol.ELEMENT, {"id": element_id})
        self._element_cache[element_id] = element
        return dict(element)

    def get_element_geometry(self, element_id: str) -> dict:
        return self._call(protocol.GEOMETRY, {"id": element_id})

    def get_element_properties(self, element_id: str) -> dict:
        return self._call(protocol.PROPERTIES, {"id": element_id}).get("properties", {})

    def sheets(self) -> list[dict]:
        return self._call(protocol.SHEETS).get("sheets", [])

    def elements(self) -> list[dict]:
        """The element index the planner and the previews iterate over."""
        return [_as_json_element(element) for element in self.host_elements()]

    def host_elements(self) -> list[dict]:
        return self._call(protocol.FIND, {"filter": {}, "detail": "full"}).get("elements", [])

    def schedules(self) -> dict:
        return self._call(protocol.SHEETS).get("schedules", {})

    # ------------------------------------------------------------------
    # measurement
    # ------------------------------------------------------------------
    def measure(self, subject: dict, metric: str, basis: str = "clear") -> Measurement:
        try:
            data = self._call(protocol.MEASURE,
                              {"subject": subject, "metric": metric, "basis": basis})
        except UnsupportedOperation:
            if metric not in LOCAL_METRICS:
                raise
            return self._measure_locally(subject, metric, basis)
        measurement = Measurement(
            metric=metric, value=float(data["value"]),
            unit=data.get("unit", protocol.UNIT_LENGTH),
            basis=data.get("basis", basis), tool=data.get("tool", "revit"),
            subject=subject, details=data.get("details", {}))
        self.log("measure", {"subject": subject, "metric": metric}, measurement.value)
        return measurement

    def _measure_locally(self, subject: dict, metric: str, basis: str) -> Measurement:
        """Planning metrics computed from the boxes the host reported.

        The host owns real geometry; these are relationships between elements,
        which are the same arithmetic in any host.
        """
        from .json_model import JSONModelDriver

        measurement = JSONModelDriver(self.plan_model()).measure(subject, metric, basis)
        measurement.tool = f"{measurement.tool} (computed from host geometry)"
        return measurement

    def set_plot(self, box: geo.Box | dict | None) -> None:
        """Tell the driver where the plot line is, for setback measurement."""
        if box is None:
            self._plot = None
        elif isinstance(box, geo.Box):
            self._plot = box
        else:
            self._plot = geo.box_from_dict(box)

    def calculate_distance(self, a: str, b: str, mode: str = "clear") -> float:
        return float(self._call(protocol.DISTANCE, {"a": a, "b": b, "mode": mode})["value"])

    def calculate_area(self, element_id: str) -> float:
        return float(self.measure({"element_id": element_id}, "area").value)

    def check_overlap(self, a: str, b: str) -> dict:
        return self._call(protocol.OVERLAP, {"a": a, "b": b})

    def check_clearance(self, element_id: str, against: list[str], required: float) -> dict:
        return self._call(protocol.CLEARANCE,
                          {"id": element_id, "against": against, "required": required})

    # ------------------------------------------------------------------
    # mutation
    # ------------------------------------------------------------------
    def _apply(self, action: str, tool: str, **payload: Any) -> ChangeRecord:
        """Queue an action; the batch goes out when the plan block closes."""
        if not self._plan_id:
            raise NotAuthorised(f"{tool}: mutation attempted outside an approved plan")
        self._pending.append({"action": action, **payload})
        record = ChangeRecord(element_id=payload.get("id", ""), property="",
                              before=None, after=None, plan_id=self._plan_id, tool=tool)
        self._records.append(record)
        self.log(tool, payload)
        return record

    def move_element(self, element_id: str, distance: float, direction: str) -> ChangeRecord:
        if direction not in geo.DIRECTIONS:
            raise UnsupportedOperation(f"unknown direction: {direction!r}")
        return self._apply(protocol.MOVE, "move_element", id=element_id,
                           distance=float(distance), direction=direction)

    def resize_element(self, element_id: str, parameter: str, value: float,
                       anchor: str = "") -> ChangeRecord:
        return self._apply(protocol.RESIZE, "resize_element", id=element_id,
                           parameter=parameter, value=float(value), anchor=anchor)

    def rotate_element(self, element_id: str, angle: float, pivot: str = "centre") -> ChangeRecord:
        return self._apply(protocol.ROTATE, "rotate_element", id=element_id,
                           angle=float(angle), pivot=pivot)

    def delete_element(self, element_id: str) -> ChangeRecord:
        return self._apply(protocol.DELETE, "delete_element", id=element_id)

    def create_element(self, element_type: str, geometry: dict, properties: dict) -> ChangeRecord:
        return self._apply(protocol.CREATE, "create_element", type=element_type,
                           geometry=geometry, properties=properties or {})

    def update_text(self, element_id: str, text: str) -> ChangeRecord:
        return self._apply(protocol.SET_TEXT, "update_text", id=element_id, text=text)

    def update_dimension(self, dimension_id: str, value: float | None = None,
                         recompute: bool = False) -> ChangeRecord:
        return self._apply(protocol.UPDATE_DIMENSION, "update_dimension", id=dimension_id,
                           value=value, recompute=recompute)

    def update_schedule(self, schedule_id: str, recompute: bool = True) -> ChangeRecord:
        return self._apply(protocol.UPDATE_SCHEDULE, "update_schedule", id=schedule_id,
                           recompute=recompute)

    def set_parameter(self, element_id: str, parameter: str, value: Any) -> ChangeRecord:
        """Revit's own escape hatch: set a family or instance parameter."""
        return self._apply(protocol.SET_PARAMETER, "set_parameter", id=element_id,
                           parameter=parameter, value=value)

    # ------------------------------------------------------------------
    # lifecycle
    # ------------------------------------------------------------------
    def snapshot(self) -> Any:
        """Open a rollback point in the document and return its handle."""
        return self._call(protocol.BEGIN, {"plan_id": "snapshot", "simulation": False})["transaction"]

    def restore(self, snapshot: Any) -> None:
        self._call(protocol.ROLLBACK, {"transaction": snapshot})
        self._element_cache.clear()

    def sandbox(self):
        """Simulate on a snapshot of the host's geometry, never on the document.

        Revit cannot keep a transaction open between requests, so a rollback-
        based sandbox would mean writing to the architect's open model to find
        out whether a change is safe.  Taking the geometry and simulating here
        is both safer and faster; what a snapshot cannot model is caught by
        validation, which re-measures through the host after the change.
        """
        from .json_model import JSONModelDriver

        return JSONModelDriver(self.plan_model())

    def close(self) -> None:
        self._element_cache.clear()
        self._pending.clear()
        self._records.clear()

    def save_as(self, path) -> str:
        data = self._call(protocol.SAVE_AS, {"path": str(path)})
        return data.get("path", str(path))

    def export_view(self, view: str = "", image_format: str = "png",
                    path: str = "", highlight: list[str] | None = None) -> str:
        """Export a view - used for the before/after previews."""
        data = self._call(protocol.EXPORT, {"view": view, "format": image_format,
                                            "path": path, "highlight": highlight or []})
        return data.get("path", "")

    def plan_model(self) -> dict:
        """The whole document as a plan model - elements, sheets and schedules.

        A snapshot that dropped the schedules would make every plan that
        updates one fail in simulation, so the snapshot carries everything the
        planner can act on.
        """
        sheets = self._call(protocol.SHEETS)
        model = {"elements": self.elements(), "site": {},
                 "sheets": sheets.get("sheets", []),
                 "schedules": sheets.get("schedules", {})}
        if self._plot is not None:
            model["site"] = {"plot": self._plot.to_dict()}
        else:
            plot = next((element for element in model["elements"]
                         if element["type"] in ("site", "plot", "boundary")), None)
            if plot:
                model["site"] = {"plot": plot["geometry"]}
        return model

    def highlight(self, element_ids: list[str]) -> int:
        """Select the changed elements in Revit, so the architect sees the diff.

        Selection is not a document edit - no transaction, no plan, nothing
        undoable - which is why it is allowed outside ``authorised``.
        """
        data = self._call(protocol.HIGHLIGHT, {"ids": list(element_ids)})
        return int(data.get("selected", 0))

    def changes(self, transaction: str = "") -> list[dict]:
        """The host's own record of what changed - the raw material of a diff."""
        return self._call(protocol.CHANGES, {"transaction": transaction}).get("changes", [])


# ----------------------------------------------------------------------
def _read_error(error: urllib.error.HTTPError) -> dict:
    try:
        return json.loads(error.read().decode("utf-8") or "{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {"error": protocol.ERR_HOST, "message": f"HTTP {error.code}"}


def _to_exception(data: dict) -> DrawingAPIError:
    code = data.get("error", protocol.ERR_HOST)
    message = data.get("message") or code
    factory = ERROR_CLASSES.get(code, DrawingAPIError)
    if factory is AmbiguousElement:
        return AmbiguousElement(message, data.get("candidates", []))
    return factory(message)


def _as_json_element(element: dict) -> dict:
    """Shape a host element the way the geometry helpers expect."""
    if "type" in element and "category" not in element:
        return element  # already translated
    bbox = (element.get("geometry") or {}).get("bbox") or {}
    properties = dict(element.get("properties") or {})
    properties.setdefault("width_axis", properties.get("width_axis", "x"))
    for key in ("rotation", "elevation", "height"):
        value = (element.get("geometry") or {}).get(key)
        if value not in (None, 0.0) and key not in properties:
            properties[key] = value
    if element.get("type_name"):
        properties.setdefault("type_name", element["type_name"])
    if element.get("pinned"):
        properties.setdefault("pinned", True)
    return {
        "id": element.get("id", ""),
        "type": element.get("category", "generic"),
        "label": element.get("label") or element.get("name", ""),
        "level": element.get("level", ""),
        "sheet": element.get("sheet", ""),
        "geometry": {"kind": "rect", "x": float(bbox.get("x", 0.0)),
                     "y": float(bbox.get("y", 0.0)), "w": float(bbox.get("w", 0.0)),
                     "h": float(bbox.get("h", 0.0))},
        "properties": properties,
    }
