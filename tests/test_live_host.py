"""The live-CAD path: the wire protocol, the driver, and the mock host.

Everything here runs against a real HTTP server speaking the real protocol, so
it exercises the exact code path that will talk to Revit - the driver, the
serialisation, the error mapping, the batching. Only the far side is swapped.
"""

import json
import re
import shutil
import socket
from pathlib import Path

import pytest

from archagent.drawing import protocol
from archagent.drawing.api import ElementNotFound, NotAuthorised, UnsupportedOperation
from archagent.drawing.json_model import JSONModelDriver
from archagent.drawing.mock_host import MockHost, serve
from archagent.drawing.revit import HostUnavailable, RevitDriver

ADDIN = Path(__file__).resolve().parents[1] / "revit-addin"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture
def host(project, tmp_path):
    """A live host serving a writable copy of the example model."""
    model = tmp_path / "served.json"
    shutil.copyfile(project / "source" / "project.json", model)
    server = serve(model, port=_free_port())
    yield f"http://127.0.0.1:{server.server_address[1]}", model
    server.shutdown()


@pytest.fixture
def live(host):
    driver = RevitDriver(host[0])
    yield driver
    driver.close()


# ----------------------------------------------------------------------
# the two sides of the protocol must not drift apart
# ----------------------------------------------------------------------
def _python_endpoints() -> list[str]:
    """Every endpoint the protocol module declares, found rather than listed."""
    return [value for name, value in vars(protocol).items()
            if name.isupper() and isinstance(value, str) and value.startswith("/")]


def _csharp_constants() -> dict[str, str]:
    source = (ADDIN / "src" / "Protocol.cs").read_text(encoding="utf-8")
    return dict(re.findall(r'public const string (\w+)\s*=\s*"([^"]*)";', source))


def test_the_addin_and_the_python_protocol_agree():
    """A rename on one side that is not mirrored on the other is a silent break."""
    constants = _csharp_constants()
    assert constants["Version"] == protocol.PROTOCOL_VERSION
    csharp = set(constants.values())
    # Derived, not listed: an endpoint added to the protocol must reach the
    # add-in, and this test has to fail until it does.
    for endpoint in _python_endpoints():
        assert endpoint in csharp, f"the add-in does not know the endpoint {endpoint}"
    for action in protocol.ACTIONS:
        assert action in csharp, f"the add-in does not know the action {action}"
    for code in (protocol.ERR_NOT_FOUND, protocol.ERR_AMBIGUOUS, protocol.ERR_UNSUPPORTED,
                 protocol.ERR_NO_TRANSACTION, protocol.ERR_READ_ONLY, protocol.ERR_HOST,
                 protocol.ERR_MEASUREMENT, protocol.ERR_BUSY):
        assert code in csharp, f"the add-in does not know the error code {code}"


def test_the_addin_routes_every_endpoint_it_declares():
    """Declaring a constant is not implementing it."""
    router = (ADDIN / "src" / "HostServer.cs").read_text(encoding="utf-8")
    endpoints = set(_python_endpoints())
    for name, value in _csharp_constants().items():
        if value in endpoints:
            assert f"case Protocol.{name}:" in router, f"HostServer does not route {name}"


def test_only_the_apply_command_opens_a_transaction():
    """The single-writer invariant, enforced in C# and not only in the caller."""
    for path in sorted((ADDIN / "src").rglob("*.cs")):
        if path.name == "ApplyCommand.cs":
            continue
        body = path.read_text(encoding="utf-8")
        assert "new Transaction(" not in body, f"{path.name} opens a transaction"


# ----------------------------------------------------------------------
# the driver against a live host
# ----------------------------------------------------------------------
def test_a_closed_host_is_a_clear_error_not_a_stack_trace():
    driver = RevitDriver(f"http://127.0.0.1:{_free_port()}")
    with pytest.raises(HostUnavailable) as error:
        driver.info()
    assert "Revit" in str(error.value)


def test_health_reports_a_compatible_protocol(live):
    info = live.info()
    assert info.compatible() and info.element_count > 0


