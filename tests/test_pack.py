"""Round trip: conversion embeds the source, pack rebuilds the .sb3."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from sb3conv.cli import main as cli_main
from sb3conv.convert import convert
from sb3conv.errors import Sb3Error
from sb3conv.sb3 import Archive, pack_project


@pytest.mark.parametrize("lang", ["python", "javascript", "c"])
def test_convert_embeds_original_sb3(sb3_path: Path, tmp_path: Path, lang: str):
    out = tmp_path / f"out-{lang}"
    result = convert(sb3_path, out, lang=lang)
    embedded = out / "original.sb3"
    assert embedded.is_file()
    assert embedded.read_bytes() == sb3_path.read_bytes()
    assert "original.sb3" in result.files


def test_pack_embedded_is_byte_identical(sb3_path: Path, tmp_path: Path):
    out = tmp_path / "game-py"
    convert(sb3_path, out, lang="python")
    packed = pack_project(out, tmp_path / "again.sb3")
    assert packed.read_bytes() == sb3_path.read_bytes()


def test_pack_default_name_comes_from_manifest(sb3_path: Path, tmp_path: Path):
    out = tmp_path / "some-dir"
    convert(sb3_path, out, lang="python")
    packed = pack_project(out)
    manifest = json.loads((out / "sb3_manifest.json").read_text(encoding="utf-8"))
    assert packed.name == f"{manifest['name']}.sb3"
    assert packed.parent == tmp_path


def test_pack_normalises_output_suffix(sb3_path: Path, tmp_path: Path):
    out = tmp_path / "game-py"
    convert(sb3_path, out, lang="python")
    packed = pack_project(out, tmp_path / "no-suffix")
    assert packed.suffix == ".sb3"


def test_pack_cli(sb3_path: Path, tmp_path: Path, capsys):
    out = tmp_path / "out"
    convert(sb3_path, out, lang="javascript")
    target = tmp_path / "cli.sb3"
    code = cli_main(["pack", str(out), "-o", str(target)])
    captured = capsys.readouterr()
    assert code == 0
    assert "packed" in captured.out
    assert target.read_bytes() == sb3_path.read_bytes()


def test_pack_requires_a_source(tmp_path: Path):
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(Sb3Error, match="has neither"):
        pack_project(empty, tmp_path / "out.sb3")


def _raw_project(sb3_path: Path) -> dict:
    with Archive.open(sb3_path) as archive:
        return archive.read_project_json()


def _write_loose_payload(sb3_path: Path, directory: Path) -> dict:
    """Lay out project.json + assets/ by hand (no embedded original)."""
    data = _raw_project(sb3_path)
    (directory / "assets").mkdir(parents=True)
    (directory / "project.json").write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8"
    )
    with Archive.open(sb3_path) as archive:
        for target in data["targets"]:
            for entry in [*target.get("costumes", []), *target.get("sounds", [])]:
                name = entry["md5ext"]
                (directory / "assets" / name).write_bytes(archive.read_asset(name))
    return data


def test_pack_assembles_from_project_json(sb3_path: Path, tmp_path: Path):
    src = tmp_path / "loose"
    data = _write_loose_payload(sb3_path, src)
    packed = pack_project(src, tmp_path / "built.sb3")
    with zipfile.ZipFile(packed) as zf:
        names = zf.namelist()
        assert names[0] == "project.json"
        assert "metadata.json" in names
        assert "abc123.png" in names
        assert "def456.wav" in names
        assert json.loads(zf.read("project.json")) == data


def test_pack_assemble_reports_missing_assets(sb3_path: Path, tmp_path: Path):
    src = tmp_path / "broken"
    src.mkdir()
    (src / "project.json").write_text(
        json.dumps(_raw_project(sb3_path)), encoding="utf-8"
    )
    (src / "assets").mkdir()
    with pytest.raises(Sb3Error, match="missing original assets"):
        pack_project(src, tmp_path / "out.sb3")
