#> Godot 4 backend: project output, script routing, headless smoke runs.
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

from sb3conv.backends.godot import find_godot
from sb3conv.convert import convert


def test_backends_registered():
    from sb3conv.backends import available_languages

    languages = available_languages()
    assert "godot" in languages


def test_convert_writes_godot_project(sb3_path: Path, tmp_path: Path):
    out = tmp_path / "godot"
    # the sample sprite script carries a `lang: js` comment; route it explicitly
    result = convert(sb3_path, out, lang="godot", script_lang=["Star=godot"])

    assert result.entrypoint == "project.godot"
    for relative in (
        "project.godot",
        "main.tscn",
        "runtime.gd",
        "scratch.gd",
        "scripts.gd",
        "manifest.json",
        "sb3_manifest.json",
        "assets/abc123.png",
        "assets/def456.wav",
    ):
        assert (out / relative).exists(), relative

    project = (out / "project.godot").read_text(encoding="utf-8")
    assert 'run/main_scene="res://main.tscn"' in project
    assert "window/size/viewport_width=480" in project
    assert "window/size/window_width_override=960" in project  # 480 * scale 2
    assert 'window/stretch/mode="canvas_items"' in project

    scene = (out / "main.tscn").read_text(encoding="utf-8")
    assert 'script = ExtResource("1")' in scene

    scripts = (out / "scripts.gd").read_text(encoding="utf-8")
    assert "func script_0(ctx, rt) -> void:" in scripts
    assert '"hat": "event_whenflagclicked"' in scripts
    assert '"hat": "event_whenkeypressed"' in scripts
    assert "func registrations() -> Array:" in scripts
    # blocking action + per-frame loop turn into await coroutines
    assert "await rt.broadcast_wait(" in scripts
    assert "await rt.tick" in scripts
    # variables resolve through the shared runtime dicts
    assert "rt.vars[" in scripts

    runtime = (out / "runtime.gd").read_text(encoding="utf-8")
    assert "class_name Sb3Runtime" in runtime
    scratch = (out / "scratch.gd").read_text(encoding="utf-8")
    assert "class_name Scratch" in scratch

    manifest = (out / "manifest.json").read_text(encoding="utf-8")
    assert '"name": "sample"' in manifest
    assert '"assetDir": "assets"' in manifest


def test_js_tagged_script_is_skipped_by_default(sb3_path: Path, tmp_path: Path):
    out = tmp_path / "godot"
    result = convert(sb3_path, out, lang="godot")

    assert any("javascript" in warning and "skipped" in warning for warning in result.warnings)
    scripts = (out / "scripts.gd").read_text(encoding="utf-8")
    assert "event_whenkeypressed" not in scripts  # the js-tagged sprite script
    assert "event_whenflagclicked" in scripts  # the untagged stage script still runs


def test_gd_alias_converts(sb3_path: Path, tmp_path: Path):
    out = tmp_path / "godot"
    result = convert(sb3_path, out, lang="gd")
    assert result.entrypoint == "project.godot"
    assert (out / "scripts.gd").is_file()


def test_build_exe_flag_is_a_noop(sb3_path: Path, tmp_path: Path):
    # the GUI ships the Build checkbox on by default; Godot needs no build
    out = tmp_path / "godot"
    lines: list[str] = []
    result = convert(sb3_path, out, lang="godot", build_exe=True, progress=lines.append)

    assert result.artifact is None
    assert not any("app build skipped" in warning for warning in result.warnings)
    assert any("no build step" in line for line in lines)


def _run_godot(godot: str, args: list[str], cwd: Path, env: dict | None = None, timeout: int = 240):
    merged = dict(os.environ)
    if env:
        merged.update(env)
    return subprocess.run(
        [godot, "--headless", "--path", str(cwd), *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        env=merged,
    )


def test_headless_smoke(sb3_path: Path, tmp_path: Path):
    godot = find_godot()
    if godot is None:
        pytest.skip("no godot editor installed ($GODOT / PATH / ~/godotsdk)")
    out = tmp_path / "godot"
    convert(sb3_path, out, lang="godot", script_lang=["Star=godot"])

    imported = _run_godot(godot, ["--import"], out)
    assert imported.returncode == 0, imported.stdout + imported.stderr
    assert "SCRIPT ERROR" not in imported.stdout + imported.stderr

    proc = _run_godot(godot, [], out, env={"SB3CONV_SMOKE": "30"})
    combined = proc.stdout + proc.stderr
    assert proc.returncode == 0, combined
    assert "SCRIPT ERROR" not in combined, combined
    assert "SMOKE OK frames=30" in combined, combined
    # the green-flag forever script must actually be running as a live thread
    assert "threads=" in combined and not re.search(r"threads=0\b", combined), combined
