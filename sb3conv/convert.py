"""High-level conversion: an .sb3 on disk becomes a runnable project directory."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from sb3conv.backends import get_backend
from sb3conv.build_app import NoBuildStep, ToolchainMissing, build_app
from sb3conv.errors import Sb3Error
from sb3conv.sb3 import Archive, Project, load_project

_BUILD_MESSAGES = {
    "python": "building .exe (this can take a minute)...",
    "c": "building .exe...",
    "javascript": "building single-file html...",
    "typescript": "compiling typescript + building html...",
    "lua": "packing .love archive...",
    "godot": "no build step: open the project folder in Godot 4...",
}


@dataclass
class ConversionResult:
    """What a conversion produced."""

    output_dir: Path
    entrypoint: str
    files: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    languages: dict[str, str] = field(default_factory=dict)
    artifact: Path | None = None


def parse_script_lang(entries: list[str] | None) -> dict[str, str]:
    """Parse ``--script-lang`` values of the form ``Sprite=js`` (comma separated)."""
    mapping: dict[str, str] = {}
    for entry in entries or []:
        for part in str(entry).split(","):
            part = part.strip()
            if not part:
                continue
            if "=" not in part:
                raise Sb3Error(f"--script-lang expects Sprite=lang, got {part!r}")
            sprite, language = part.split("=", 1)
            if not sprite.strip() or not language.strip():
                raise Sb3Error(f"--script-lang expects Sprite=lang, got {part!r}")
            mapping[sprite.strip()] = language.strip()
    return mapping


def collect_asset_names(project: Project) -> list[str]:
    """Every asset file name referenced by the project's costumes and sounds."""
    names: list[str] = []
    for target in project.targets:
        for costume in target.costumes:
            names.append(costume.asset.filename)
        for sound in target.sounds:
            names.append(sound.asset.filename)
    return names


def default_output_dir(input_path: Path, lang: str) -> Path:
    return input_path.with_name(f"{input_path.stem}-{lang}")


def _group_unsupported(
    unsupported: list[tuple[str, str]],
) -> list[tuple[str, list[tuple[str, int]]]]:
    """Group (opcode, location) pairs: [(opcode, [(location, count)...])...] by count."""
    counts: dict[str, dict[str, int]] = {}
    for opcode, where in unsupported:
        locations = counts.setdefault(opcode, {})
        locations[where] = locations.get(where, 0) + 1
    grouped = [
        (opcode, sorted(locations.items(), key=lambda item: (-item[1], item[0])))
        for opcode, locations in counts.items()
    ]
    grouped.sort(key=lambda item: (-sum(count for _, count in item[1]), item[0]))
    return grouped


def unsupported_report_text(
    project_name: str, lang: str, unsupported: list[tuple[str, str]]
) -> str:
    """Human-readable unsupported-block report (the ``unsupported.txt`` file)."""
    grouped = _group_unsupported(unsupported)
    lines = [
        "sb3conv unsupported-block report",
        f"project: {project_name}",
        f"target: {lang}",
        "",
        "These Scratch blocks could not be translated and became no-ops:",
        "",
    ]
    for opcode, locations in grouped:
        opcode_total = sum(count for _, count in locations)
        lines.append(f"  {opcode} ({opcode_total}x)")
        for where, count in locations:
            lines.append(f"    {where}" + (f" x{count}" if count > 1 else ""))
    lines += [
        "",
        f"total: {len(unsupported)} unsupported blocks, {len(grouped)} distinct opcodes",
    ]
    return "\n".join(lines) + "\n"


def unsupported_report_json(
    project_name: str, lang: str, unsupported: list[tuple[str, str]]
) -> str:
    """Machine-readable variant of the report (the ``unsupported.json`` file)."""
    grouped = _group_unsupported(unsupported)
    payload = {
        "project": project_name,
        "target": lang,
        "opcodes": [
            {
                "opcode": opcode,
                "count": sum(count for _, count in locations),
                "locations": [{"where": where, "count": count} for where, count in locations],
            }
            for opcode, locations in grouped
        ],
        "total": len(unsupported),
    }
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def convert(
    input_path: str | Path,
    output_dir: str | Path | None = None,
    *,
    lang: str | None = None,
    scale: int = 2,
    fps: int = 30,
    script_lang: list[str] | None = None,
    build_exe: bool = False,
    progress: Callable[[str], None] | None = None,
) -> ConversionResult:
    """Convert ``input_path`` into ``output_dir`` and return what happened.

    With ``build_exe`` the finished project is additionally packaged into a
    playable artifact (``.exe`` for python/c, one self-contained ``.html``
    for javascript). A missing toolchain downgrades to a warning; call
    ``progress`` to receive status lines while building.
    """
    input_path = Path(input_path)
    backend = get_backend(lang)
    out = Path(output_dir) if output_dir else default_output_dir(input_path, backend.name)
    original_bytes = input_path.read_bytes()

    with Archive.open(input_path) as archive:
        project = load_project(archive.read_project_json())
        assets = {
            name: archive.read_asset(name)
            for name in collect_asset_names(project)
            if archive.has_asset(name)
        }

    result = backend.emit(
        project,
        {
            "name": input_path.stem,
            "scale": scale,
            "fps": fps,
            "script_lang": parse_script_lang(script_lang),
            "assets": assets,
        },
    )

    written: list[str] = []
    for output in result.files:
        target = out / output.path
        target.parent.mkdir(parents=True, exist_ok=True)
        if output.mode == "wb":
            target.write_bytes(output.content)  # type: ignore[arg-type]
        else:
            target.write_text(output.content, encoding=output.encoding)  # type: ignore[arg-type]
        written.append(output.path)

    # the embedded source makes the conversion reversible (sb3conv pack)
    out.mkdir(parents=True, exist_ok=True)
    (out / "original.sb3").write_bytes(original_bytes)
    written.append("original.sb3")

    warnings = list(result.warnings)
    if result.unsupported:
        (out / "unsupported.txt").write_text(
            unsupported_report_text(input_path.stem, backend.name, result.unsupported),
            encoding="utf-8",
        )
        (out / "unsupported.json").write_text(
            unsupported_report_json(input_path.stem, backend.name, result.unsupported),
            encoding="utf-8",
        )
        written += ["unsupported.txt", "unsupported.json"]
        distinct = len({opcode for opcode, _ in result.unsupported})
        warnings.append(
            f"{len(result.unsupported)} unsupported blocks ({distinct} distinct opcodes)"
            " - see unsupported.txt"
        )
    artifact: Path | None = None
    if build_exe:
        if progress is not None:
            progress(_BUILD_MESSAGES.get(backend.name, "building app..."))
        try:
            artifact = build_app(out, lang=backend.name, name=input_path.stem)
        except NoBuildStep:
            pass  # the progress line already explained it (e.g. Godot)
        except ToolchainMissing as exc:
            warnings.append(f"app build skipped: {exc}")

    return ConversionResult(
        output_dir=out,
        entrypoint=result.entrypoint,
        files=written,
        warnings=warnings,
        languages=dict(result.script_languages),
        artifact=artifact,
    )
