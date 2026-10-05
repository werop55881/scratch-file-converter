"""Pixel-perfect collision in the python runtime template (Scratch semantics)."""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pygame
import pytest

RUNTIME_SRC = (
    Path(__file__).resolve().parents[1] / "sb3conv" / "backends" / "python" / "runtime_src.py"
)


@pytest.fixture(scope="module")
def rt():
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
    spec = importlib.util.spec_from_file_location("sb3_runtime_src_under_test", RUNTIME_SRC)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["sb3_runtime_src_under_test"] = module
    spec.loader.exec_module(module)
    return module


def _blob_png(path: Path, canvas: tuple[int, int], blobs: list[tuple[int, int, int, int]]) -> None:
    surf = pygame.Surface(canvas, pygame.SRCALPHA)
    surf.fill((0, 0, 0, 0))
    for blob in blobs:
        surf.fill((255, 0, 0, 255), pygame.Rect(*blob))
    pygame.image.save(surf, str(path))


def _costume(rt, path: Path, canvas: tuple[int, int], cx: float, cy: float):
    return rt.Costume(
        {"name": path.stem, "file": path.name, "resolution": 1, "cx": cx, "cy": cy},
        path.parent,
    )


def _actor(rt, costume, x: float = 0.0, y: float = 0.0):
    target = rt.TargetDef(name="A", x=x, y=y, costumes=[costume])
    return rt.Actor(SimpleNamespace(warn_once=lambda m: None), target)


def test_tight_bounds_exclude_padding(tmp_path: Path, rt):
    _blob_png(tmp_path / "pad.png", (20, 20), [(8, 8, 4, 4)])
    costume = _costume(rt, tmp_path / "pad.png", (20, 20), 10, 10)
    actor = _actor(rt, costume)

    assert costume.tight.size == (4, 4)
    assert actor.rect() == pygame.Rect(-2, -2, 4, 4)


def test_union_bbox_gap_does_not_collide(tmp_path: Path, rt):
    # one costume with two blobs in a gap: bounding boxes overlap the gap but
    # no opaque pixel does - Scratch (and the runtime) must report no touch
    _blob_png(tmp_path / "pair.png", (40, 20), [(8, 8, 4, 4), (28, 8, 4, 4)])
    pair = _costume(rt, tmp_path / "pair.png", (40, 20), 20, 10)
    a = _actor(rt, pair, x=0, y=0)

    _blob_png(tmp_path / "one.png", (20, 20), [(8, 8, 4, 4)])
    one = _costume(rt, tmp_path / "one.png", (20, 20), 10, 10)
    b = _actor(rt, one, x=4, y=0)  # rect inside a's union bbox, no opaque pixels

    assert a.rect().colliderect(b.rect())
    assert not a.overlaps(b)

    b.x = 10  # blobs now share stage x 8..12
    assert a.overlaps(b)

    b.x = 40  # far outside
    assert not a.overlaps(b)


def test_opaque_at(tmp_path: Path, rt):
    _blob_png(tmp_path / "pad.png", (20, 20), [(8, 8, 4, 4)])
    costume = _costume(rt, tmp_path / "pad.png", (20, 20), 10, 10)
    actor = _actor(rt, costume)

    assert actor.opaque_at(0, 0)
    assert actor.opaque_at(1.9, -1.9)
    assert not actor.opaque_at(3, 0)  # inside the padded canvas, transparent
    assert not actor.opaque_at(100, 100)
