"""Build-a-playable-app: PyInstaller packaging, C exe, single-file html, wiring."""

from __future__ import annotations

import importlib.util
import os
import subprocess
import types
from pathlib import Path

import pytest

from sb3conv.backends.c import find_sdl2_home, find_zig
from sb3conv.build_app import (
    ToolchainMissing,
    _script_safe,
    build_app,
    build_c_app,
    build_js_app,
    build_python_exe,
)
from sb3conv.cli import main as cli_main
from sb3conv.convert import convert
from sb3conv.errors import BackendError

needs_pyinstaller = pytest.mark.skipif(
    importlib.util.find_spec("PyInstaller") is None, reason="pyinstaller not installed"
)

needs_toolchain = pytest.mark.skipif(
    find_zig() is None or find_sdl2_home() is None, reason="zig/SDL2 not installed"
)


# ---------------------------------------------------------------- fast units


def test_convert_without_build_has_no_artifact(sb3_path: Path, tmp_path: Path):
    assert convert(sb3_path, tmp_path / "out").artifact is None


def test_convert_build_exe_warns_when_toolchain_missing(
    sb3_path: Path, tmp_path: Path, monkeypatch
):
    def fake_build(*args, **kwargs):
        raise ToolchainMissing("zig not found; install zig")

    monkeypatch.setattr("sb3conv.convert.build_app", fake_build)
    seen: list[str] = []
    result = convert(
        sb3_path, tmp_path / "out", lang="python", build_exe=True, progress=seen.append
    )
    assert result.artifact is None
    assert any("app build skipped" in warning for warning in result.warnings)
    assert any("zig" in warning for warning in result.warnings)
    assert any("building" in message for message in seen)


def test_build_python_exe_command(tmp_path: Path, monkeypatch):
    out = tmp_path / "game"
    out.mkdir()
    (out / "main.py").write_text("print('hi')\n", encoding="utf-8")
    (out / "sb3_manifest.json").write_text("{}\n", encoding="utf-8")
    (out / "assets").mkdir()

    recorded: dict[str, list[str]] = {}

    def fake_run(command, **kwargs):
        recorded["cmd"] = list(command)
        recorded["cwd"] = kwargs.get("cwd")
        dist = Path(command[command.index("--distpath") + 1])
        name = command[command.index("--name") + 1]
        (dist / (name + (".exe" if os.name == "nt" else ""))).write_bytes(b"MZfake")
        return types.SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr("sb3conv.build_app._runs", lambda command: True)
    monkeypatch.setattr("sb3conv.build_app.subprocess.run", fake_run)

    exe = build_python_exe(out, name="star-game")
    assert exe == out / ("star-game.exe" if os.name == "nt" else "star-game")

    command = recorded["cmd"]
    assert "PyInstaller" in command
    assert "--onefile" in command
    assert "--windowed" in command
    assert command[command.index("--name") + 1] == "star-game"
    add_data = [
        command[index + 1] for index, value in enumerate(command) if value == "--add-data"
    ]
    assert any("sb3_manifest.json" in value for value in add_data)
    assert any(value.endswith(f"{os.pathsep}assets") for value in add_data)
    assert str(out / "main.py") in command
    # PyInstaller refuses to run from a system cwd, so it must be pinned here
    assert Path(recorded["cwd"]).is_absolute()


def test_build_python_exe_console_flag(tmp_path: Path, monkeypatch):
    out = tmp_path / "game"
    out.mkdir()
    (out / "main.py").write_text("print('hi')\n", encoding="utf-8")

    recorded: dict[str, list[str]] = {}

    def fake_run(command, **kwargs):
        recorded["cmd"] = list(command)
        dist = Path(command[command.index("--distpath") + 1])
        name = command[command.index("--name") + 1]
        (dist / (name + (".exe" if os.name == "nt" else ""))).write_bytes(b"MZfake")
        return types.SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr("sb3conv.build_app._runs", lambda command: True)
    monkeypatch.setattr("sb3conv.build_app.subprocess.run", fake_run)

    build_python_exe(out, name="g", console=True)
    assert "--console" in recorded["cmd"]


def test_build_python_exe_without_project(tmp_path: Path):
    with pytest.raises(BackendError, match="converted python project"):
        build_python_exe(tmp_path, name="x")


