"""High-level conversion: an .sb3 on disk becomes a runnable project directory."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from sb3conv.backends import get_backend
from sb3conv.build_app import ToolchainMissing, build_app
from sb3conv.errors import Sb3Error
from sb3conv.sb3 import Archive, Project, load_project

_BUILD_MESSAGES = {
    "python": "building .exe (this can take a minute)...",
    "c": "building .exe...",
    "javascript": "building single-file html...",
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

    warnings = list(result.warnings)
    artifact: Path | None = None
    if build_exe:
        if progress is not None:
            progress(_BUILD_MESSAGES.get(backend.name, "building app..."))
        try:
            artifact = build_app(out, lang=backend.name, name=input_path.stem)
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
