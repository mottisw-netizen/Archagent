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

from .drawing.api import DrawingAPIError, DrawingDriver
from .drawing.json_model import JSONModelDriver
from .ingest import Ingestor
from .models import ChangeRecord, VersionManifest, new_id
from .versioning import VersionStore

VALID_ACTIONS = ("move", "resize", "delete")


class ManualEditError(Exception):
    """A manual edit could not be applied - bad input or a driver failure,
    never silently ignored."""


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


def load_driver_for_edit(project_dir: Path, base_version: str | None = None
                         ) -> tuple[DrawingDriver, str, VersionStore]:
    """The driver to edit, loaded at ``base_version`` (or the latest existing
    version, or the original source if no version has ever been created)."""
    project_dir = Path(project_dir)
    versions = VersionStore(project_dir / "versions")
    existing = versions.versions()

    if base_version == "original":
        return JSONModelDriver.load(_source_model_path(project_dir)), "original", versions
    if base_version is not None:
        if base_version not in existing:
            raise ManualEditError(f"no such version: {base_version!r}")
        return JSONModelDriver.load(versions.model_path(base_version)), base_version, versions
    if existing:
        latest = existing[-1]
        return JSONModelDriver.load(versions.model_path(latest)), latest, versions
    return JSONModelDriver.load(_source_model_path(project_dir)), "original", versions


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
        # audited identically.
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
    versions.create(driver, manifest, [change])
    return ManualEditResult(version=version, parent_version=base_version,
                            change=change, model=driver.plan_model())
