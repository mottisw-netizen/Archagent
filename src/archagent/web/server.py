"""The Archagent web application.

A thin API over the agent: projects in, runs out, with the run streaming its
progress to the browser and stopping to ask when a correction needs a human.

Nothing about the safety model changes here - the web layer starts runs and
relays questions; the pipeline still owns every edit, every measurement and
every version.
"""

from __future__ import annotations

import json
import os
import queue
import shutil
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from starlette.datastructures import UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .. import __version__
from ..adapters import SourceRef, default_registry
from ..llm import client as llm_client
from .engines import ClaudeCodeEngine, build_engine
from .projects import ProjectStore
from .runs import RunManager

STATIC = Path(__file__).resolve().parent / "static"
WORKSPACE = Path(os.environ.get("ARCHAGENT_WORKSPACE",
                                Path.home() / ".archagent" / "projects"))
MAX_UPLOAD = 32 * 1024 * 1024

app = FastAPI(title="Archagent", version=__version__, docs_url="/api/docs")
projects = ProjectStore(WORKSPACE)
runs = RunManager()


# ----------------------------------------------------------------------
# status
# ----------------------------------------------------------------------
def connection_status() -> dict:
    """Whether this server can reach the Claude service, and how."""
    key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")
    profile = Path(os.path.expanduser("~/.config/anthropic")).exists()
    claude_code_ok, claude_code_reason = ClaudeCodeEngine.available()
    return {
        "connected": bool(key or profile),
        "source": "api_key" if key else ("profile" if profile else "none"),
        "hint": _mask(key) if key else ("ant auth profile" if profile else ""),
        "model": os.environ.get("ARCHAGENT_MODEL", llm_client.DEFAULT_MODEL),
        "effort": os.environ.get("ARCHAGENT_EFFORT", llm_client.DEFAULT_EFFORT),
        "claude_code": claude_code_ok,
        "claude_code_reason": claude_code_reason,
    }


def _mask(key: str) -> str:
    return f"{key[:7]}…{key[-4:]}" if key and len(key) > 14 else "set"


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "version": __version__, "connection": connection_status(),
            "workspace": str(WORKSPACE)}


@app.post("/api/connect")
async def connect(request: Request) -> dict:
    """Store an API key for this server process only - never written to disk."""
    body = await request.json()
    key = (body.get("api_key") or "").strip()
    if key:
        if not key.startswith("sk-"):
            raise HTTPException(400, "that does not look like an Anthropic API key")
        os.environ["ANTHROPIC_API_KEY"] = key
    else:
        os.environ.pop("ANTHROPIC_API_KEY", None)
    if body.get("model"):
        os.environ["ARCHAGENT_MODEL"] = str(body["model"])
    if body.get("effort"):
        os.environ["ARCHAGENT_EFFORT"] = str(body["effort"])
    return connection_status()


# ----------------------------------------------------------------------
# the CAD host
# ----------------------------------------------------------------------
@app.post("/api/cad")
async def cad_status(request: Request) -> dict:
    """Is a live CAD host reachable, and what does it have open?

    The architect asks this before starting a run: an answer naming their own
    project file is the proof that Archagent is talking to the right document.
    """
    body = await request.json()
    reference = str(body.get("source") or "").strip()
    if not reference:
        return {"available": False, "reason": "no CAD host given"}
    source = SourceRef.parse(reference)
    adapter = default_registry().for_source(source)
    if adapter is None:
        raise HTTPException(400, f"no adapter opens {reference}")
    status = adapter.status(source)
    return {"available": status.available, "adapter": adapter.name,
            "reason": status.reason, "capabilities": list(status.capabilities),
            "disciplines": list(status.disciplines), "detail": status.detail}


# ----------------------------------------------------------------------
# projects
# ----------------------------------------------------------------------
@app.get("/api/projects")
def list_projects() -> dict:
    return {"projects": [project.to_dict() for project in projects.list()]}


@app.post("/api/projects")
async def create_project(request: Request) -> dict:
    form = await request.form()
    name = str(form.get("name") or "פרויקט חדש")
    uploads: list[tuple[str, str, bytes]] = []
    total = 0
    for field, value in form.multi_items():
        if not isinstance(value, UploadFile):
            continue
        content = await value.read()
        total += len(content)
        if total > MAX_UPLOAD:
            raise HTTPException(413, "the upload is larger than 32 MB")
        uploads.append((field, value.filename or "file", content))
    if not uploads:
        raise HTTPException(400, "no files were uploaded")
    return projects.create(name, uploads).to_dict()


@app.delete("/api/projects/{project_id}")
def delete_project(project_id: str) -> dict:
    try:
        projects.delete(project_id)
    except KeyError:
        raise HTTPException(404, "no such project")
    except PermissionError as error:
        raise HTTPException(403, str(error))
    return {"ok": True}


