"""The drawing-editing tool interface (SKILL.md 12).

Everything above this layer speaks only these operations.  A CAD/BIM adapter
implements :class:`DrawingDriver` against the host application's API; the
reference :class:`~archagent.drawing.json_model.JSONModelDriver` implements it
against a plain JSON model so the whole pipeline is runnable and testable
without a CAD seat.

Two rules are enforced here rather than left to convention:

* mutations are rejected unless they cite an approved plan
  (:meth:`DrawingDriver.authorised`);
* every mutation returns a :class:`~archagent.models.ChangeRecord` carrying
  ``before`` and ``after`` - a mutation that cannot report both is a failure.
"""

from __future__ import annotations

import abc
from contextlib import contextmanager
from typing import Any, Iterator

from ..models import ChangeRecord, Measurement


class DrawingAPIError(RuntimeError):
    """Base class for every driver failure (SKILL.md 21)."""


class ElementNotFound(DrawingAPIError):
    pass


class AmbiguousElement(DrawingAPIError):
    def __init__(self, message: str, candidates: list[str] | None = None):
        super().__init__(message)
        self.candidates = candidates or []


class UnsupportedOperation(DrawingAPIError):
    pass


class NotAuthorised(DrawingAPIError):
    """A mutation was attempted without an approved plan id."""


class MeasurementError(DrawingAPIError):
    pass


class DrawingDriver(abc.ABC):
    """Abstract drawing-editing API."""

    name = "abstract"
    read_only = False
    #: The filename suffix a version of this driver's model is saved with -
    #: read by ``VersionStore`` so ``save_as`` gets a path in the driver's own
    #: native format instead of always ".json".
    preferred_suffix = ".json"

    def __init__(self) -> None:
        self._plan_id: str | None = None
        self.call_log: list[dict] = []

    # ------------------------------------------------------------------
    # authorisation
    # ------------------------------------------------------------------
    @contextmanager
    def authorised(self, plan_id: str) -> Iterator["DrawingDriver"]:
        """Allow mutations for the duration of the block, for one plan only."""
        if not plan_id:
            raise NotAuthorised("a plan id is required to mutate the model")
        previous, self._plan_id = self._plan_id, plan_id
        try:
            yield self
        finally:
            self._plan_id = previous

    def _require_authorisation(self, tool: str) -> str:
        if self.read_only:
            raise NotAuthorised(f"{tool}: driver is read-only")
        if not self._plan_id:
            raise NotAuthorised(f"{tool}: mutation attempted outside an approved plan")
        return self._plan_id

    # ------------------------------------------------------------------
    # query
    # ------------------------------------------------------------------
    @abc.abstractmethod
    def find_element(self, **filters: Any) -> list[str]:
        """Return element ids matching type/layer/label/level/sheet filters."""

    @abc.abstractmethod
    def get_element(self, element_id: str) -> dict:
        ...

    @abc.abstractmethod
    def get_element_geometry(self, element_id: str) -> dict:
        ...

    @abc.abstractmethod
    def get_element_properties(self, element_id: str) -> dict:
        ...

    @abc.abstractmethod
    def sheets(self) -> list[dict]:
        ...

    # ------------------------------------------------------------------
    # measurement
    # ------------------------------------------------------------------
    @abc.abstractmethod
    def measure(self, subject: dict, metric: str, basis: str = "clear") -> Measurement:
        """Measure *metric* on *subject*; the single source of reported values."""

    @abc.abstractmethod
    def calculate_distance(self, a: str, b: str, mode: str = "clear") -> float:
        ...

    @abc.abstractmethod
    def calculate_area(self, element_id: str) -> float:
        ...

    @abc.abstractmethod
    def check_overlap(self, a: str, b: str) -> dict:
        ...

    @abc.abstractmethod
    def check_clearance(self, element_id: str, against: list[str], required: float) -> dict:
        ...

    # ------------------------------------------------------------------
    # mutation
    # ------------------------------------------------------------------
    @abc.abstractmethod
    def move_element(self, element_id: str, distance: float, direction: str) -> ChangeRecord:
        ...

    @abc.abstractmethod
    def resize_element(self, element_id: str, parameter: str, value: float, anchor: str = "") -> ChangeRecord:
        ...

    @abc.abstractmethod
    def rotate_element(self, element_id: str, angle: float, pivot: str = "centre") -> ChangeRecord:
        ...

    @abc.abstractmethod
    def delete_element(self, element_id: str) -> ChangeRecord:
        ...

    @abc.abstractmethod
    def create_element(self, element_type: str, geometry: dict, properties: dict) -> ChangeRecord:
        ...

    @abc.abstractmethod
    def update_text(self, element_id: str, text: str) -> ChangeRecord:
        ...

    @abc.abstractmethod
    def update_dimension(self, dimension_id: str, value: float | None = None, recompute: bool = False) -> ChangeRecord:
        ...

    @abc.abstractmethod
    def update_schedule(self, schedule_id: str, recompute: bool = True) -> ChangeRecord:
        ...

    # ------------------------------------------------------------------
    # lifecycle
    # ------------------------------------------------------------------
    @abc.abstractmethod
    def snapshot(self) -> Any:
        """Opaque state used to roll a failed transaction back."""

    @abc.abstractmethod
    def restore(self, snapshot: Any) -> None:
        ...

    @abc.abstractmethod
    def sandbox(self) -> "DrawingDriver":
        """A driver for simulation, to be used as a context manager.

        A file-backed driver returns an isolated copy.  A live host cannot fork
        a document, so it returns a driver bound to a transaction that is rolled
        back on close - which is why callers must close it (SKILL.md 9.1).
        """

    @abc.abstractmethod
    def save_as(self, path) -> str:
        ...

    def plan_model(self) -> dict:
        """The plan the previews and the local metrics work from.

        A file driver returns its own document; a live host is asked for its
        elements and they are shaped the same way, so nothing above this layer
        needs to know which kind of driver it holds.
        """
        elements = getattr(self, "elements", None)
        index = elements() if elements is not None else []
        schedules = getattr(self, "schedules", None)
        model: dict = {"elements": index, "site": {},
                       "sheets": self.sheets(),
                       "schedules": schedules() if schedules is not None else {}}
        plot = next((element for element in index
                     if str(element.get("type", "")).casefold() in ("site", "plot", "boundary")),
                    None)
        if plot and plot.get("geometry"):
            model["site"] = {"plot": plot["geometry"]}
        return model

    def close(self) -> None:
        """Release whatever the driver holds. A file driver holds nothing."""

    def __enter__(self) -> "DrawingDriver":
        return self

    def __exit__(self, exc_type, exc, traceback) -> bool:
        self.close()
        return False

    def log(self, tool: str, params: dict, result: Any = "ok") -> None:
        self.call_log.append({"tool": tool, "params": params, "result": result, "plan_id": self._plan_id})