def test_build_python_exe_resolves_relative_out_dir(tmp_path: Path, monkeypatch):
    # PyInstaller resolves relative --add-data paths against its temp spec
    # directory, so a relative out_dir must be absolutized before the call.
    out = tmp_path / "game"
    out.mkdir()
    (out / "main.py").write_text("print('hi')\n", encoding="utf-8")
    (out / "sb3_manifest.json").write_text("{}\n", encoding="utf-8")
    (out / "assets").mkdir()

    recorded: dict[str, list[str]] = {}

    def fake_run(command, **kwargs):
        recorded["cmd"] = list(command)
        dist = Path(command[command.index("--distpath") + 1])
        name = command[command.index("--name") + 1]
        (dist / (name + (".exe" if os.name == "nt" else ""))).write_bytes(b"MZfake")
        return types.SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr("sb3conv.build_app._runs", lambda command: True)
    monkeypatch.setattr("sb3conv.build_app.subprocess.run", fake_run)
    monkeypatch.chdir(tmp_path)

    exe = build_python_exe(Path("game"), name="rel-game")
    assert exe.is_absolute()

    command = recorded["cmd"]
    add_data = [
        command[index + 1] for index, value in enumerate(command) if value == "--add-data"
    ]
    manifest_arg = next(value for value in add_data if "sb3_manifest.json" in value)
    assert Path(manifest_arg.split(os.pathsep)[0]).is_absolute()


def test_build_c_app_reports_missing_toolchain(tmp_path: Path, monkeypatch):
    (tmp_path / "main.c").write_text("int main(void){return 0;}\n", encoding="utf-8")
    monkeypatch.setattr("sb3conv.backends.c.find_zig", lambda: None)
    with pytest.raises(ToolchainMissing, match="zig"):
        build_c_app(tmp_path, name="x")


def test_build_js_app_requires_converted_project(tmp_path: Path):
    with pytest.raises(BackendError, match="javascript project"):
        build_js_app(tmp_path, name="x")


def test_build_app_unknown_lang(tmp_path: Path):
    with pytest.raises(BackendError, match="no build step"):
        build_app(tmp_path, lang="lua", name="x")


def test_script_safe_escapes_closing_tags():
    assert _script_safe('x = "</script>"') == 'x = "<\\/script>"'
    assert _script_safe('x = "</SCRIPT>"') == 'x = "<\\/SCRIPT>"'


def test_convert_javascript_builds_single_file(sb3_path: Path, tmp_path: Path):
    result = convert(sb3_path, tmp_path / "js", lang="javascript", build_exe=True)

    assert result.artifact is not None
    assert result.artifact.suffix == ".html"
    assert result.artifact.exists()
    text = result.artifact.read_text(encoding="utf-8")
    assert "<script src=" not in text
    assert "window.__SB3_ASSETS" in text
    assert "data:image/png;base64," in text
    assert "data:audio/wav;base64," in text
    assert "const MANIFEST" in text


def test_cli_convert_exe_flag(sb3_path: Path, tmp_path: Path, capsys):
    code = cli_main(
        [
            "convert",
            str(sb3_path),
            "-o",
            str(tmp_path / "js"),
            "--lang",
            "javascript",
            "--exe",
        ]
    )
    captured = capsys.readouterr()
    assert code == 0
    assert "app:" in captured.out
    assert list((tmp_path / "js").glob("*.html"))


# ------------------------------------------------------------------ slow e2e


@needs_toolchain
@pytest.mark.slow
def test_c_exe_build_runs_smoke(sb3_path: Path, tmp_path: Path):
    from sb3conv.backends.c import runtime_env

    out = tmp_path / "c"
    convert(sb3_path, out, lang="c")
    exe = build_c_app(out, name="smoke-game")
    assert exe.exists()
    proc = subprocess.run(
        [str(exe), "--smoke", "10"],
        cwd=out,
        capture_output=True,
        text=True,
        timeout=120,
        env=runtime_env(smoke=True),
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "SMOKE OK" in proc.stdout, proc.stdout


@needs_pyinstaller
@pytest.mark.slow
def test_python_exe_build_runs_smoke(sb3_path: Path, tmp_path: Path):
    out = tmp_path / "py"
    convert(sb3_path, out, lang="python")
    exe = build_python_exe(out, name="smoke-game", console=True)
    assert exe.exists()
    proc = subprocess.run(
        [str(exe), "--smoke", "10"],
        cwd=out,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "SMOKE OK" in proc.stdout, proc.stdout