def test_the_driver_reads_the_same_elements_the_file_driver_does(live, project):
    reference = JSONModelDriver.load(project / "source" / "project.json")
    assert {element["id"] for element in live.elements()} == \
           {element["id"] for element in reference.elements()}


def test_mutation_without_an_approved_plan_is_refused(live):
    with pytest.raises(NotAuthorised):
        live.resize_element("parking_p11", "width", 2.5)


def test_a_plan_reaches_the_host_as_one_batch(live, host):
    """Two actions, one round trip: Revit cannot hold a transaction open."""
    before = live.get_element("parking_p11")["geometry"]["w"]
    with live.authorised("PLAN-1"):
        first = live.resize_element("parking_p11", "width", 2.5)
        live.resize_element("parking_p12", "width", 2.5)
        assert len(live._pending) == 2          # still buffered, nothing sent
        assert live.get_element("parking_p11")["geometry"]["w"] == before
    assert (first.before, first.after) == (before, 2.5)
    assert live.get_element("parking_p11")["geometry"]["w"] == 2.5


def test_a_failing_action_rolls_the_whole_plan_back(live):
    before = live.get_element("parking_p11")["geometry"]["w"]
    with pytest.raises(ElementNotFound):
        with live.authorised("PLAN-2"):
            live.resize_element("parking_p11", "width", 2.9)
            live.resize_element("ghost", "width", 2.9)
    assert live.get_element("parking_p11")["geometry"]["w"] == before


def test_the_sandbox_never_writes_to_the_open_document(live):
    before = live.get_element("parking_p11")["geometry"]["w"]
    with live.sandbox() as sandbox:
        with sandbox.authorised("PLAN-3"):
            sandbox.resize_element("parking_p11", "width", 9.0)
        assert sandbox.get_element("parking_p11")["geometry"]["w"] == 9.0
    assert live.get_element("parking_p11")["geometry"]["w"] == before


def test_the_snapshot_carries_what_the_planner_needs(live):
    """Schedules and sheets, not only geometry - a plan may update a table."""
    model = live.plan_model()
    assert model["elements"] and model["schedules"] and model["sheets"]


def test_measurements_the_host_cannot_do_are_computed_here(live):
    """The host answers `unsupported`; the driver falls back to geometry."""
    measurement = live.measure({"selector": {"id": "parking_p11"}}, "width")
    assert measurement.value == pytest.approx(2.4, abs=0.05)
    assert live.measure({"selector": {"type": "parking"}}, "count").value >= 2


def test_an_unknown_action_is_refused_rather_than_ignored(live):
    with pytest.raises(UnsupportedOperation):
        live._call(protocol.APPLY, {"plan_id": "PLAN-4", "actions": [{"action": "explode"}]})


def test_the_addin_refuses_to_hold_a_transaction_between_requests():
    """Revit cannot; saying so beats pretending, which would corrupt a plan."""
    router = (ADDIN / "src" / "HostServer.cs").read_text(encoding="utf-8")
    block = router.split("case Protocol.Begin:")[1][:600]
    assert "Unsupported" in block


def test_a_read_only_host_refuses_to_be_written(project, tmp_path):
    model = tmp_path / "read_only.json"
    shutil.copyfile(project / "source" / "project.json", model)
    server = serve(model, port=_free_port(), read_only=True)
    driver = RevitDriver(f"http://127.0.0.1:{server.server_address[1]}")
    try:
        assert driver.read_only
        with pytest.raises(NotAuthorised):
            with driver.authorised("PLAN-5"):
                driver.resize_element("parking_p11", "width", 2.5)
    finally:
        driver.close()
        server.shutdown()


def test_a_token_is_required_when_the_host_asks_for_one(project, tmp_path):
    model = tmp_path / "guarded.json"
    shutil.copyfile(project / "source" / "project.json", model)
    server = serve(model, port=_free_port(), token="s3cret")
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        with pytest.raises(Exception):
            RevitDriver(base).info()
        assert RevitDriver(base, token="s3cret").info().compatible()
    finally:
        server.shutdown()


