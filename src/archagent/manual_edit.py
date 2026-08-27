"""Direct manual editing of a project's model - move / resize / delete.

The Web Editor's comment-driven pipeline already moves, resizes, and deletes
elements through :class:`~archagent.drawing.api.DrawingDriver` - that is
exactly what :class:`~archagent.execute.ExecutionAgent` calls when a
correction plan runs. This module is a second, parallel control surface onto
the *same* primitives, triggered directly by a human decision instead of a
municipal comment: every edit still goes through the same safety rails as a
full run - the original source is never touched, each edit becomes a new
immutable version with its own manifest, and the change is recorded exactly
like any other :class:`~archagent.models.ChangeRecord`.

Scope, stated plainly: this operates on the project's own JSON model file (or
a JSON-format version snapshot already saved under ``versions/``) via
:class:`~archagent.drawing.json_model.JSONModelDriver` - the same file every
example/demo project in this repository already uses. It does not reach into
a live Revit/AutoCAD session; editing a live CAD document still goes through
that tool's own add-in, as documented in SKILL.md §12.3.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .audit import AuditLog
from .drawing.api import DrawingAPIError, DrawingDriver
from .drawing.json_model import JSONModelDriver
from .ingest import Ingestor
from .models import ChangeRecord, VersionManifest, new_id
from .versioning import VersionError, VersionStore

VALID_ACTIONS = ("move", "resize", "delete")

#: The version label meaning "before any version was ever saved" - the
#: project's own ingested source model.
ORIGINAL = "original"


class ManualEditError(Exception):
    """A manual edit could not be applied - bad input, an unreadable version,
    or a driver failure. Every failure this module can produce is raised as
    this one type, so a caller (the web layer included) never has to catch a
    ``VersionError`` or a ``DrawingAPIError`` leaking out of it.
    """


@dataclass
class ManualEditResult:
    version: str
    parent_version: str
    change: ChangeRecord
    model: dict


def _source_model_path(project_dir: Path) -> Path:
    manifest = Ingestor(project_dir).scan()
    for entry in manifest:
        if entry.role == "source_model" and entry.read_status == "ok" and entry.file.endswith(".json"):
            return Path(entry.file)
    raise ManualEditError("no JSON source model was found for this project")


def list_versions(project_dir: Path) -> list[str]:
    """Every editable version of this project, oldest first, starting with
    ``"original"``.

    Read-only on purpose: unlike :class:`~archagent.versioning.VersionStore`,
    which creates its root directory on construction, merely *listing* a
    project's versions must not write anything into it - a browser opening
    the editor should never leave a ``versions/`` directory behind in a
    project it did not edit (the bundled ``examples/`` tree especially).
    """
    root = Path(project_dir) / "versions"
    if not root.is_dir():
        return [ORIGINAL]
    return [ORIGINAL] + VersionStore(root).versions()


def _load_version(versions: VersionStore, version: str) -> DrawingDriver:
    try:
        path = versions.model_path(version)
    except VersionError as error:
        # A run that versioned a DXF/DWG project saved project_v1.dxf, so the
        # .json VersionStore looks for is absent. Name the format actually
        # found rather than reporting a bare "no model saved" (manual editing
        # is JSON-model only - see the module docstring).
        saved = sorted(versions.directory(version).glob(f"project_{version}.*"))
        if saved:
            raise ManualEditError(
                f"version {version} was saved as {saved[0].suffix} - manual editing "
                "supports JSON model projects only") from error
        raise ManualEditError(str(error)) from error
    return JSONModelDriver.load(path)


def load_driver_for_edit(project_dir: Path, base_version: str | None = None
                         ) -> tuple[DrawingDriver, str, VersionStore]:
    """The driver to edit, loaded at ``base_version`` (or the latest existing
    version, or the original source if no version has ever been created)."""
    project_dir = Path(project_dir)
    versions = VersionStore(project_dir / "versions")
    existing = versions.versions()

    if base_version == ORIGINAL:
        return JSONModelDriver.load(_source_model_path(project_dir)), ORIGINAL, versions
    if base_version is not None:
        if base_version not in existing:
            raise ManualEditError(f"no such version: {base_version!r}")
        return _load_version(versions, base_version), base_version, versions
    if existing:
        latest = existing[-1]
        return _load_version(versions, latest), latest, versions
    return JSONModelDriver.load(_source_model_path(project_dir)), ORIGINAL, versions


def apply_manual_edit(versions: VersionStore, driver: DrawingDriver, base_version: str,
                      action: str, element_id: str, **params) -> ManualEditResult:
    """Apply one move/resize/delete to ``driver`` (already loaded at
    ``base_version``) and save the result as a new immutable version whose
    parent is ``base_version`` - never a rewrite of an existing one."""
    if action not in VALID_ACTIONS:
        raise ManualEditError(f"unknown manual edit action: {action!r}")
    plan_id = new_id("MANUAL")
    try:
        # A manual edit skips the simulate-before-mutate scaffolding built
        # for AI-proposed corrections (SKILL.md §9.1) on purpose: a human is
        # deciding this action directly, right now, not the agent proposing
        # one for review. It still only reaches the model through the same
        # `authorised` gate every other mutation does, and is versioned and
        # audited the same way.
        with driver.authorised(plan_id):
            if action == "move":
                change = driver.move_element(element_id, params["distance"], params["direction"])
            elif action == "resize":
                change = driver.resize_element(element_id, params["parameter"], params["value"],
                                               params.get("anchor", ""))
            else:
                change = driver.delete_element(element_id)
    except DrawingAPIError as error:
        raise ManualEditError(str(error)) from error
    except KeyError as error:
        raise ManualEditError(f"missing parameter: {error}") from error
    change.plan_id = plan_id

    version = versions.next_version()
    manifest = VersionManifest(
        version=version, parent_version=base_version, operating_mode="manual_edit",
        validation_result="not_evaluated",
    )
    try:
        record = versions.create(driver, manifest, [change])
    except VersionError as error:
        # Two edits racing for the same next_version(), or a version
        # directory that already exists - never silently overwrite one.
        raise ManualEditError(str(error)) from error

    audit = AuditLog(record.audit_path)
    audit.write("manual_edit", "api_call", plan_id=plan_id, tool=change.tool,
                result="ok", before=change.before, after=change.after,
                params={"element_id": change.element_id, "property": change.property,
                        "action": action, "base_version": base_version})
    return ManualEditResult(version=version, parent_version=base_version,
                            change=change, model=driver.plan_model())
