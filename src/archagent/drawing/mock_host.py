"""A host that speaks the Revit protocol without Revit.

It exists for three reasons, all of them practical:

1. The pipeline, the web app and the tests can exercise the *live-host* code
   path - transactions, rollback, simulation-by-rollback - on any machine.
2. The C# add-in has an executable specification to match: whatever this host
   answers, Revit must answer.
3. A demo runs without a Revit licence.

It is not a CAD engine: it serves a JSON model, the same one the file driver
uses. Anything geometric it gets right is arithmetic, not Revit.
"""

from __future__ import annotations

import copy
import json
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from ..models import Measurement
from . import protocol
from .api import AmbiguousElement, DrawingAPIError, ElementNotFound, UnsupportedOperation
from .json_model import JSONModelDriver

HOST_NAME = "mock"


class MockHost:
    """The protocol, implemented over a JSON model."""

    def __init__(self, model_path: Path | str, read_only: bool = False):
        self.model_path = Path(model_path)
        self.driver = JSONModelDriver.load(self.model_path)
        self.read_only = read_only
        self.highlighted: list[str] = []
        self.transactions: dict[str, dict] = {}
        self.changes: dict[str, list[dict]] = {}
        self.lock = threading.Lock()

    # ------------------------------------------------------------------
    def handle(self, endpoint: str, payload: dict) -> dict:
        handler = getattr(self, f"_do_{endpoint.strip('/').replace('/', '_')}", None)
        if handler is None:
            raise UnsupportedOperation(f"unknown endpoint: {endpoint}")
        with self.lock:
            return handler(payload)

    # ------------------------------------------------------------------
    # read
    # ------------------------------------------------------------------
    def _do_health(self, payload: dict) -> dict:
        return {
            "protocol": protocol.PROTOCOL_VERSION,
            "host": HOST_NAME,
            "host_version": "1.0",
            "document": self.model_path.name,
            "units": protocol.UNIT_LENGTH,
            "read_only": self.read_only,
            "project_north": 0.0,
            "element_count": len(self.driver.elements()),
        }

    def _do_find(self, payload: dict) -> dict:
        filters = payload.get("filter") or {}
        ids = self.driver.find_element(**filters)
        if payload.get("detail") == "full":
            return {"elements": [self._element(element_id) for element_id in ids]}
        return {"elements": ids}

    def _do_element(self, payload: dict) -> dict:
        return self._element(payload["id"])

    def _element(self, element_id: str) -> dict:
        element = self.driver.get_element(element_id)
        geometry = self.driver.get_element_geometry(element_id)
        properties = dict(element.get("properties", {}))
        return {
            "id": element["id"],
            "category": element.get("type", "generic"),
            "type_name": properties.get("type_name", element.get("type", "")),
            "name": element.get("label", element["id"]),
            "label": element.get("label", ""),
            "level": element.get("level", ""),
            "sheet": element.get("sheet", ""),
            "geometry": {"bbox": geometry["bbox"],
                         "elevation": float(properties.get("elevation", 0.0)),
                         "height": float(properties.get("height", 0.0)),
                         "rotation": float(properties.get("rotation", 0.0))},
            "properties": properties,
            "editable": not properties.get("pinned", False),
            "pinned": bool(properties.get("pinned", False)),
            "workset": properties.get("workset", ""),
        }

    def _do_geometry(self, payload: dict) -> dict:
        return self.driver.get_element_geometry(payload["id"])

    def _do_properties(self, payload: dict) -> dict:
        return {"properties": self.driver.get_element_properties(payload["id"])}

    def _do_sheets(self, payload: dict) -> dict:
        return {"sheets": self.driver.sheets(), "schedules": self.driver.schedules()}

    def _do_measure(self, payload: dict) -> dict:
        measurement: Measurement = self.driver.measure(
            payload["subject"], payload["metric"], payload.get("basis", "clear"))
        return {"value": measurement.value, "unit": measurement.unit,
                "basis": measurement.basis, "tool": f"{HOST_NAME}:{measurement.tool}",
                "details": measurement.details}

    def _do_distance(self, payload: dict) -> dict:
        return {"value": self.driver.calculate_distance(
            payload["a"], payload["b"], payload.get("mode", "clear"))}

    def _do_overlap(self, payload: dict) -> dict:
        return self.driver.check_overlap(payload["a"], payload["b"])

    def _do_clearance(self, payload: dict) -> dict:
        return self.driver.check_clearance(payload["id"], payload.get("against", []),
                                           float(payload.get("required", 0.0)))

    def _do_changes(self, payload: dict) -> dict:
        transaction = payload.get("transaction", "")
        if transaction:
            return {"changes": self.changes.get(transaction, [])}
        return {"changes": [change for records in self.changes.values() for change in records]}

    # ------------------------------------------------------------------
    # transactions
    # ------------------------------------------------------------------
    def _do_transaction_begin(self, payload: dict) -> dict:
        if self.read_only and not payload.get("simulation"):
            raise DrawingAPIError(protocol.ERR_READ_ONLY)
        transaction = uuid.uuid4().hex[:12]
        self.transactions[transaction] = {
            "plan_id": payload.get("plan_id", ""),
            "simulation": bool(payload.get("simulation")),
            "snapshot": copy.deepcopy(self.driver.model),
        }
        self.changes[transaction] = []
        return {"transaction": transaction, "plan_id": payload.get("plan_id", "")}

    def _do_transaction_commit(self, payload: dict) -> dict:
        transaction = self._transaction(payload)
        state = self.transactions.pop(transaction)
        if state["simulation"]:
            # A simulation never keeps its work, even if the caller commits.
            self.driver.restore(state["snapshot"])
            return {"committed": False, "rolled_back": True, "reason": "simulation"}
        return {"committed": True, "changes": len(self.changes.get(transaction, []))}

    def _do_transaction_rollback(self, payload: dict) -> dict:
        transaction = self._transaction(payload)
        state = self.transactions.pop(transaction)
        self.driver.restore(state["snapshot"])
        return {"rolled_back": True}

    def _transaction(self, payload: dict) -> str:
        transaction = payload.get("transaction", "")
        if transaction not in self.transactions:
            raise DrawingAPIError(protocol.ERR_NO_TRANSACTION)
        return transaction

    # ------------------------------------------------------------------
    # write
    # ------------------------------------------------------------------
    def _do_apply(self, payload: dict) -> dict:
        """One action inside an open transaction, or a whole plan in one call.

        The batch form is what a Revit host implements, because Revit cannot
        hold a transaction open between requests: the host opens one transaction
        group, applies every action, and rolls the group back if any of them
        fails.
        """
        if "actions" in payload:
            return self._apply_batch(payload)
        transaction = self._transaction(payload)
        action = payload.get("action")
        if action not in protocol.ACTIONS:
            raise UnsupportedOperation(f"unsupported action: {action!r}")
        with self.driver.authorised(self.transactions[transaction]["plan_id"] or "plan"):
            record = self._perform(action, payload)
        entry = record.to_dict()
        self.changes[transaction].append(entry)
        return entry

    def _apply_batch(self, payload: dict) -> dict:
        if self.read_only:
            raise DrawingAPIError(protocol.ERR_READ_ONLY)
        plan_id = payload.get("plan_id") or "plan"
        snapshot = copy.deepcopy(self.driver.model)
        changes: list[dict] = []
        try:
            with self.driver.authorised(plan_id):
                for index, action in enumerate(payload.get("actions", [])):
                    name = action.get("action")
                    if name not in protocol.ACTIONS:
                        raise UnsupportedOperation(f"unsupported action: {name!r}")
                    changes.append(self._perform(name, action).to_dict())
        except Exception:
            self.driver.restore(snapshot)   # all or nothing, like a transaction group
            raise
        self.changes[plan_id] = changes
        return {"plan_id": plan_id, "changes": changes, "committed": True}

    def _perform(self, action: str, payload: dict):
        driver = self.driver
        if action == protocol.MOVE:
            return driver.move_element(payload["id"], float(payload["distance"]),
                                       payload["direction"])
        if action == protocol.RESIZE:
            return driver.resize_element(payload["id"], payload["parameter"],
                                         float(payload["value"]), payload.get("anchor", ""))
        if action == protocol.ROTATE:
            return driver.rotate_element(payload["id"], float(payload["angle"]),
                                         payload.get("pivot", "centre"))
        if action == protocol.DELETE:
            return driver.delete_element(payload["id"])
        if action == protocol.CREATE:
            return driver.create_element(payload["type"], payload["geometry"],
                                         payload.get("properties", {}))
        if action == protocol.SET_TEXT:
            return driver.update_text(payload["id"], payload.get("text", ""))
        if action == protocol.UPDATE_DIMENSION:
            value = payload.get("value")
            return driver.update_dimension(payload["id"],
                                           None if value is None else float(value),
                                           bool(payload.get("recompute", value is None)))
        if action == protocol.UPDATE_SCHEDULE:
            return driver.update_schedule(payload["id"], bool(payload.get("recompute", True)))
        if action == protocol.SET_PARAMETER:
            element = driver._element(payload["id"])
            before = element.setdefault("properties", {}).get(payload["parameter"])
            element["properties"][payload["parameter"]] = payload.get("value")
            from ..models import ChangeRecord
            return ChangeRecord(element_id=payload["id"], property=payload["parameter"],
                                before=before, after=payload.get("value"),
                                tool="set_parameter", sheet=element.get("sheet", ""))
        raise UnsupportedOperation(action)

    def _do_highlight(self, payload: dict) -> dict:
        """A real host selects the elements; this one records what it was asked.

        Unknown ids are reported rather than raised: a diff naming an element
        that has since been deleted should still highlight the rest.
        """
        known = {element["id"] for element in self.driver.elements()}
        requested = [str(value) for value in payload.get("ids", [])]
        self.highlighted = [value for value in requested if value in known]
        return {"selected": len(self.highlighted),
                "unknown": [value for value in requested if value not in known]}

    def _do_export(self, payload: dict) -> dict:
        """A real host renders a view; this one writes the model it would render."""
        path = Path(payload.get("path") or (self.model_path.parent / "export.json"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"view": payload.get("view", ""),
                                    "highlight": payload.get("highlight", []),
                                    "elements": self.driver.elements()},
                                   ensure_ascii=False, indent=2), encoding="utf-8")
        return {"path": str(path), "format": payload.get("format", "json")}

    def _do_save_as(self, payload: dict) -> dict:
        path = Path(payload.get("path") or "")
        if not str(path):
            raise UnsupportedOperation("save_as needs a path")
        # The same rule the Revit host enforces: a version is a new file, and
        # the document the architect has open is never the target of a write.
        if path.resolve() == self.model_path.resolve():
            raise UnsupportedOperation(
                "refusing to overwrite the open document; a version is a new file")
        return {"path": self.driver.save_as(path)}


