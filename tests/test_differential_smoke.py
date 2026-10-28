#> Differential smoke: every backend must agree on observable stage state after N frames.
"""Differential smoke: every backend must agree on observable stage state after N frames.

This is the cross-runtime equivalent of a differential test: the sample project is
converted to each available target, each runtime is driven headless for the same
number of frames, and the ``SBSTATE`` lines are compared.  Any divergence in
frame scheduling, variable updates or control flow shows up as a mismatch.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from sb3conv.backends.c import build_executable, find_sdl2_home, find_zig, runtime_env
from sb3conv.backends.godot import find_godot
from sb3conv.convert import convert

SMOKE_FRAMES = 30


def _sb3_path(tmp_path: Path) -> Path:
    """Build the sample .sb3 (mirrors the conftest fixture)."""
    import tests.helpers as helpers

    project_dict = helpers.sample_project()
    path = tmp_path / "sample.sb3"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("project.json", json.dumps(project_dict))
        # minimal assets
        zf.writestr("abc123.png", b"")
        zf.writestr("def456.wav", b"")
    return path


def _parse_states(stdout: str) -> dict[str, str]:
    states: dict[str, str] = {}
    for line in stdout.splitlines():
        m = re.match(r"^SBSTATE (\S+)=(.*)$", line)
        if m:
            states[m.group(1)] = m.group(2)
    return states


def _normalise(value: str):
    try:
        return float(value)
    except ValueError:
        return value


@pytest.mark.slow
def test_differential_smoke(tmp_path: Path):
    sb3 = _sb3_path(tmp_path)
    results: dict[str, dict[str, str]] = {}

    # --- python ---------------------------------------------------------
    py_out = tmp_path / "python"
    convert(sb3, py_out, lang="python")
    env = {**os.environ, "SDL_VIDEODRIVER": "dummy", "SDL_AUDIODRIVER": "dummy",
           "PYGAME_HIDE_SUPPORT_PROMPT": "1"}
    proc = subprocess.run(
        [sys.executable, "main.py", "--smoke", str(SMOKE_FRAMES)],
        cwd=py_out, env=env, capture_output=True, text=True, timeout=180,
    )
    assert proc.returncode == 0, f"python:\n{proc.stdout}\n{proc.stderr}"
    assert "SMOKE OK" in proc.stdout
    results["python"] = _parse_states(proc.stdout)

    # --- javascript (node) ----------------------------------------------
    if shutil.which("node"):
        js_out = tmp_path / "js"
        convert(sb3, js_out, lang="javascript")
        combined = (js_out / "runtime.js").read_text(encoding="utf-8") + "\n" + \
                   (js_out / "main.js").read_text(encoding="utf-8")
        smoke = js_out / "_node_smoke.js"
        smoke.write_text(combined, encoding="utf-8")
        env = {**os.environ, "SB3CONV_SMOKE": str(SMOKE_FRAMES)}
        proc = subprocess.run(
            [shutil.which("node"), str(smoke)],
            cwd=js_out, env=env, capture_output=True, text=True, timeout=180,
        )
        assert proc.returncode == 0, f"js:\n{proc.stdout}\n{proc.stderr}"
        assert "SMOKE OK" in proc.stdout
        results["javascript"] = _parse_states(proc.stdout)

    # --- c ---------------------------------------------------------------
    if find_zig() is not None and find_sdl2_home() is not None:
        c_out = tmp_path / "c"
        convert(sb3, c_out, lang="c")
        exe = build_executable(c_out)
        proc = subprocess.run(
            [str(exe), "--smoke", str(SMOKE_FRAMES)],
            cwd=c_out, capture_output=True, text=True, timeout=180,
            env=runtime_env(smoke=True),
        )
        assert proc.returncode == 0, f"c:\n{proc.stdout}\n{proc.stderr}"
        assert "SMOKE OK" in proc.stdout
        results["c"] = _parse_states(proc.stdout)

    # --- godot -----------------------------------------------------------
    godot = find_godot()
    if godot is not None:
        gd_out = tmp_path / "godot"
        convert(sb3, gd_out, lang="godot")
        imported = subprocess.run(
            [godot, "--headless", "--path", str(gd_out), "--import"],
            capture_output=True, text=True, timeout=240,
        )
        assert imported.returncode == 0, imported.stdout + imported.stderr
        env = {**os.environ, "SB3CONV_SMOKE": str(SMOKE_FRAMES)}
        proc = subprocess.run(
            [godot, "--headless", "--path", str(gd_out)],
            capture_output=True, text=True, timeout=240, env=env,
        )
        combined = proc.stdout + proc.stderr
        assert proc.returncode == 0, combined
        assert "SMOKE OK" in combined
        results["godot"] = _parse_states(combined)

    # --- lua (LÖVE) ------------------------------------------------------
    love = shutil.which("love") or (
        r"C:\Program Files\LOVE\love.exe" if Path(r"C:\Program Files\LOVE\love.exe").exists() else None
    )
    if love is not None:
        lua_out = tmp_path / "lua"
        convert(sb3, lua_out, lang="lua")
        env = {**os.environ, "SB3CONV_SMOKE": str(SMOKE_FRAMES)}
        proc = subprocess.run(
            [love, str(lua_out)],
            capture_output=True, text=True, timeout=180, env=env,
        )
        combined = proc.stdout + proc.stderr
        assert proc.returncode == 0, f"lua:\n{combined}"
        assert "SMOKE OK" in combined
        results["lua"] = _parse_states(combined)

    # --- compare ---------------------------------------------------------
    assert len(results) >= 2, "need at least two backends to compare"
    normalised = {name: {k: _normalise(v) for k, v in states.items()}
                  for name, states in results.items()}
    reference = next(iter(normalised.values()))
    for name, states in normalised.items():
        assert states == reference, (
            f"{name} state diverges from reference:\n"
            f"  {name}: {states}\n  ref:   {reference}"
        )
