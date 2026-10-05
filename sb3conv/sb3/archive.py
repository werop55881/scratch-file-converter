"""Reading .sb3 archives (plain zip files with a project.json inside)."""

from __future__ import annotations

import json
import zipfile
from dataclasses import dataclass
from pathlib import Path

from sb3conv.errors import ArchiveError, ProjectFormatError

PROJECT_JSON = "project.json"


@dataclass
class Archive:
    """A opened .sb3 (zip) file."""

    path: Path
    _zip: zipfile.ZipFile

    @classmethod
    def open(cls, path: str | Path) -> Archive:
        path = Path(path)
        if not path.exists():
            raise ArchiveError(f"file not found: {path}")
        if not zipfile.is_zipfile(path):
            raise ArchiveError(f"not a zip archive (is it really an .sb3?): {path}")
        try:
            zf = zipfile.ZipFile(path)
        except zipfile.BadZipFile as exc:  # pragma: no cover - is_zipfile already checked
            raise ArchiveError(str(exc)) from exc
        return cls(path, zf)

    def close(self) -> None:
        self._zip.close()

    def __enter__(self) -> Archive:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -----------------------------------------------------------------------
    def names(self) -> list[str]:
        return self._zip.namelist()

    def read_project_json(self) -> dict:
        try:
            raw = self._zip.read(PROJECT_JSON)
        except KeyError as exc:
            raise ProjectFormatError(f"{self.path.name} contains no {PROJECT_JSON}") from exc
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ProjectFormatError(f"{PROJECT_JSON} is not valid JSON: {exc}") from exc
        if not isinstance(data, dict) or "targets" not in data:
            raise ProjectFormatError(f"{PROJECT_JSON} has no 'targets' key - not a Scratch 3 project")
        return data

    def has_asset(self, filename: str) -> bool:
        return filename in self._zip.namelist()

    def read_asset(self, filename: str) -> bytes:
        try:
            return self._zip.read(filename)
        except KeyError as exc:
            raise ArchiveError(f"asset {filename!r} missing from {self.path.name}") from exc


def load_project_data(path: str | Path) -> dict:
    with Archive.open(path) as archive:
        return archive.read_project_json()