# ----------------------------------------------------------------------
# runs
# ----------------------------------------------------------------------
@app.post("/api/runs")
async def start_run(request: Request) -> dict:
    body = await request.json()
    project_id = body.get("project_id")
    try:
        project_dir = projects.directory(project_id)
    except KeyError:
        raise HTTPException(404, "no such project")

    options = {
        "engine": body.get("engine", "pipeline"),
        "mode": body.get("mode", "consultation"),
        "language": body.get("language", "auto"),
        "effort": body.get("effort"),
        "model": body.get("model"),
        "threshold": body.get("threshold", 0.85),
        "no_llm": bool(body.get("no_llm", False)),
        # Blank: work on the model in the project. "revit://host:port": work on
        # the document the architect has open in Revit.
        "sources": body.get("sources") or body.get("source") or [],
    }
    try:
        engine = build_engine(options["engine"], options)
    except KeyError:
        raise HTTPException(400, "unknown engine")

    run = runs.create(project_id, options)
    runs.start(run, lambda active: engine.run(active, project_dir))
    return run.to_dict()


@app.get("/api/runs")
def list_runs() -> dict:
    return {"runs": runs.list()}


@app.get("/api/runs/{run_id}")
def get_run(run_id: str) -> dict:
    try:
        return runs.get(run_id).to_dict(include_events=True)
    except KeyError:
        raise HTTPException(404, "no such run")


@app.post("/api/runs/{run_id}/answer")
async def answer_run(run_id: str, request: Request) -> dict:
    body = await request.json()
    answer = str(body.get("answer") or "").strip()
    if not answer:
        raise HTTPException(400, "an answer is required")
    try:
        run = runs.get(run_id)
    except KeyError:
        raise HTTPException(404, "no such run")
    if run.question is None:
        raise HTTPException(409, "this run is not waiting for an answer")
    run.answer(answer)
    return {"ok": True}


@app.post("/api/runs/{run_id}/cancel")
def cancel_run(run_id: str) -> dict:
    try:
        runs.get(run_id).cancel()
    except KeyError:
        raise HTTPException(404, "no such run")
    return {"ok": True}


@app.get("/api/runs/{run_id}/events")
def stream_events(run_id: str) -> StreamingResponse:
    try:
        run = runs.get(run_id)
    except KeyError:
        raise HTTPException(404, "no such run")

    def stream():
        channel = run.subscribe()
        try:
            yield _sse("state", run.to_dict())
            while True:
                try:
                    event = channel.get(timeout=15)
                except queue.Empty:
                    yield ": keep-alive\n\n"
                    if run.status in ("done", "failed") :
                        break
                    continue
                yield _sse("event", event.to_dict())
                if event.kind in ("finished", "question", "answer"):
                    yield _sse("state", run.to_dict())
                if event.kind == "finished":
                    break
        finally:
            run.unsubscribe(channel)

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


def _sse(name: str, payload: Any) -> str:
    return f"event: {name}\ndata: {json.dumps(payload, ensure_ascii=False, default=str)}\n\n"


# ----------------------------------------------------------------------
# artefacts
# ----------------------------------------------------------------------
@app.get("/api/runs/{run_id}/file")
def run_file(run_id: str, name: str) -> FileResponse:
    """Serve an artefact of this run, and nothing outside its project."""
    try:
        run = runs.get(run_id)
        project_dir = projects.directory(run.project_id).resolve()
    except KeyError:
        raise HTTPException(404, "no such run")
    paths = (run.result or {}).get("paths", {})
    path = Path(paths.get(name, name)).resolve()
    if not str(path).startswith(str(project_dir)) or not path.is_file():
        raise HTTPException(404, "no such artefact")
    media = {
        ".svg": "image/svg+xml", ".html": "text/html; charset=utf-8",
        ".json": "application/json", ".md": "text/markdown; charset=utf-8",
        ".jsonl": "text/plain; charset=utf-8",
    }.get(path.suffix, "application/octet-stream")
    inline = path.suffix in (".svg", ".html", ".json", ".md", ".jsonl")
    return FileResponse(path, media_type=media, filename=path.name,
                        content_disposition_type="inline" if inline else "attachment")


@app.get("/api/runs/{run_id}/report")
def run_report(run_id: str) -> JSONResponse:
    try:
        run = runs.get(run_id)
    except KeyError:
        raise HTTPException(404, "no such run")
    path = (run.result or {}).get("paths", {}).get("correction_report")
    if not path or not Path(path).is_file():
        raise HTTPException(404, "the report is not ready")
    return JSONResponse({"markdown": Path(path).read_text(encoding="utf-8")})


# ----------------------------------------------------------------------
# the page itself
# ----------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse((STATIC / "index.html").read_text(encoding="utf-8"))


app.mount("/static", StaticFiles(directory=STATIC), name="static")


def main() -> int:  # pragma: no cover - entry point
    import argparse

    import uvicorn

    parser = argparse.ArgumentParser(prog="archagent-web",
                                     description="Archagent web application")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--workspace", default=None, help="where uploaded projects live")
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()
    if args.workspace:
        os.environ["ARCHAGENT_WORKSPACE"] = args.workspace
    if not shutil.which("claude"):
        print("! the claude CLI was not found - the Claude Code engine will be disabled")
    uvicorn.run("archagent.web.server:app" if args.reload else app,
                host=args.host, port=args.port, reload=args.reload)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
