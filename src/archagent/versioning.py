"""Safety and versioning (SKILL.md 16).

Versions are immutable directories.  The original is never opened for write,
a version directory is never rewritten - including a failed one, which is kept
and marked - and rollback means "deliver the parent version", not "undo edits
in place".
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from .audit import AuditLog
from .drawing.api import DrawingDriver
from .models import ChangeRecord, VersionManifest, sha256_file

_VERSION = re.compile(r"^v(?P<number>\d+)$")


class VersionError(RuntimeError):
    pass


@dataclass
class VersionRecord:
    version: str
    directory: Path
    model_path: Path
    manifest_path: Path
    audit_path: Path
    manifest: VersionManifest

    def to_dict(self) -> dict:
        return {"version": self.version, "directory": str(self.directory),
                "model": str(self.model_path), "manifest": self.manifest.to_dict()}


class VersionStore:
    """Immutable version directories under ``<project>/versions``."""

    def __init__(self, root: Path, model_suffix: str = ".json"):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.model_suffix = model_suffix

    # ------------------------------------------------------------------
    def versions(self) -> list[str]:
        found = [p.name for p in self.root.iterdir() if p.is_dir() and _VERSION.match(p.name)]
        return sorted(found, key=lambda name: int(_VERSION.match(name).group("number")))

    def next_version(self) -> str:
        existing = self.versions()
        return f"v{int(_VERSION.match(existing[-1]).group('number')) + 1}" if existing else "v1"

    def directory(self, version: str) -> Path:
        return self.root / version

    def audit_log(self, version: str) -> AuditLog:
        directory = self.directory(version)
        directory.mkdir(parents=True, exist_ok=True)
        return AuditLog(directory / "audit.jsonl")

    # ------------------------------------------------------------------
    def create(self, driver: DrawingDriver, manifest: VersionManifest,
               changes: list[ChangeRecord] | None = None) -> VersionRecord:
        version = manifest.version
        directory = self.directory(version)
        model_path = directory / f"project_{version}{self.model_suffix}"
        if model_path.exists():
            raise VersionError(f"version {version} already exists and is immutable: {model_path}")
        directory.mkdir(parents=True, exist_ok=True)
        driver.save_as(model_path)
        manifest.output_sha256 = sha256_file(model_path)
        manifest.changes = list(changes or [])
        manifest_path = directory / "version.json"
        manifest_path.write_text(manifest.to_json() + "\n", encoding="utf-8")
        return VersionRecord(version, directory, model_path, manifest_path,
                             directory / "audit.jsonl", manifest)

    def snapshot_secondary(self, version: str, adapter_name: str, model: dict) -> dict:
        """A reference snapshot of another live source this run also touched.

        Only the primary architectural source is versioned authoritatively via
        :meth:`create` (SKILL.md 16, ``save_as``): a second live tool - a DWG in
        AutoCAD, say - owns its own document and its own save; Archagent does
        not manage that file's versioning on the tool's behalf. This snapshot
        exists so the change set and a reviewer can see what that source looked
        like at this version without reaching back into the live document.
        """
        directory = self.directory(version)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"project_{version}_{adapter_name}.json"
        path.write_text(json.dumps(model, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return {"adapter": adapter_name, "path": str(path), "sha256": sha256_file(path)}

    def load_manifest(self, version: str) -> VersionManifest:
        path = self.directory(version) / "version.json"
        if not path.exists():
            raise VersionError(f"no manifest for version {version}")
        data = json.loads(path.read_text(encoding="utf-8"))
        data["changes"] = [ChangeRecord(**c) for c in data.get("changes", [])]
        return VersionManifest(**data)

    def model_path(self, version: str) -> Path:
        path = self.directory(version) / f"project_{version}{self.model_suffix}"
        if not path.exists():
            raise VersionError(f"no model saved for version {version}")
        return path

    def rollback_to(self, version: str) -> Path:
        """Rollback is a pointer to the parent version, not an in-place undo."""
        return self.model_path(version)


def verify_original(path: Path, expected_sha256: str) -> bool:
    """The original source file must be byte-identical to its ingest checksum."""
    return sha256_file(path) == expected_sha256
