"""TypeScript backend: JS emit as .ts sources, tsc compile, html packaging."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from sb3conv.convert import convert


def _tsc_command() -> list[str] | None:
    """Command prefix that compiles a tsconfig directory, or None."""
    tsc = shutil.which("tsc")
    if tsc:
        return [tsc, "-p"]
    npx = shutil.which("npx")
    if npx:
        return [npx, "-y", "-p", "typescript", "tsc", "-p"]
    return None


def test_convert_writes_typescript_files(sb3_path: Path, tmp_path: Path):
    out = tmp_path / "ts"
    result = convert(sb3_path, out, lang="typescript")

    assert result.entrypoint == "index.html"
    for relative in (
        "index.html",
        "main.ts",
        "runtime.ts",
        "tsconfig.json",
        "sb3_manifest.json",
        "assets/abc123.png",
        "assets/def456.wav",
    ):
        assert (out / relative).exists(), relative

    main = (out / "main.ts").read_text(encoding="utf-8")
    assert "const MANIFEST" in main
    assert "function*" in main
    assert "new ScriptReg(" in main
    assert "run(SCRIPTS, MANIFEST);" in main

    runtime = (out / "runtime.ts").read_text(encoding="utf-8")
    assert runtime.startswith("// @ts-nocheck\n")

    config = json.loads((out / "tsconfig.json").read_text(encoding="utf-8"))
    assert config["compilerOptions"]["strict"] is False
    assert config["files"] == ["runtime.ts", "main.ts"]

    index = (out / "index.html").read_text(encoding="utf-8")
    assert '<script src="runtime.js"></script>' in index
    assert '<script src="main.js"></script>' in index


def test_ts_alias_converts(sb3_path: Path, tmp_path: Path):
    out = tmp_path / "ts-alias"
    result = convert(sb3_path, out, lang="ts")
    assert result.entrypoint == "index.html"
    assert (out / "main.ts").is_file()


def test_python_tagged_script_is_skipped_with_warning(sb3_path: Path, tmp_path: Path):
    out = tmp_path / "ts"
    result = convert(sb3_path, out, lang="ts", script_lang=["Star=python"])

    assert any("skipped" in warning for warning in result.warnings)
    main = (out / "main.ts").read_text(encoding="utf-8")
    assert "event_whenkeypressed" not in main  # the python-tagged sprite script
    assert "event_whenflagclicked" in main  # the untagged stage script still runs


def test_tsc_compiles_and_builds_single_file(sb3_path: Path, tmp_path: Path):
    command = _tsc_command()
    if command is None:
        pytest.skip("neither tsc nor npx installed")
    out = tmp_path / "ts"

    result = convert(sb3_path, out, lang="typescript", build_exe=True)

    assert result.artifact is not None
    assert result.artifact.suffix == ".html"
    assert (out / "runtime.js").is_file()
    assert (out / "main.js").is_file()
    text = result.artifact.read_text(encoding="utf-8")
    assert "<script src=" not in text
    assert "window.__SB3_ASSETS" in text
    assert "const MANIFEST" in text
