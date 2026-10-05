"""C backend: conversion output, compilation, script language routing, behavior."""

from __future__ import annotations

import json
import subprocess
import zipfile
from pathlib import Path

import pytest

from sb3conv.backends.c import build_executable, find_sdl2_home, find_zig, runtime_env
from sb3conv.convert import convert

needs_toolchain = pytest.mark.skipif(
    find_zig() is None or find_sdl2_home() is None, reason="zig/SDL2 not installed"
)


def test_convert_writes_c_files(sb3_path: Path, tmp_path: Path):
    out = tmp_path / "c"
    result = convert(sb3_path, out, lang="c")

    assert result.entrypoint == "main.c"
    for relative in (
        "main.c",
        "runtime.c",
        "runtime.h",
        "Makefile",
        "sb3_manifest.json",
        "assets/abc123.png",
        "assets/def456.wav",
    ):
        assert (out / relative).exists(), relative

    main = (out / "main.c").read_text(encoding="utf-8")
    assert '#include "runtime.h"' in main
    assert "static void script_" in main
    assert "sb_run(&PROJECT" in main
    assert 'event_whenflagclicked' in main  # the untagged stage script still runs
    assert "event_whenkeypressed" not in main  # the js-tagged sprite script is skipped

    # the sample's Star script carries a `lang: js` comment
    assert any("skipped" in warning for warning in result.warnings)

    manifest = (out / "sb3_manifest.json").read_text(encoding="utf-8")
    assert '"name": "Stage"' in manifest


def test_simple_svg_stays_vector(sb3_path: Path, tmp_path: Path, project_dict: dict):
    with zipfile.ZipFile(sb3_path) as zf:
        payload = zf.read("project.json")
    data = json.loads(payload)
    costume = data["targets"][1]["costumes"][0]
    costume.update({"name": "star", "md5ext": "star.svg", "assetId": "star"})
    with zipfile.ZipFile(sb3_path, "w") as zf:
        zf.writestr("project.json", json.dumps(data))
        zf.writestr("star.svg", b"<svg xmlns='http://www.w3.org/2000/svg'/>")
        zf.writestr("def456.wav", b"RIFF....WAVE")

    out = tmp_path / "c"
    result = convert(sb3_path, out, lang="c")

    assert not any("cannot" in warning for warning in result.warnings)
    assert (out / "assets" / "star.svg").exists()
    main = (out / "main.c").read_text(encoding="utf-8")
    assert '.file = "star.svg"' in main


def test_complex_svg_is_rasterized(sb3_path: Path, tmp_path: Path, project_dict: dict):
    with zipfile.ZipFile(sb3_path) as zf:
        payload = zf.read("project.json")
    data = json.loads(payload)
    costume = data["targets"][1]["costumes"][0]
    costume.update(
        {
            "name": "star",
            "md5ext": "star.svg",
            "assetId": "star",
            "rotationCenterX": 10,
            "rotationCenterY": 20,
        }
    )
    svg = (
        b"<svg xmlns='http://www.w3.org/2000/svg' width='40' height='40'>"
        b"<text x='2' y='20'>hi</text></svg>"
    )
    with zipfile.ZipFile(sb3_path, "w") as zf:
        zf.writestr("project.json", json.dumps(data))
        zf.writestr("star.svg", svg)
        zf.writestr("def456.wav", b"RIFF....WAVE")

    out = tmp_path / "c"
    result = convert(sb3_path, out, lang="c")

    assert not any("cannot" in warning for warning in result.warnings)
    png = (out / "assets" / "star.png").read_bytes()
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert not (out / "assets" / "star.svg").exists()
    main = (out / "main.c").read_text(encoding="utf-8")
    assert '.file = "star.png"' in main
    assert ".cx = 20.0, .cy = 40.0" in main  # pixel-space center x2; init divides by resolution
    assert ".resolution = 2" in main  # doubled with the supersampled raster


def test_script_lang_override_skips_stage_script(sb3_path: Path, tmp_path: Path):
    out = tmp_path / "c"
    result = convert(sb3_path, out, lang="c", script_lang=["Stage=python"])

    assert sum("skipped" in warning for warning in result.warnings) == 2  # both scripts
    main = (out / "main.c").read_text(encoding="utf-8")
    assert "event_whenflagclicked" not in main
    assert "#define SB_SCRIPT_COUNT 0" in main


