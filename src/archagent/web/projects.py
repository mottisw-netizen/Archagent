"""Projects the web application can run: the bundled examples and uploads."""

from __future__ import annotations

import re
import shutil
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from ..ingest import Ingestor
from ..lang import detect_script

#: Where the demo projects live inside the repository.
EXAMPLES = Path(__file__).resolve().parents[3] / "examples"

ROLE_DIRECTORY = {
    "source_model": "source",
    "municipal_comments": "municipal_comments",
    "constraint": "constraints",
    "previous_version": "previous_versions",
    "reference": "reference",
}

SAFE_NAME = re.compile(r"[^\w.\-]+", re.UNICODE)


def safe_filename(name: str) -> str:
    """A filename that cannot escape its directory, keeping Hebrew intact."""
    name = unicodedata.normalize("NFC", Path(name).name)
    cleaned = SAFE_NAME.sub("_", name).strip("._") or "file"
    return cleaned[:120]


@dataclass
class ProjectSummary:
    project_id: str
    name: str
    kind: str            # example | upload
    path: str
    language: str
    comments: int
    has_model: bool
    files: list[dict]

    def to_dict(self) -> dict:
        return {
            "project_id": self.project_id, "name": self.name, "kind": self.kind,
            "language": self.language, "comments": self.comments,
            "has_model": self.has_model, "files": self.files,
        }


class ProjectStore:
    """The bundled examples plus whatever the user uploads."""

    def __init__(self, workspace: Path):
        self.workspace = Path(workspace)
        self.workspace.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    def directory(self, project_id: str) -> Path:
        if project_id.startswith("example:"):
            name = safe_filename(project_id.split(":", 1)[1])
            path = EXAMPLES / name
            if not (path / "source").exists() and not (path / "municipal_comments").exists():
                raise KeyError(project_id)
            return path
        path = self.workspace / safe_filename(project_id)
        if not path.exists():
            raise KeyError(project_id)
        return path

    def list(self) -> list[ProjectSummary]:
        found = []
        if EXAMPLES.exists():
            for path in sorted(EXAMPLES.iterdir()):
                if path.is_dir() and (path / "municipal_comments").exists():
                    found.append(self.describe(f"example:{path.name}", path, "example"))
        for path in sorted(self.workspace.iterdir()):
            if path.is_dir():
                found.append(self.describe(path.name, path, "upload"))
        return found

    def describe(self, project_id: str, path: Path, kind: str) -> ProjectSummary:
        ingestor = Ingestor(path)
        manifest = ingestor.scan()
        text = " ".join(ingestor.text_of(entry) for entry in manifest
                        if entry.role == "municipal_comments")[:4000]
        comments = sum(1 for line in text.splitlines()
                       if re.match(r"^\s*(?:[A-Z]{1,3}-\d+|\d{1,3})\s*[.):\-]", line.strip()))
        return ProjectSummary(
            project_id=project_id,
            name=_display_name(path),
            kind=kind,
            path=str(path),
            language=detect_script(text) if text.strip() else "en",
            comments=comments,
            has_model=any(entry.role == "source_model" and entry.read_status == "ok"
                          for entry in manifest),
            files=[{"name": Path(entry.file).name, "role": entry.role,
                    "status": entry.read_status, "format": entry.format}
                   for entry in manifest],
        )

    # ------------------------------------------------------------------
    def create(self, name: str, uploads: list[tuple[str, str, bytes]]) -> ProjectSummary:
        """Store an uploaded project. *uploads* is (role, filename, content)."""
        project_id = _unique_id(self.workspace, name)
        root = self.workspace / project_id
        for directory in set(ROLE_DIRECTORY.values()):
            (root / directory).mkdir(parents=True, exist_ok=True)
        for role, filename, content in uploads:
            directory = ROLE_DIRECTORY.get(role, "reference")
            (root / directory / safe_filename(filename)).write_bytes(content)
        return self.describe(project_id, root, "upload")

    def delete(self, project_id: str) -> None:
        if project_id.startswith("example:"):
            raise PermissionError("the bundled examples cannot be deleted")
        shutil.rmtree(self.directory(project_id), ignore_errors=True)


def _display_name(path: Path) -> str:
    names = {"project": "פרויקט לדוגמה (אנגלית)", "project_he": "פרויקט לדוגמה (עברית)"}
    return names.get(path.name, path.name.replace("_", " "))


def _unique_id(workspace: Path, name: str) -> str:
    base = safe_filename(name) or "project"
    candidate = base
    index = 2
    while (workspace / candidate).exists():
        candidate = f"{base}-{index}"
        index += 1
    return candidate
