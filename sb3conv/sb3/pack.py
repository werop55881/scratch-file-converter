"""Rebuild a Scratch .sb3 archive from a converted project directory.

Every conversion embeds the source project as ``original.sb3`` in the
output directory, so the round trip is lossless: packing copies those
exact bytes back out. For directories that carry a plain ``project.json``
plus ``assets/`` instead, the packer assembles the archive itself.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

from sb3conv.errors import Sb3Error

EMBEDDED_NAME = "original.sb3"
_METADATA_JSON = json.dumps({"semver": "3.0.0", "vm": "0.2.0", "agent": ""})


def referenced_assets(project_data: dict) -> list[str]:
    """Asset file names (md5ext) referenced by costumes and sounds."""
    names: list[str] = []
    for target in project_data.get("targets", []):
        for entry in [*target.get("costumes", []), *target.get("sounds", [])]:
            md5ext = entry.get("md5ext")
            if md5ext:
                names.append(str(md5ext))
    return names


def _load_embedded(embedded: Path) -> bytes:
    try:
        with zipfile.ZipFile(embedded) as zf:
            if "project.json" not in zf.namelist():
                raise Sb3Error(f"{embedded} has no project.json inside")
            zf.read("project.json")
    except zipfile.BadZipFile as exc:
        raise Sb3Error(f"{embedded} is not a valid .sb3 archive: {exc}") from exc
    return embedded.read_bytes()


def _load_project_json(project_dir: Path) -> dict:
    project_json = project_dir / "project.json"
    if not project_json.is_file():
        raise Sb3Error(
            f"{project_dir} has neither {EMBEDDED_NAME} nor project.json - "
            "convert the .sb3 with this version first"
        )
    try:
        return json.loads(project_json.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise Sb3Error(f"{project_json} is not valid JSON: {exc}") from exc


def _assemble_zip(project_dir: Path, data: dict, out_path: Path) -> None:
    assets_dir = project_dir / "assets"
    names = referenced_assets(data)
    missing = [name for name in names if not (assets_dir / name).is_file()]
    if missing:
        preview = ", ".join(sorted(missing)[:4]) + (", ..." if len(missing) > 4 else "")
        raise Sb3Error(
            f"missing original assets in {assets_dir}: {preview} - "
            f"keep {EMBEDDED_NAME} in the converted folder instead"
        )
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "project.json",
            json.dumps(data, ensure_ascii=False, separators=(",", ":")),
        )
        for name in sorted(set(names)):
            zf.write(assets_dir / name, arcname=name)
        zf.writestr("metadata.json", _METADATA_JSON)


def _default_name(project_dir: Path) -> str:
    manifest = project_dir / "sb3_manifest.json"
    if manifest.is_file():
        try:
            name = json.loads(manifest.read_text(encoding="utf-8")).get("name")
            if name:
                return str(name)
        except json.JSONDecodeError:
            pass
    return project_dir.name


def pack_project(project_dir: str | Path, out_path: str | Path | None = None) -> Path:
    """Pack *project_dir* back into a Scratch ``.sb3`` and return its path.

    Preferred source is the embedded ``original.sb3`` (byte-identical
    round trip). Otherwise ``project.json`` + ``assets/`` are re-zipped.
    """
    project_dir = Path(project_dir)
    embedded = project_dir / EMBEDDED_NAME

    if out_path is None:
        out_path = project_dir.parent / f"{_default_name(project_dir)}.sb3"
    out_path = Path(out_path)
    if out_path.suffix.lower() != ".sb3":
        out_path = out_path.with_suffix(".sb3")

    if embedded.is_file():
        out_path.write_bytes(_load_embedded(embedded))
        return out_path

    data = _load_project_json(project_dir)
    _assemble_zip(project_dir, data, out_path)
    return out_path
