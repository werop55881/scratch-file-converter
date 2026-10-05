"""SVG support: conversion-time rasterization via resvg and capability heuristics."""

from __future__ import annotations

import re
import struct
import zlib

import resvg_py

# Supersample factor: SVGs are rendered at twice their natural size so the
# bitmap runtime stays sharp when the game window is scaled. Manifest geometry
# (rotation centers, resolution) is scaled by the same factor so display sizes
# match what the browser runtime draws from the original vector file.
RASTER_ZOOM = 2.0

# Features the vendored nanosvg renderer (C target) cannot draw. SVGs using
# any of these are rasterized at conversion time instead.
_COMPLEX_MARKERS = (b"<text", b"<image", b"filter=")

_SVG_TAG = re.compile(rb"<svg\b[^>]*", re.IGNORECASE)
_DIMENSION = re.compile(r"""(?<![-\w])(?:width|height)\s*=\s*["']\s*([0-9.eE+-]+)\s*[a-z%]*["']""")
_VIEWBOX = re.compile(r"""\bviewBox\s*=\s*["']\s*([^"']+)["']""", re.IGNORECASE)

# A 1x1 fully transparent PNG, built once: Scratch draws zero-extent SVGs as
# nothing, and a transparent pixel of any runtime draws nothing too.
_TRANSPARENT_PNG: bytes | None = None


def _transparent_png() -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    header = struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)
    raw = b"\x00\x00\x00\x00\x00"  # one transparent RGBA pixel
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


def is_complex(svg: bytes) -> bool:
    """True when the markup uses features nanosvg cannot render."""
    haystack = svg.lower()
    return any(marker in haystack for marker in _COMPLEX_MARKERS)


def has_zero_extent(svg: bytes) -> bool:
    """True when the root <svg> declares a zero width/height (draws nothing).

    Such documents (common leftovers from vector editors) make resvg raise
    "SVG has an invalid size" and make nanosvg produce an empty surface, so
    callers rasterize them to a transparent pixel instead.
    """
    match = _SVG_TAG.search(svg)
    if match is None:
        return False
    tag = match.group(0).decode("ascii", errors="ignore")
    for found in _DIMENSION.finditer(tag):
        try:
            if float(found.group(1)) == 0.0:
                return True
        except ValueError:
            pass
    viewbox = _VIEWBOX.search(tag)
    if viewbox is not None:
        parts = re.split(r"[\s,]+", viewbox.group(1).strip())
        if len(parts) == 4:
            try:
                if float(parts[2]) == 0.0 or float(parts[3]) == 0.0:
                    return True
            except ValueError:
                pass
    return False


def rasterize(svg: bytes, *, zoom: float = RASTER_ZOOM) -> bytes | None:
    """Render SVG markup to PNG bytes at ``zoom`` times its natural size.

    Zero-extent documents become a 1x1 transparent pixel (Scratch draws
    nothing for them). Returns None when the document cannot be parsed;
    callers then pass the original .svg through unchanged.
    """
    global _TRANSPARENT_PNG
    try:
        return resvg_py.svg_to_bytes(svg_string=svg.decode("utf-8", errors="replace"), zoom=zoom)
    except ValueError:
        if has_zero_extent(svg):
            if _TRANSPARENT_PNG is None:
                _TRANSPARENT_PNG = _transparent_png()
            return _TRANSPARENT_PNG
        return None