# ----------------------------------------------------------------------
class _Handler(BaseHTTPRequestHandler):
    server_version = "ArchagentMockHost/1.0"
    host: MockHost = None  # type: ignore[assignment]
    token: str = ""

    def do_POST(self) -> None:  # noqa: N802 - http.server's interface
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        if self.token and self.headers.get("X-Archagent-Token") != self.token:
            return self._send(403, {"error": protocol.ERR_HOST, "message": "bad token"})
        try:
            payload = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError as error:
            return self._send(400, {"error": protocol.ERR_HOST, "message": str(error)})
        try:
            return self._send(200, self.host.handle(self.path, payload))
        except ElementNotFound as error:
            return self._send(404, {"error": protocol.ERR_NOT_FOUND, "message": str(error)})
        except AmbiguousElement as error:
            return self._send(409, {"error": protocol.ERR_AMBIGUOUS, "message": str(error),
                                    "candidates": error.candidates})
        except UnsupportedOperation as error:
            return self._send(400, {"error": protocol.ERR_UNSUPPORTED, "message": str(error)})
        except DrawingAPIError as error:
            code = str(error) if str(error) in (protocol.ERR_NO_TRANSACTION,
                                                protocol.ERR_READ_ONLY) else protocol.ERR_HOST
            return self._send(400, {"error": code, "message": str(error)})
        except Exception as error:  # a host bug must not look like a clean answer
            return self._send(500, {"error": protocol.ERR_HOST, "message": repr(error)})

    def do_GET(self) -> None:  # noqa: N802
        self.do_POST()

    def _send(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args) -> None:  # quiet by default
        pass


def serve(model_path, host: str = "127.0.0.1", port: int = 8735, token: str = "",
          read_only: bool = False) -> ThreadingHTTPServer:
    """Start the mock host; returns the server so a caller can shut it down."""
    handler = type("Handler", (_Handler,),
                   {"host": MockHost(model_path, read_only=read_only), "token": token})
    server = ThreadingHTTPServer((host, port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True,
                              name=f"mock-host-{port}")
    thread.start()
    return server


def main() -> int:  # pragma: no cover - entry point
    import argparse

    parser = argparse.ArgumentParser(
        prog="archagent-host",
        description="Serve a JSON model over the Archagent CAD host protocol")
    parser.add_argument("model", help="path to the JSON model")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8735)
    parser.add_argument("--token", default="", help="require this X-Archagent-Token header")
    parser.add_argument("--read-only", action="store_true")
    args = parser.parse_args()
    server = serve(args.model, args.host, args.port, args.token, args.read_only)
    print(f"mock host serving {args.model} on http://{args.host}:{args.port} "
          f"(protocol {protocol.PROTOCOL_VERSION})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
