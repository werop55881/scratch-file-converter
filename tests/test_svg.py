"""SVG handling across the backends: rasterization, passthrough, geometry."""

from __future__ import annotations

import json
import struct
import zipfile
from pathlib import Path

from sb3conv.convert import convert
from sb3conv.svg import RASTER_ZOOM, has_zero_extent, is_complex, rasterize

SIMPLE_SVG = (
    b"<svg xmlns='http://www.w3.org/2000/svg' width='40' height='40'>"
    b"<rect x='0' y='0' width='40' height='40' fill='#ff0000'/></svg>"
)
TEXT_SVG = (
    b"<svg xmlns='http://www.w3.org/2000/svg' width='40' height='40'>"
    b"<text x='4' y='20'>hi</text></svg>"
)
ZERO_SVG = (
    b"<svg xmlns='http://www.w3.org/2000/svg' width='0' height='0' viewBox='0,0,0,0'></svg>"
)
VIEWBOX_ONLY_SVG = (
    b"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0,0,0,0'></svg>"
)


def _repack_with_svg(sb3_path: Path, svg: bytes) -> None:
    with zipfile.ZipFile(sb3_path) as zf:
        data = json.loads(zf.read("project.json"))
    costume = data["targets"][1]["costumes"][0]
    costume.update(
        {
            "name": "star",
            "md5ext": "star.svg",
            "assetId": "star",
            "rotationCenterX": 10,
            "rotationCenterY": 20,
            "bitmapResolution": 1,
        }
    )
    with zipfile.ZipFile(sb3_path, "w") as zf:
        zf.writestr("project.json", json.dumps(data))
        zf.writestr("star.svg", svg)
        zf.writestr("def456.wav", b"RIFF....WAVE")


def _png_size(png: bytes) -> tuple[int, int]:
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    return struct.unpack(">II", png[16:24])


def test_python_rasterizes_svg_costume(sb3_path: Path, tmp_path: Path, project_dict: dict):
    _repack_with_svg(sb3_path, SIMPLE_SVG)

    out = tmp_path / "py"
    result = convert(sb3_path, out, lang="python")

    assert not any("svg" in warning.lower() for warning in result.warnings)
    png = (out / "assets" / "star.png").read_bytes()
    width, height = _png_size(png)
    assert (width, height) == (40 * RASTER_ZOOM, 40 * RASTER_ZOOM)
    assert not (out / "assets" / "star.svg").exists()

    manifest = json.loads((out / "sb3_manifest.json").read_text(encoding="utf-8"))
    costume = manifest["sprites"][0]["costumes"][0]
    assert costume["file"] == "star.png"
    assert costume["cx"] == 10 * RASTER_ZOOM
    assert costume["cy"] == 20 * RASTER_ZOOM
    assert costume["resolution"] == RASTER_ZOOM


def test_python_keeps_svg_when_rasterize_fails(
    sb3_path: Path, tmp_path: Path, project_dict: dict, monkeypatch
):
    _repack_with_svg(sb3_path, SIMPLE_SVG)
    monkeypatch.setattr("sb3conv.backends.python.rasterize", lambda *args, **kwargs: None)

    out = tmp_path / "py"
    result = convert(sb3_path, out, lang="python")

    assert (out / "assets" / "star.svg").exists()
    assert not (out / "assets" / "star.png").exists()
    assert any(
        "could not be rasterized" in warning and "pygame" in warning
        for warning in result.warnings
    )
    manifest = json.loads((out / "sb3_manifest.json").read_text(encoding="utf-8"))
    costume = manifest["sprites"][0]["costumes"][0]
    assert costume["file"] == "star.svg"
    assert costume["cx"] == 10  # failed raster keeps the original geometry
    assert costume["resolution"] == 1


def test_javascript_keeps_svg(sb3_path: Path, tmp_path: Path, project_dict: dict):
    _repack_with_svg(sb3_path, SIMPLE_SVG)

    out = tmp_path / "js"
    result = convert(sb3_path, out, lang="javascript")

    assert not any("svg" in warning.lower() for warning in result.warnings)
    assert (out / "assets" / "star.svg").read_bytes() == SIMPLE_SVG
    assert not (out / "assets" / "star.png").exists()
    main_js = (out / "main.js").read_text(encoding="utf-8")
    assert '"file": "star.svg"' in main_js


def test_rasterize_returns_png():
    png = rasterize(SIMPLE_SVG)
    assert png is not None
    assert _png_size(png) == (40 * RASTER_ZOOM, 40 * RASTER_ZOOM)


def test_rasterize_invalid_svg_returns_none():
    assert rasterize(b"<not-svg") is None


def test_is_complex_detects_unsupported_features():
    assert not is_complex(SIMPLE_SVG)
    assert is_complex(TEXT_SVG)
    assert is_complex(b"<svg><image href='x.png'/></svg>")
    assert is_complex(b"<svg filter='url(#f)'><rect/></svg>")
    assert is_complex(b"<svg><TEXT>x</TEXT></svg>")


def test_has_zero_extent():
    assert has_zero_extent(ZERO_SVG)
    assert has_zero_extent(VIEWBOX_ONLY_SVG)
    assert not has_zero_extent(SIMPLE_SVG)
    assert not has_zero_extent(b"<svg viewBox='0,0,40,40'></svg>")


def test_rasterize_zero_extent_returns_transparent_pixel():
    png = rasterize(ZERO_SVG)
    assert png is not None
    assert _png_size(png) == (1, 1)


def test_python_converts_zero_extent_svg_without_warning(
    sb3_path: Path, tmp_path: Path, project_dict: dict
):
    _repack_with_svg(sb3_path, ZERO_SVG)

    out = tmp_path / "py"
    result = convert(sb3_path, out, lang="python")

    assert not any("svg" in warning.lower() for warning in result.warnings)
    png = (out / "assets" / "star.png").read_bytes()
    assert _png_size(png) == (1, 1)
    assert not (out / "assets" / "star.svg").exists()


def test_c_rasterizes_zero_extent_svg(sb3_path: Path, tmp_path: Path, project_dict: dict):
    _repack_with_svg(sb3_path, ZERO_SVG)

    out = tmp_path / "c"
    result = convert(sb3_path, out, lang="c")

    assert not any("svg" in warning.lower() for warning in result.warnings)
    png = (out / "assets" / "star.png").read_bytes()
    assert _png_size(png) == (1, 1)
    assert not (out / "assets" / "star.svg").exists()


def test_javascript_keeps_zero_extent_svg(sb3_path: Path, tmp_path: Path, project_dict: dict):
    _repack_with_svg(sb3_path, ZERO_SVG)

    out = tmp_path / "js"
    result = convert(sb3_path, out, lang="javascript")

    assert not any("svg" in warning.lower() for warning in result.warnings)
    assert (out / "assets" / "star.svg").read_bytes() == ZERO_SVG
    assert not (out / "assets" / "star.png").exists()
