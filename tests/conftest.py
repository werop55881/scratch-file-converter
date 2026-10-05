"""Shared fixtures: a synthetic project.json and a synthetic .sb3 file."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from sb3conv.sb3 import load_project
from tests.helpers import sample_project


@pytest.fixture
def project_dict() -> dict:
    return sample_project()


@pytest.fixture
def project(project_dict: dict):
    return load_project(project_dict)


@pytest.fixture
def sb3_path(tmp_path: Path, project_dict: dict) -> Path:
    """A real .sb3 (zip) on disk containing the sample project plus assets."""
    path = tmp_path / "sample.sb3"
    stage_png = _png_bytes(4, 4)
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("project.json", json.dumps(project_dict))
        zf.writestr("abc123.png", stage_png)
        zf.writestr("def456.wav", _wav_bytes())
    return path


def _png_bytes(width: int, height: int) -> bytes:
    """Minimal valid RGBA PNG built with the standard library only."""
    import struct
    import zlib

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    raw = b"".join(b"\x00" + b"\xff\x00\x00\xff" * width for _ in range(height))
    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


def _wav_bytes() -> bytes:
    import io
    import wave

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(8000)
        handle.writeframes(b"\x00\x00" * 800)
    return buffer.getvalue()
