"""End-to-end behaviour of the generated star game: build -> convert -> simulate."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from game.make_star_game import build_project
from sb3conv.convert import convert


@pytest.fixture(scope="module")
def star_game(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    """Build the star game .sb3 once and convert it without warnings."""
    base = tmp_path_factory.mktemp("star-game")
    sb3 = base / "star-game.sb3"
    build_project().write(sb3)
    out = base / "out"
    result = convert(sb3, out)
    assert result.warnings == [], result.warnings
    assert result.entrypoint == "main.py"
    return sb3, out


@pytest.fixture(scope="module")
def new_runtime(star_game: tuple[Path, Path]) -> Callable[[], Any]:
    """Factory producing a fresh headless runtime for each test."""
    _sb3, out = star_game
    os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    sys.path.insert(0, str(out))
    try:
        spec = importlib.util.spec_from_file_location("star_game_main", out / "main.py")
        assert spec is not None and spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        manifest = json.loads((out / "sb3_manifest.json").read_text(encoding="utf-8"))

        import pygame
        from runtime import Runtime

        pygame.init()

        def make() -> Any:
            return Runtime(manifest, mod.SCRIPTS, manifest_path=out / "sb3_manifest.json")

        yield make
    finally:
        sys.path.remove(str(out))


def live_clones(rt: Any, sprite: str) -> list[Any]:
    return [a for a in rt.actors if a.is_clone and not a.dead and a.target.name == sprite]


def fire_click(rt: Any, sprite: str, slot: int | None = None) -> Any:
    """Spawn 'when this sprite clicked' on the topmost matching visible actor."""
    for actor in reversed(list(rt.actors)):
        if actor.dead or not actor.visible or actor.target.name != sprite:
            continue
        if slot is not None and (not actor.is_clone or actor.vars.get("slotIdx") != slot):
            continue
        for reg in rt.routes["click"].get(sprite, []):
            rt.spawn(reg, actor)
        return actor
    return None


def test_flag_spawns_stable_populations(new_runtime: Callable[[], Any]) -> None:
    rt = new_runtime()
    rt.green_flag()
    # wait-free flag scripts run synchronously at event time
    assert len(live_clones(rt, "BgStar")) == 28
    assert len(live_clones(rt, "Shop")) == 3
    assert not live_clones(rt, "Planet")

    for _ in range(150):
        rt.step()

    # no runaway spawning: counts stay exactly at design values
    assert len(live_clones(rt, "BgStar")) == 28
    assert len(live_clones(rt, "Shop")) == 3
    assert not live_clones(rt, "Planet")
    assert rt.warned == set()
    assert rt.errors == []


def test_star_click_earns_star_dust(new_runtime: Callable[[], Any]) -> None:
    rt = new_runtime()
    rt.green_flag()
    assert rt.vars["starDust"] == 0

    assert fire_click(rt, "Star") is not None
    rt.step()
    assert rt.vars["starDust"] == 1


def test_buying_first_planet_costs_dust_and_spawns_orbit(
    new_runtime: Callable[[], Any],
) -> None:
    rt = new_runtime()
    rt.green_flag()
    rt.step()
    rt.vars["starDust"] = 100

    assert fire_click(rt, "Shop", slot=0) is not None
    rt.step()

    assert rt.vars["starDust"] == 90
    assert rt.vars["planetsBought"] == 1
    assert rt.vars["shopIndex"] == 1
    assert rt.vars["perSecond"] == 1
    assert rt.vars["spawnIdx"] == 1

    planets = live_clones(rt, "Planet")
    assert len(planets) == 1
    planet = planets[0]
    assert planet.visible
    assert 95 <= planet.vars["myRadius"] <= 150
    assert planet.vars["mySpeed"] in (1, 2, 3, 4)


def test_income_ticks_every_second(new_runtime: Callable[[], Any]) -> None:
    rt = new_runtime()
    rt.green_flag()
    rt.vars["perSecond"] = 5
    for _ in range(65):
        rt.step()
    # ticks at frames 31 and 61
    assert rt.vars["starDust"] == 10


def test_upgrade_doubles_click_and_income(new_runtime: Callable[[], Any]) -> None:
    rt = new_runtime()
    rt.green_flag()
    rt.step()
    rt.vars.update(starDust=25000, shopIndex=5, upgraded=0, clickPower=1, perSecond=100)

    fire_click(rt, "Shop", slot=0)
    rt.step()
    assert rt.vars["upgraded"] == 1
    assert rt.vars["clickPower"] == 2
    assert rt.vars["perSecond"] == 200
    assert rt.vars["starDust"] == 5000
    assert rt.vars["planetsBought"] == 0

    fire_click(rt, "Shop", slot=0)
    rt.step()
    assert rt.vars["upgraded"] == 1
    assert rt.vars["clickPower"] == 2
    assert rt.vars["starDust"] == 5000


def test_cannot_afford_planet(new_runtime: Callable[[], Any]) -> None:
    rt = new_runtime()
    rt.green_flag()
    rt.step()
    rt.vars["starDust"] = 5

    fire_click(rt, "Shop", slot=0)
    rt.step()
    assert rt.vars["starDust"] == 5
    assert rt.vars["planetsBought"] == 0
    assert not live_clones(rt, "Planet")


def test_supernova_pays_bonus_and_replaces_star(new_runtime: Callable[[], Any]) -> None:
    rt = new_runtime()
    rt.green_flag()
    for _ in range(2):
        rt.step()
    stars = live_clones(rt, "BgStar")
    assert len(stars) == 28
    doomed = stars[0]
    doomed.vars["mySize"] = 141.0

    rt.step()
    assert rt.vars["starDust"] == 10  # 10 * clickPower bonus
    assert len(live_clones(rt, "BgStar")) == 29  # replacement spawned

    for _ in range(8):
        rt.step()
    assert doomed.dead
    assert len(live_clones(rt, "BgStar")) == 28  # exploded star deleted itself
    assert rt.warned == set()


def test_sb3_structure_is_scratch_shaped(star_game: tuple[Path, Path]) -> None:
    sb3, _out = star_game
    with zipfile.ZipFile(sb3) as zf:
        names = set(zf.namelist())
        project = json.loads(zf.read("project.json"))

        for target in project["targets"]:
            for costume in target.get("costumes", []):
                assert costume["md5ext"] in names, costume["md5ext"]
                assert costume["rotationCenterX"] >= 0
            for sound in target.get("sounds", []):
                assert sound["md5ext"] in names, sound["md5ext"]
            for block_id, block in target["blocks"].items():
                if not isinstance(block, dict):
                    continue
                assert isinstance(block["topLevel"], bool)
                assert isinstance(block["shadow"], bool)
                for entry in (block.get("inputs") or {}).values():
                    assert entry[0] in (1, 2, 3), (block_id, entry)
                    # Scratch's schema wants payloads to be a block id string
                    # or a compressed primitive literal ([4..13, ...]) - a raw
                    # input entry like [1, id] here is rejected at load time
                    for payload in entry[1:]:
                        valid = payload is None or isinstance(payload, str) or (
                            isinstance(payload, list)
                            and isinstance(payload[0], int)
                            and 4 <= payload[0] <= 13
                        )
                        assert valid, (block_id, entry)
                for field_value in (block.get("fields") or {}).values():
                    assert isinstance(field_value, list) and 1 <= len(field_value) <= 2

        for monitor in project.get("monitors", []):
            assert monitor["opcode"].startswith("data_")
            assert "VARIABLE" in monitor["params"]
