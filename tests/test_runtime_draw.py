"""draw() must reuse cached screen surfaces: no per-frame transform.scale."""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pygame
import pytest

RUNTIME_SRC = (
    Path(__file__).resolve().parents[1] / "sb3conv" / "backends" / "python" / "runtime_src.py"
)


@pytest.fixture(scope="module")
def rt():
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
    spec = importlib.util.spec_from_file_location("sb3_runtime_draw_under_test", RUNTIME_SRC)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["sb3_runtime_draw_under_test"] = module
    spec.loader.exec_module(module)
    return module


def _png(path: Path, canvas: tuple[int, int], fill: tuple[int, int, int, int]) -> None:
    surf = pygame.Surface(canvas, pygame.SRCALPHA)
    surf.fill(fill)
    pygame.image.save(surf, str(path))


@pytest.fixture()
def runtime(rt, tmp_path: Path):
    assets = tmp_path / "assets"
    assets.mkdir()
    _png(assets / "bg.png", (480, 360), (10, 20, 30, 255))
    _png(assets / "hero.png", (16, 16), (255, 64, 64, 255))
    manifest = {
        "scale": 2,
        "stage": {"name": "Stage", "costumes": [{"name": "bg", "file": "bg.png", "cx": 240, "cy": 180}]},
        "sprites": [
            {
                "name": "Hero",
                "costumes": [{"name": "h", "file": "hero.png", "cx": 8, "cy": 8}],
                "x": 0,
                "y": 0,
                "layerOrder": 1,
            }
        ],
    }
    pygame.init()
    r = rt.Runtime(manifest, [], manifest_path=tmp_path / "sb3_manifest.json")
    r.screen = pygame.Surface((480 * r.scale, 360 * r.scale))
    return r


def test_second_draw_scales_nothing(runtime, monkeypatch):
    calls = {"scale": 0, "smoothscale": 0}
    real_scale = pygame.transform.scale
    real_smooth = pygame.transform.smoothscale

    def counting_scale(*args, **kwargs):
        calls["scale"] += 1
        return real_scale(*args, **kwargs)

    def counting_smooth(*args, **kwargs):
        calls["smoothscale"] += 1
        return real_smooth(*args, **kwargs)

    runtime.draw()
    calls["scale"] = calls["smoothscale"] = 0
    runtime.draw()
    assert calls == {"scale": 0, "smoothscale": 0}, calls


def test_cached_draw_is_pixel_identical(runtime):
    runtime.draw()
    first = pygame.image.tobytes(runtime.screen, "RGB")
    runtime.draw()
    second = pygame.image.tobytes(runtime.screen, "RGB")
    assert first == second


def test_moving_actor_reblits_without_rescaling(runtime, monkeypatch):
    runtime.draw()
    calls = {"scale": 0}
    real_scale = pygame.transform.scale

    def counting_scale(*args, **kwargs):
        calls["scale"] += 1
        return real_scale(*args, **kwargs)

    monkeypatch.setattr(pygame.transform, "scale", counting_scale)
    hero = next(a for a in runtime.layers if a.target.name == "Hero")
    hero.x = 50
    runtime.draw()
    assert calls["scale"] == 0, calls


def test_ghost_change_recomputes_screen_surface(runtime):
    runtime.draw()
    hero = next(a for a in runtime.layers if a.target.name == "Hero")
    before = runtime._prepare_screen(hero)
    hero.effects["ghost"] = 50.0
    after = runtime._prepare_screen(hero)
    assert before[0] is not after[0]
    assert after[0].get_alpha() in (127, 128)


def _red_centre(runtime, y: int) -> float | None:
    screen = runtime.screen
    xs = [x for x in range(screen.get_width()) if screen.get_at((x, y))[:3] == (255, 64, 64)]
    if not xs:
        return None
    return (min(xs) + max(xs)) / 2


def test_render_follows_live_position(runtime):
    """Moving an actor must move its blit on the very next draw.

    Regression: the prepared/screen draw caches once baked actor.x/y into
    the cached value while their key held only costume geometry, so a
    cache hit re-blitted at a stale position and sprites froze mid-motion
    (teleporting whenever the costume changed) even though the game
    logic stepped at 30fps.
    """
    hero = next(a for a in runtime.layers if a.target.name == "Hero")
    hero.x = 0
    runtime.draw()
    first = _red_centre(runtime, 350)
    hero.x = 50
    runtime.draw()
    second = _red_centre(runtime, 350)
    assert first is not None and second is not None
    assert first == pytest.approx(480, abs=1)
    assert second - first == pytest.approx(100, abs=1)  # 50 stage units * scale 2
