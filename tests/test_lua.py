"""Lua (LÖVE) backend: conversion output, .love packaging, syntax checking."""

from __future__ import annotations

import json
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

from sb3conv.convert import convert


def test_backends_registered():
    from sb3conv.backends import available_languages

    languages = available_languages()
    assert "lua" in languages
    assert "typescript" in languages


def test_convert_writes_love_files(sb3_path: Path, tmp_path: Path):
    out = tmp_path / "lua"
    # the sample sprite script carries a `lang: js` comment; route it explicitly
    result = convert(sb3_path, out, lang="lua", script_lang=["Star=lua"])

    assert result.entrypoint == "main.lua"
    for relative in (
        "main.lua",
        "runtime.lua",
        "manifest.lua",
        "conf.lua",
        "sb3_manifest.json",
        "assets/abc123.png",
        "assets/def456.wav",
    ):
        assert (out / relative).exists(), relative

    main = (out / "main.lua").read_text(encoding="utf-8")
    assert 'require("runtime")' in main
    assert 'local MANIFEST = require("manifest")' in main
    assert "local script_0" in main
    assert "= function(ctx, rt)" in main
    assert 'ScriptReg("Stage", "event_whenflagclicked"' in main
    assert 'ScriptReg("Star", "event_whenkeypressed"' in main
    assert "run(SCRIPTS, MANIFEST)" in main
    # blocking action + per-frame loop turn into coroutines/yields
    assert "rt:broadcast_wait(" in main
    assert "coroutine.yield()" in main
    # conditions go through s_bool to keep JavaScript truthiness
    assert "rt.vars[" in main

    conf = (out / "conf.lua").read_text(encoding="utf-8")
    assert "function love.conf(t)" in conf
    assert "t.window.width = 960" in conf  # 480 * scale 2

    manifest_lua = (out / "manifest.lua").read_text(encoding="utf-8")
    assert manifest_lua.startswith("-- Project manifest")
    assert 'name = "sample"' in manifest_lua
    assert 'assetDir = "assets"' in manifest_lua

    runtime = (out / "runtime.lua").read_text(encoding="utf-8")
    assert "_G.s_bool = s_bool" in runtime


def test_js_tagged_script_is_skipped_by_default(sb3_path: Path, tmp_path: Path):
    out = tmp_path / "lua"
    result = convert(sb3_path, out, lang="lua")

    assert any("javascript" in warning and "skipped" in warning for warning in result.warnings)
    main = (out / "main.lua").read_text(encoding="utf-8")
    assert "event_whenkeypressed" not in main  # the js-tagged sprite script
    assert "event_whenflagclicked" in main  # the untagged stage script still runs


def test_love_alias_converts(sb3_path: Path, tmp_path: Path):
    out = tmp_path / "love"
    result = convert(sb3_path, out, lang="love")
    assert result.entrypoint == "main.lua"
    assert (out / "main.lua").is_file()


def test_python_tagged_script_is_skipped_with_warning(sb3_path: Path, tmp_path: Path):
    out = tmp_path / "lua"
    result = convert(sb3_path, out, lang="lua", script_lang=["Star=python"])

    assert any("skipped" in warning for warning in result.warnings)
    main = (out / "main.lua").read_text(encoding="utf-8")
    assert "event_whenkeypressed" not in main  # the python-tagged sprite script
    assert "event_whenflagclicked" in main  # the untagged stage script still runs


def _lua_command() -> list[str] | None:
    """Command prefix that runs a Lua script, or None when nothing is installed."""
    for name in ("lua", "luajit"):
        found = shutil.which(name)
        if found:
            return [found]
    if shutil.which("npx"):
        return [shutil.which("npx"), "-y", "-p", "fengari-node-cli", "fengari"]
    return None


def test_generated_lua_is_syntax_valid(sb3_path: Path, tmp_path: Path):
    command = _lua_command()
    if command is None:
        pytest.skip("no lua interpreter (lua/luajit/npx) installed")
    out = tmp_path / "lua"
    convert(sb3_path, out, lang="lua")

    names = ["main.lua", "runtime.lua", "manifest.lua", "conf.lua"]
    checker = tmp_path / "_syntax_check.lua"
    checker.write_text(
        "\n".join(
            f"assert(loadfile({json.dumps(str(out / name))}), {json.dumps(name)})"
            for name in names
        )
        + "\nprint('lua syntax ok')\n",
        encoding="utf-8",
    )
    proc = subprocess.run(
        [*command, str(checker)],
        capture_output=True,
        text=True,
        check=False,
        timeout=180,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "lua syntax ok" in proc.stdout


def test_build_exe_packs_love_archive(sb3_path: Path, tmp_path: Path):
    out = tmp_path / "lua"
    seen: list[str] = []
    result = convert(sb3_path, out, lang="lua", build_exe=True, progress=seen.append)

    assert any(".love" in message for message in seen)
    assert result.artifact is not None
    assert result.artifact.suffix == ".love"
    with zipfile.ZipFile(result.artifact) as archive:
        names = set(archive.namelist())
    assert "main.lua" in names
    assert "runtime.lua" in names
    assert "manifest.lua" in names
    assert "conf.lua" in names
    assert "assets/abc123.png" in names
    # converter bookkeeping stays out of the game archive
    assert "original.sb3" not in names
    assert "sb3_manifest.json" not in names
