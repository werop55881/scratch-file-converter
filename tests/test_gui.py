"""GUI logic that runs without a window: run planning, launcher flags, CLI wiring."""

from __future__ import annotations

from pathlib import Path

import pytest

from sb3conv.cli import build_parser
from sb3conv.convert import ConversionResult, convert
from sb3conv.errors import Sb3Error
from sb3conv.gui import main as gui_main
from sb3conv.gui import plan_run


def test_cli_exposes_gui_command():
    args = build_parser().parse_args(["gui", "game.sb3"])
    assert args.command == "gui"
    assert args.input == "game.sb3"


def test_cli_gui_command_accepts_no_input():
    args = build_parser().parse_args(["gui"])
    assert args.command == "gui"
    assert args.input is None


def test_plan_run_python(sb3_path: Path, tmp_path: Path):
    result = convert(sb3_path, tmp_path / "out", lang="python")
    plan = plan_run(result)
    assert plan.kind == "python"
    assert plan.entrypoint == (tmp_path / "out" / "main.py").resolve()
    assert plan.output_dir == (tmp_path / "out").resolve()


def test_plan_run_javascript(sb3_path: Path, tmp_path: Path):
    result = convert(sb3_path, tmp_path / "out", lang="javascript")
    plan = plan_run(result)
    assert plan.kind == "browser"
    assert plan.entrypoint.name == "index.html"


def test_plan_run_c(sb3_path: Path, tmp_path: Path):
    result = convert(sb3_path, tmp_path / "out", lang="c")
    plan = plan_run(result)
    assert plan.kind == "native"
    assert plan.entrypoint.name == "main.c"


def test_plan_run_rejects_unknown_entrypoint(tmp_path: Path):
    result = ConversionResult(output_dir=tmp_path, entrypoint="game.lua")
    with pytest.raises(Sb3Error, match="no launcher"):
        plan_run(result)


def test_run_project_flag_executes_script(tmp_path: Path):
    marker = tmp_path / "ran.marker"
    (tmp_path / "sibling_mod.py").write_text("VALUE = 'sibling-ok'\n", encoding="utf-8")
    (tmp_path / "sb3_manifest.json").write_text("{}\n", encoding="utf-8")
    script = tmp_path / "tiny.py"
    script.write_text(
        "from pathlib import Path\n"
        "import sys\n"
        "import pygame  # prove pygame is importable in launcher mode\n"
        "from sibling_mod import VALUE  # sibling modules must be importable\n"
        f"Path(r'{marker}').write_text(pygame.version.ver + '|' + VALUE + '|' + ' '.join(sys.argv[1:]))\n",
        encoding="utf-8",
    )
    code = gui_main(["--run-project", str(script), "--smoke", "10"])
    assert code == 0
    content = marker.read_text(encoding="utf-8").strip()
    assert content, "script did not run"
    assert "|sibling-ok|" in content, "sibling module not importable"
    assert "--manifest" in content, "manifest flag not injected"
    assert content.endswith("--smoke 10"), "extra argv not passed through"


def test_run_project_flag_requires_argument(capsys):
    code = gui_main(["--run-project"])
    captured = capsys.readouterr()
    assert code == 2
    assert "usage" in captured.err


def test_gui_entry_delegates_cli_commands(capsys):
    code = gui_main(["languages"])
    captured = capsys.readouterr()
    assert code == 0
    assert "python" in captured.out


def test_theme_flag_validates(capsys):
    code = gui_main(["--theme", "neon"])
    captured = capsys.readouterr()
    assert code == 2
    assert "usage" in captured.err


def test_gui_build_app_checkbox_and_worker(tmp_path: Path, monkeypatch):
    import tkinter as tk

    from sb3conv.gui.app import ConverterApp

    captured: dict = {}

    def fake_convert(*args, **kwargs):
        captured.update(kwargs)
        return ConversionResult(output_dir=tmp_path, entrypoint="main.py")

    monkeypatch.setattr("sb3conv.gui.app.convert", fake_convert)
    root = tk.Tk()
    root.withdraw()
    try:
        app = ConverterApp(root)
        assert app.build_exe_var.get() is True
        app._convert_worker(Path("game.sb3"), None, "python", 2, 30, True)
        assert captured["build_exe"] is True
        app._convert_worker(Path("game.sb3"), None, "python", 2, 30, False)
        assert captured["build_exe"] is False
    finally:
        root.destroy()
