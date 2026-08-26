"""Run management for the web application.

A run is a pipeline execution the browser can watch: it streams events, it can
stop and ask the architect a question, and it ends with a payload the UI
renders.  Runs execute in worker threads; the consultation gate is a plain
``threading.Event``, so a question genuinely blocks the pipeline until the
person answers - exactly as SKILL.md 10 requires.
"""

from __future__ import annotations

import queue
import threading
import traceback
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from ..payload import run_payload

#: Audit events worth showing a human, and the step they belong to.
STEP_OF_EVENT = {
    "ingest": "ingest",
    "language": "ingest",
    "llm_enabled": "ingest",
    "comment_extracted": "comments",
    "conflict": "constraints",
    "mapping": "mapping",
    "baseline": "constraints",
    "plan_generated": "plan",
    "plan_escalated": "plan",
    "no_action_required": "plan",
    "decision_recorded": "consult",
    "precondition_failed": "execute",
    "api_call": "execute",
    "api_error": "execute",
    "validation_result": "validate",
    "version_written": "version",
    "narrative": "report",
    "llm_usage": "report",
    "run_complete": "report",
}

STEPS = [
    ("ingest", "קליטת הקבצים", "Ingest"),
    ("comments", "ניתוח ההערות", "Analyse comments"),
    ("constraints", "בניית מאגר האילוצים", "Build constraints"),
    ("mapping", "איתור האלמנטים", "Map elements"),
    ("plan", "תכנון התיקונים", "Plan corrections"),
    ("consult", "התייעצות", "Consult"),
    ("execute", "ביצוע במודל", "Execute"),
    ("validate", "אימות ומדידה", "Validate"),
    ("version", "שמירת גרסה", "Save version"),
    ("report", "הפקת הדוח", "Report"),
]


__all__ = ["Run", "RunEvent", "RunManager", "STEPS", "STEP_OF_EVENT", "run_payload"]


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


@dataclass
class RunEvent:
    seq: int
    ts: str
    kind: str
    step: str = ""
    title: str = ""
    detail: str = ""
    data: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"seq": self.seq, "ts": self.ts, "kind": self.kind, "step": self.step,
                "title": self.title, "detail": self.detail, "data": self.data}


class Run:
    """One pipeline execution, watchable from the browser."""

    def __init__(self, run_id: str, project_id: str, options: dict):
        self.run_id = run_id
        self.project_id = project_id
        self.options = options
        self.status = "starting"
        self.started_at = now()
        self.finished_at = ""
        self.error = ""
        self.events: list[RunEvent] = []
        self.result: dict | None = None
        self.question: dict | None = None
        self.language = options.get("language", "auto")
        self._seq = 0
        self._lock = threading.Lock()
        self._subscribers: list[queue.Queue] = []
        self._answer: str | None = None
        self._answered = threading.Event()
        self._cancelled = threading.Event()

    # ------------------------------------------------------------------
    # events
    # ------------------------------------------------------------------
    def emit(self, kind: str, title: str = "", detail: str = "", step: str = "",
             **data: Any) -> RunEvent:
        with self._lock:
            self._seq += 1
            event = RunEvent(self._seq, now(), kind, step, title, detail, data)
            self.events.append(event)
            subscribers = list(self._subscribers)
        for subscriber in subscribers:
            try:
                subscriber.put_nowait(event)
            except queue.Full:  # a slow browser never stalls the run
                pass
        return event

    def subscribe(self) -> queue.Queue:
        channel: queue.Queue = queue.Queue(maxsize=1000)
        with self._lock:
            backlog = list(self.events)
            self._subscribers.append(channel)
        for event in backlog:
            channel.put_nowait(event)
        return channel

    def unsubscribe(self, channel: queue.Queue) -> None:
        with self._lock:
            if channel in self._subscribers:
                self._subscribers.remove(channel)

    # ------------------------------------------------------------------
    # consultation gate
    # ------------------------------------------------------------------
    def ask(self, question: dict, timeout: float = 1800.0) -> str:
        """Block the pipeline until the architect answers - or the run stops."""
        self.question = question
        self.status = "waiting"
        self._answered.clear()
        self.emit("question", question.get("title", ""), step="consult", question=question)
        answered = self._answered.wait(timeout)
        self.question = None
        self.status = "running"
        if self._cancelled.is_set():
            return "reject"
        if not answered:
            self.emit("answer", "לא התקבלה תשובה", step="consult", answer="question")
            return "question"
        answer = self._answer or "question"
        self.emit("answer", answer, step="consult", answer=answer)
        return answer

    def answer(self, answer: str) -> None:
        self._answer = answer
        self._answered.set()

    def cancel(self) -> None:
        self._cancelled.set()
        self._answer = "reject"
        self._answered.set()
        self.emit("cancelled", "ההרצה בוטלה", step="")

    @property
    def cancelled(self) -> bool:
        return self._cancelled.is_set()

    # ------------------------------------------------------------------
    def finish(self, result: dict | None = None, error: str = "") -> None:
        self.result = result
        self.error = error
        self.status = "failed" if error else "done"
        self.finished_at = now()
        self.emit("finished", error or "ההרצה הסתיימה", step="report",
                  status=self.status, error=error)

    def to_dict(self, include_events: bool = False) -> dict:
        payload = {
            "run_id": self.run_id,
            "project_id": self.project_id,
            "status": self.status,
            "options": self.options,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "error": self.error,
            "question": self.question,
            "result": self.result,
            "steps": [{"id": step, "he": he, "en": en} for step, he, en in STEPS],
        }
        if include_events:
            payload["events"] = [event.to_dict() for event in self.events]
        return payload


class RunManager:
    """Holds the runs of this server process."""

    def __init__(self, limit: int = 50):
        self.runs: dict[str, Run] = {}
        self.limit = limit
        self._lock = threading.Lock()

    def create(self, project_id: str, options: dict) -> Run:
        run = Run(uuid.uuid4().hex[:12], project_id, options)
        with self._lock:
            self.runs[run.run_id] = run
            if len(self.runs) > self.limit:
                for old in sorted(self.runs.values(), key=lambda r: r.started_at)[:5]:
                    if old.status in ("done", "failed"):
                        self.runs.pop(old.run_id, None)
        return run

    def get(self, run_id: str) -> Run:
        run = self.runs.get(run_id)
        if run is None:
            raise KeyError(run_id)
        return run

    def list(self) -> list[dict]:
        return [
            {"run_id": run.run_id, "project_id": run.project_id, "status": run.status,
             "started_at": run.started_at, "engine": run.options.get("engine", "pipeline"),
             "mode": run.options.get("mode", "consultation")}
            for run in sorted(self.runs.values(), key=lambda r: r.started_at, reverse=True)
        ]

    def start(self, run: Run, worker: Callable[[Run], None]) -> None:
        def target() -> None:
            run.status = "running"
            try:
                worker(run)
            except Exception as error:  # surfaced in the UI, never swallowed
                run.emit("error", str(error), detail=traceback.format_exc()[-2000:])
                run.finish(error=str(error))

        thread = threading.Thread(target=target, name=f"run-{run.run_id}", daemon=True)
        thread.start()
