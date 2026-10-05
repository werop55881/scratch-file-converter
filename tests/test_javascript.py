"""JavaScript backend: conversion output, syntax checking, script language routing."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from sb3conv.convert import convert


def test_convert_writes_web_files(sb3_path: Path, tmp_path: Path):
    out = tmp_path / "js"
    result = convert(sb3_path, out, lang="js")

    assert result.entrypoint == "index.html"
    for relative in (
        "index.html",
        "main.js",
        "runtime.js",
        "sb3_manifest.json",
        "assets/abc123.png",
        "assets/def456.wav",
    ):
        assert (out / relative).exists(), relative

    main = (out / "main.js").read_text(encoding="utf-8")
    assert "function*" in main
    assert "const MANIFEST" in main
    assert "run(SCRIPTS, MANIFEST);" in main
    assert "new ScriptReg(" in main

    index = (out / "index.html").read_text(encoding="utf-8")
    assert '<script src="runtime.js"></script>' in index
    assert '<script src="main.js"></script>' in index
    assert 'id="stage"' in index

    manifest = (out / "sb3_manifest.json").read_text(encoding="utf-8")
    assert '"name": "Stage"' in manifest


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_generated_javascript_is_syntax_valid(sb3_path: Path, tmp_path: Path):
    out = tmp_path / "js"
    convert(sb3_path, out, lang="js")

    node = shutil.which("node")
    assert node is not None
    for name in ("main.js", "runtime.js"):
        proc = subprocess.run(
            [node, "--check", str(out / name)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode == 0, f"{name}: {proc.stderr}"


def test_python_tagged_script_is_skipped_with_warning(sb3_path: Path, tmp_path: Path):
    out = tmp_path / "js"
    result = convert(sb3_path, out, lang="js", script_lang=["Star=python"])

    assert any("skipped" in warning for warning in result.warnings)
    main = (out / "main.js").read_text(encoding="utf-8")
    assert "event_whenkeypressed" not in main  # the python-tagged sprite script
    assert "event_whenflagclicked" in main  # the untagged stage script still runs


def test_converted_sample_runs_headless_with_node(sb3_path: Path, tmp_path: Path):
    if shutil.which("node") is None:
        pytest.skip("node not installed")
    out = tmp_path / "js"
    convert(sb3_path, out, lang="js")

    # in a browser the two scripts share one global scope; emulate that here
    combined = "\n".join(
        [
            (out / "runtime.js").read_text(encoding="utf-8"),
            (out / "main.js").read_text(encoding="utf-8"),
        ]
    )
    smoke = out / "_node_smoke.js"
    smoke.write_text(combined, encoding="utf-8")

    # without a DOM the runtime must print its message and exit cleanly
    proc = subprocess.run(
        [shutil.which("node"), str(smoke)],
        cwd=out,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert "no DOM" in proc.stderr


def test_game_converts_to_js_without_warnings(tmp_path: Path):
    game = Path(__file__).resolve().parents[1] / "game" / "star-game.sb3"
    if not game.exists():
        pytest.skip("game project not built")

    out = tmp_path / "game-js"
    result = convert(game, out, lang="js")

    assert result.warnings == []
    main = (out / "main.js").read_text(encoding="utf-8")
    assert main.count("new ScriptReg(") == 10
    assert (out / "assets").is_dir()


def _find_chrome() -> str | None:
    env = os.environ.get("CHROME")
    if env and Path(env).exists():
        return env
    candidates = [
        Path(os.environ.get("PROGRAMFILES", "")) / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Microsoft/Edge/Application/msedge.exe",
        Path(os.environ.get("PROGRAMFILES", "")) / "Microsoft/Edge/Application/msedge.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe",
    ]
    for candidate in candidates:
        if str(candidate) and candidate.exists():
            return str(candidate)
    return None


@pytest.mark.slow
def test_game_smoke_in_headless_browser(tmp_path: Path):
    """End-to-end: real Chrome, real canvas and images, 60 frames of the game."""
    if shutil.which("node") is None:
        pytest.skip("node not installed")
    chrome = _find_chrome()
    if chrome is None:
        pytest.skip("chrome/edge not installed")

    game = Path(__file__).resolve().parents[1] / "game" / "star-game.sb3"
    if not game.exists():
        pytest.skip("game project not built")

    out = tmp_path / "game-js"
    convert(game, out, lang="js")

    tool = Path(__file__).resolve().parents[1] / "tools" / "browser_smoke.js"
    url = f"file:///{(out / 'index.html').as_posix()}?smoke=60"
    proc = subprocess.run(
        [shutil.which("node"), str(tool), url, "25"],
        capture_output=True,
        text=True,
        check=False,
        timeout=90,
        env={**os.environ, "CHROME": chrome},
    )
    assert proc.returncode == 0, f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    assert "BROWSER SMOKE OK" in proc.stdout
