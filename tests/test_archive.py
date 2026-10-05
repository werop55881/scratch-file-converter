"""Phase 1: archive reading."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from sb3conv.errors import ArchiveError, ProjectFormatError
from sb3conv.sb3 import Archive, load_project_data


def test_open_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ArchiveError, match="file not found"):
        Archive.open(tmp_path / "nope.sb3")


def test_open_rejects_non_zip(tmp_path: Path) -> None:
    path = tmp_path / "fake.sb3"
    path.write_text("hello, i am not a zip")
    with pytest.raises(ArchiveError, match="not a zip"):
        Archive.open(path)


def test_read_project_json(sb3_path: Path) -> None:
    with Archive.open(sb3_path) as archive:
        data = archive.read_project_json()
    assert "targets" in data
    assert data["targets"][0]["isStage"] is True


def test_missing_project_json(tmp_path: Path) -> None:
    path = tmp_path / "empty.sb3"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("notes.txt", "no project here")
    with Archive.open(path) as archive, pytest.raises(ProjectFormatError, match="contains no project.json"):
        archive.read_project_json()


def test_invalid_json(tmp_path: Path) -> None:
    path = tmp_path / "bad.sb3"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("project.json", "{not json")
    with Archive.open(path) as archive, pytest.raises(ProjectFormatError, match="not valid JSON"):
        archive.read_project_json()


def test_json_without_targets(tmp_path: Path) -> None:
    path = tmp_path / "wrong.sb3"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("project.json", json.dumps({"hello": "world"}))
    with Archive.open(path) as archive, pytest.raises(ProjectFormatError, match="no 'targets'"):
        archive.read_project_json()


def test_read_assets(sb3_path: Path) -> None:
    with Archive.open(sb3_path) as archive:
        assert archive.has_asset("abc123.png")
        assert not archive.has_asset("missing.png")
        png = archive.read_asset("abc123.png")
        assert png.startswith(b"\x89PNG")
        with pytest.raises(ArchiveError, match="missing"):
            archive.read_asset("missing.png")


def test_load_project_data(sb3_path: Path) -> None:
    data = load_project_data(sb3_path)
    assert len(data["targets"]) == 2