@needs_toolchain
def test_generated_main_c_compiles(sb3_path: Path, tmp_path: Path):
    out = tmp_path / "c"
    convert(sb3_path, out, lang="c")

    proc = subprocess.run(
        [find_zig(), "cc", "-c", "-std=c11", "-Wall", "main.c", "-o", "main.o"],
        cwd=out,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stderr == "", proc.stderr


@needs_toolchain
def test_runtime_c_compiles_clean(tmp_path: Path):
    source = Path(__file__).resolve().parents[1] / "sb3conv" / "backends" / "c"
    (tmp_path / "runtime.c").write_bytes((source / "runtime_src.c").read_bytes())
    (tmp_path / "runtime.h").write_bytes((source / "runtime_src.h").read_bytes())
    for name in ("nanosvg.h", "nanosvgrast.h"):
        (tmp_path / name).write_bytes((source / "vendor" / "nanosvg" / name).read_bytes())

    proc = subprocess.run(
        [
            find_zig(),
            "cc",
            "-c",
            "-std=c11",
            "-Wall",
            f"-I{find_sdl2_home() / 'include'}",
            "runtime.c",
            "-o",
            "runtime.o",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert "warning:" not in proc.stderr, proc.stderr


def test_game_converts_to_c_without_warnings(tmp_path: Path):
    game = Path(__file__).resolve().parents[1] / "game" / "star-game.sb3"
    if not game.exists():
        pytest.skip("game project not built")

    out = tmp_path / "game-c"
    result = convert(game, out, lang="c")

    assert result.warnings == []
    main = (out / "main.c").read_text(encoding="utf-8")
    assert main.count("static void script_") == 10
    assert "#define SB_SCRIPT_COUNT 10" in main
    assert (out / "assets").is_dir()


# ----------------------------------------------------------------------
# behavior: build the real game once, then drive it with --smoke/--set/--click
# ----------------------------------------------------------------------
@pytest.fixture(scope="module")
def game_exe(tmp_path_factory: pytest.TempPathFactory) -> Path:
    if find_zig() is None or find_sdl2_home() is None:
        pytest.skip("zig/SDL2 not installed")
    game = Path(__file__).resolve().parents[1] / "game" / "star-game.sb3"
    if not game.exists():
        pytest.skip("game project not built")
    out = tmp_path_factory.mktemp("game-c") / "c"
    result = convert(game, out, lang="c")
    assert result.warnings == [], result.warnings
    return build_executable(out)


def run_game(exe: Path, *args: str) -> tuple[dict[str, str], dict[str, int]]:
    """Run the game headless with --smoke; parse SBVAR/SBPOP from --dump."""
    proc = subprocess.run(
        [str(exe), "--smoke", *args],
        cwd=exe.parent,
        capture_output=True,
        text=True,
        timeout=180,
        env=runtime_env(smoke=True),
        check=False,
    )
    assert proc.returncode == 0, f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    assert "SMOKE OK" in proc.stdout, proc.stdout
    return parse_dump(proc.stdout)


def parse_dump(stdout: str) -> tuple[dict[str, str], dict[str, int]]:
    values: dict[str, str] = {}
    population: dict[str, int] = {}
    for line in stdout.splitlines():
        parts = line.split(maxsplit=3)
        if len(parts) == 4 and parts[0] == "SBVAR":
            values[f"{parts[1]}.{parts[2]}"] = parts[3]
        elif len(parts) == 3 and parts[0] == "SBPOP":
            population[parts[1]] = int(parts[2])
    return values, population


@pytest.mark.slow
def test_c_population_after_60_frames(game_exe: Path):
    values, population = run_game(game_exe, "60", "--dump")
    assert population == {"Stage": 1, "BgStar": 29, "Planet": 1, "Star": 1, "Shop": 4}
    assert values["Stage.starDust"] == "0"


@pytest.mark.slow
def test_c_income_ticks_every_second(game_exe: Path):
    values, _ = run_game(game_exe, "65", "--set", "perSecond=5", "--dump")
    assert values["Stage.starDust"] == "10"  # ticks at frames 31 and 61


@pytest.mark.slow
def test_c_star_click_earns_star_dust(game_exe: Path):
    values, _ = run_game(game_exe, "5", "--click", "0,0,1", "--dump")
    assert values["Stage.starDust"] == "1"


@pytest.mark.slow
def test_c_buying_first_planet_costs_dust_and_spawns_orbit(game_exe: Path):
    values, population = run_game(
        game_exe, "2", "--set", "starDust=100", "--click", "-150,100,2", "--dump"
    )
    assert values["Stage.starDust"] == "90"
    assert values["Stage.planetsBought"] == "1"
    assert values["Stage.shopIndex"] == "1"
    assert values["Stage.perSecond"] == "1"
    assert values["Stage.spawnIdx"] == "1"
    assert population["Planet"] == 2


@pytest.mark.slow
def test_c_upgrade_doubles_click_and_income(game_exe: Path):
    values, population = run_game(
        game_exe,
        "2",
        "--set",
        "starDust=25000",
        "--set",
        "shopIndex=5",
        "--set",
        "upgraded=0",
        "--set",
        "clickPower=1",
        "--set",
        "perSecond=100",
        "--click",
        "-150,100,2",
        "--dump",
    )
    assert values["Stage.starDust"] == "5000"
    assert values["Stage.upgraded"] == "1"
    assert values["Stage.clickPower"] == "2"
    assert values["Stage.perSecond"] == "200"
    assert values["Stage.planetsBought"] == "0"
    assert population["Planet"] == 1


@pytest.mark.slow
def test_c_cannot_afford_planet(game_exe: Path):
    values, population = run_game(
        game_exe, "2", "--set", "starDust=5", "--click", "-150,100,2", "--dump"
    )
    assert values["Stage.starDust"] == "5"
    assert values["Stage.planetsBought"] == "0"
    assert population["Planet"] == 1