def test_save_as_refuses_to_overwrite_the_open_document(host):
    """The architect's file is never the target of a write."""
    base, model = host
    driver = RevitDriver(base)
    with pytest.raises(Exception):
        driver.save_as(str(model))
    assert driver.save_as(str(model.with_name("v2.json")))


# ----------------------------------------------------------------------
# the host itself
# ----------------------------------------------------------------------
def test_the_batch_is_all_or_nothing_inside_the_host(project, tmp_path):
    model = tmp_path / "batch.json"
    shutil.copyfile(project / "source" / "project.json", model)
    host = MockHost(model)
    before = host.driver.get_element("parking_p11")["geometry"]["w"]
    with pytest.raises(ElementNotFound):
        host.handle(protocol.APPLY, {"plan_id": "PLAN-6", "actions": [
            {"action": protocol.RESIZE, "id": "parking_p11", "parameter": "width", "value": 2.9},
            {"action": protocol.RESIZE, "id": "ghost", "parameter": "width", "value": 2.9},
        ]})
    assert host.driver.get_element("parking_p11")["geometry"]["w"] == before


# ----------------------------------------------------------------------
# the whole pipeline, against a live host
# ----------------------------------------------------------------------
def _summary(result):
    return (result.validation.result,
            sorted((item.comment_id, item.status.value) for item in result.validation.comments),
            sorted((change.element_id, change.tool, change.after) for change in result.changes))


def test_a_live_host_run_matches_the_file_run(project, tmp_path):
    """The host is a different door to the same model, not a different answer."""
    from archagent.consult import ScriptedResponder
    from archagent.orchestrator import Orchestrator

    answers = {"C-005": "approve"}
    on_file = Orchestrator(project, responder=ScriptedResponder(answers),
                           output_dir=tmp_path / "file").run()

    served = tmp_path / "served.json"
    shutil.copyfile(project / "source" / "project.json", served)
    server = serve(served, port=_free_port())
    try:
        live = Orchestrator(project, responder=ScriptedResponder(answers),
                            output_dir=tmp_path / "live",
                            sources=[f"revit://127.0.0.1:{server.server_address[1]}"]).run()
    finally:
        server.shutdown()

    assert _summary(live) == _summary(on_file)
    assert live.context.source_format == "REVIT"


def test_a_live_run_edits_the_open_document_and_leaves_a_version(project, tmp_path):
    """The document in the host is changed; the file on disk is the user's to save."""
    from archagent.consult import ScriptedResponder
    from archagent.orchestrator import Orchestrator

    served = tmp_path / "served.json"
    shutil.copyfile(project / "source" / "project.json", served)
    server = serve(served, port=_free_port())
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        result = Orchestrator(project, responder=ScriptedResponder({"C-005": "approve"}),
                              output_dir=tmp_path / "out",
                              sources=[f"revit://127.0.0.1:{server.server_address[1]}"]).run()
        assert result.changes and result.version
        inspector = RevitDriver(base)
        assert inspector.get_element("parking_p12")["geometry"]["w"] == 2.5
        inspector.close()
    finally:
        server.shutdown()

    # The architect's own file was never written behind their back.
    assert json.loads(served.read_text(encoding="utf-8"))["elements"][2]["geometry"]["w"] == 2.4
    assert (project / "versions").exists()


def test_an_unreachable_host_is_an_open_item_not_a_crash(project, tmp_path):
    from archagent.orchestrator import Orchestrator

    result = Orchestrator(project, output_dir=tmp_path / "out",
                          sources=[f"revit://127.0.0.1:{_free_port()}"]).run()
    reasons = " ".join(str(item.get("why", "")) for item in result.context.open_items)
    assert "Revit" in reasons and "add-in" in reasons
    # Falling back to the file model would be worse than stopping: the run says
    # markup only rather than quietly editing something the user did not name.
    assert result.context.execution_mode == "markup_only"
