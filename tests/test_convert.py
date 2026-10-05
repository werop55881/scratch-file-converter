"""End-to-end conversion: .sb3 on disk -> output directory -> headless smoke run."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from sb3conv.cli import main as cli_main
from sb3conv.convert import convert, parse_script_lang
from sb3conv.errors import Sb3Error


def test_convert_writes_every_file(sb3_path: Path, tmp_path: Path):
    out = tmp_path / "out"
    result = convert(sb3_path, out, lang="python", scale=2, fps=30)

    assert result.entrypoint == "main.py"
    for relative in ("main.py", "runtime.py", "sb3_manifest.json", "assets/abc123.png",
                     "assets/def456.wav"):
        assert (out / relative).exists(), relative

    with zipfile.ZipFile(sb3_path) as zf:
        assert (out / "assets/abc123.png").read_bytes() == zf.read("abc123.png")
        assert (out / "assets/def456.wav").read_bytes() == zf.read("def456.wav")

    manifest = json.loads((out / "sb3_manifest.json").read_text(encoding="utf-8"))
    assert manifest["stage"]["name"] == "Stage"
    assert manifest["sprites"][0]["name"] == "Star"

    # the js-tagged sprite script was skipped with a warning
    assert any("skipped" in w for w in result.warnings)
    assert result.languages  # script id -> language map is reported back


def test_default_output_directory(sb3_path: Path, tmp_path: Path):
    copy = tmp_path / "game.sb3"
    copy.write_bytes(sb3_path.read_bytes())
    result = convert(copy)
    assert result.output_dir.name == "game-python"
    assert (result.output_dir / "main.py").exists()


@pytest.mark.slow
def test_converted_project_runs_headless(sb3_path: Path, tmp_path: Path):
    out = tmp_path / "run"
    convert(sb3_path, out)

    env = {
        **os.environ,
        "SDL_VIDEODRIVER": "dummy",
        "SDL_AUDIODRIVER": "dummy",
        "PYGAME_HIDE_SUPPORT_PROMPT": "1",
    }
    proc = subprocess.run(
        [sys.executable, "main.py", "--smoke", "15"],
        cwd=out,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    assert "SMOKE OK" in proc.stdout
    assert "Traceback" not in proc.stderr


def test_unknown_language_fails_cleanly(sb3_path: Path, tmp_path: Path, capsys):
    code = cli_main(["convert", str(sb3_path), "-o", str(tmp_path / "o"), "--lang", "cobol"])
    captured = capsys.readouterr()
    assert code == 1
    assert "unknown language" in captured.err


def test_cli_convert_reports_entrypoint(sb3_path: Path, tmp_path: Path, capsys):
    out = tmp_path / "cli-out"
    code = cli_main(["convert", str(sb3_path), "-o", str(out)])
    captured = capsys.readouterr()
    assert code == 0
    assert "entrypoint: main.py" in captured.out
    assert (out / "main.py").exists()


def test_cli_languages_lists_backends(capsys):
    code = cli_main(["languages"])
    captured = capsys.readouterr()
    assert code == 0
    assert "python" in captured.out


@pytest.mark.slow
def test_cli_run_smoke(sb3_path: Path, tmp_path: Path, capfd):
    # regression: run options (-o, --smoke) must not leak into main.py's argv
    code = cli_main(["run", str(sb3_path), "-o", str(tmp_path / "r"), "--smoke", "10"])
    captured = capfd.readouterr()
    assert code == 0, captured.err
    assert "SMOKE OK" in captured.out


def test_parse_script_lang_accepts_commas_and_rejects_garbage():
    assert parse_script_lang(["Star=js,Stage=python"]) == {"Star": "js", "Stage": "python"}
    assert parse_script_lang(None) == {}
    with pytest.raises(Sb3Error):
        parse_script_lang(["Star"])
