"""Step 1 - Ingest (SKILL.md 5.1) and the input manifest (3.2).

Every file is recorded with its role, format, checksum and read status before
anything else happens.  A file that could not be read is never silently
dropped: it is carried into the report as an open item.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Callable

from .models import InputFile, sha256_file

ROLE_BY_DIRECTORY = {
    "source": "source_model",
    "municipal_comments": "municipal_comments",
    "comments": "municipal_comments",
    "constraints": "constraint",
    "previous_versions": "previous_version",
    "reference": "reference",
}

TEXT_SUFFIXES = {".txt", ".md", ".json", ".csv"}
MODEL_SUFFIXES = {".json", ".dwg", ".rvt", ".ifc"}

#: Optional hook: set to a callable ``(path) -> str`` to plug in a PDF text
#: extractor (pdfminer, PyMuPDF, an OCR service).  When unset the ingester
#: falls back to the ``pdftotext`` binary, and reports the file as unreadable
#: if neither is available - it never guesses a comment's content.
PDF_TEXT_EXTRACTOR: Callable[[Path], str] | None = None


class IngestError(RuntimeError):
    pass


def detect_role(path: Path, root: Path) -> str:
    try:
        relative = path.relative_to(root)
    except ValueError:
        relative = path
    for part in relative.parts[:-1]:
        if part in ROLE_BY_DIRECTORY:
            return ROLE_BY_DIRECTORY[part]
    name = path.name.casefold()
    if "comment" in name:
        return "municipal_comments"
    if any(word in name for word in ("zoning", "constraint", "requirement")):
        return "constraint"
    if path.suffix.casefold() in MODEL_SUFFIXES:
        return "source_model"
    return "reference"


def extract_pdf_text(path: Path) -> tuple[str, str]:
    """Return ``(text, status)`` for a PDF, without ever inventing content."""
    if PDF_TEXT_EXTRACTOR is not None:
        try:
            return PDF_TEXT_EXTRACTOR(path), "ok"
        except Exception as error:  # pragma: no cover - depends on the hook
            return "", f"unreadable: extractor failed ({error})"
    if shutil.which("pdftotext"):
        try:
            output = subprocess.run(
                ["pdftotext", "-layout", str(path), "-"],
                capture_output=True, text=True, timeout=120, check=True,
            )
            text = output.stdout.strip()
            return (text, "ok") if text else ("", "unreadable: no text layer (scanned?)")
        except Exception as error:  # pragma: no cover - environment dependent
            return "", f"unreadable: pdftotext failed ({error})"
    return "", "unreadable: no PDF text extractor configured"


def read_text(path: Path) -> tuple[str, str]:
    suffix = path.suffix.casefold()
    if suffix == ".pdf":
        return extract_pdf_text(path)
    if suffix in TEXT_SUFFIXES:
        try:
            return path.read_text(encoding="utf-8"), "ok"
        except UnicodeDecodeError:
            return path.read_text(encoding="utf-8", errors="replace"), "partial: encoding errors"
    return "", "unreadable: unsupported format for text extraction"


class Ingestor:
    """Walks a project directory and builds the input manifest."""

    def __init__(self, root: Path):
        self.root = Path(root)
        if not self.root.exists():
            raise IngestError(f"project directory does not exist: {self.root}")
        self.texts: dict[str, str] = {}

    def scan(self) -> list[InputFile]:
        manifest: list[InputFile] = []
        for path in sorted(self.root.rglob("*")):
            if not path.is_file() or path.name.startswith("."):
                continue
            if any(part in {"versions", "output", "__pycache__"} for part in path.parts):
                continue
            manifest.append(self._describe(path))
        return manifest

    def _describe(self, path: Path) -> InputFile:
        role = detect_role(path, self.root)
        entry = InputFile(
            file=str(path),
            role=role,
            format=path.suffix.lstrip(".").upper() or "UNKNOWN",
            sha256=sha256_file(path),
        )
        if role in ("municipal_comments", "constraint", "reference"):
            text, status = read_text(path)
            if text:
                self.texts[str(path)] = text
                entry.pages = text.count("\f") + 1
            entry.read_status = "ok" if status == "ok" else status.split(":")[0]
            if status != "ok":
                entry.notes = status
        elif role == "source_model" and path.suffix.casefold() == ".json":
            try:
                document = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as error:
                entry.read_status = "unreadable"
                entry.notes = f"invalid JSON model: {error}"
            else:
                if not (isinstance(document, dict) and "elements" in document):
                    # A JSON file without an element list is not a drawing model.
                    entry.role = "reference"
                    entry.notes = "JSON file without an 'elements' list; not treated as a model"
        elif role == "source_model":
            entry.read_status = "ok"
            entry.notes = "binary model; requires a CAD/BIM driver"
        return entry

    def files(self, manifest: list[InputFile], role: str) -> list[InputFile]:
        return [entry for entry in manifest if entry.role == role]

    def text_of(self, entry: InputFile) -> str:
        return self.texts.get(entry.file, "")
