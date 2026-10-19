"""Browser bridge: web_convert produces downloadable files, zip and play html."""

from __future__ import annotations

import io
import json
import sys
import zipfile
from pathlib import Path

import pytest

from sb3conv.errors import Sb3Error
from sb3conv.svg import rasterize
from sb3conv.web import _safe_name, web_convert, web_run_job

_ZERO_EXTENT = b'<svg xmlns="http://www.w3.org/2000/svg" width="0" height="0"></svg>'
_PLAIN_SVG = b'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"></svg>'


def test_javascript_target_yields_play_html_and_zip(sb3_path: Path):
    data = sb3_path.read_bytes()
    result = web_convert(data, lang="javascript", project_name="fighter")
    assert set(result["files"]) >= {
        "index.html",
        "runtime.js",
        "main.js",
        "original.sb3",
    }
    assert result["entrypoint"] == "index.html"
    assert result["name"] == "fighter"
    assert result["html"] is not None
    assert b"window.__SB3_ASSETS" in result["html"]
    assert b"<script src=" not in result["html"]
    assert result["log"] == ["building single-file html..."]
    assert result["warnings"] == []
    with zipfile.ZipFile(io.BytesIO(result["zip"])) as archive:
        names = archive.namelist()
        assert "original.sb3" in names
        assert archive.read("original.sb3") == data
        assert "main.js" in names


def test_python_target_files_and_manifest(sb3_path: Path):
    result = web_convert(
        sb3_path.read_bytes(), lang="python", scale=4, fps=24, project_name="My Game!"
    )
    assert "main.py" in result["files"]
    assert "runtime.py" in result["files"]
    assert result["html"] is None
    manifest = json.loads(result["files"]["sb3_manifest.json"].decode("utf-8"))
    assert manifest["scale"] == 4
    assert manifest["fps"] == 24
    assert result["name"] == "My Game"


def test_c_target_files(sb3_path: Path):
    result = web_convert(sb3_path.read_bytes(), lang="c")
    assert "main.c" in result["files"]
    assert result["html"] is None


def test_web_run_job_json_bridge(sb3_path: Path):
    payload = memoryview(sb3_path.read_bytes())
    job = json.dumps({"lang": "javascript", "scale": 1, "fps": 30, "name": "bridge"})
    result = web_run_job(payload, job)
    assert result["name"] == "bridge"
    assert result["html"] is not None


def test_rejects_bad_input(tmp_path: Path):
    with pytest.raises(Sb3Error, match="unknown target"):
        web_convert(b"not used", lang="rust")
    with pytest.raises(Sb3Error, match="empty"):
        web_convert(b"", lang="javascript")


def test_safe_name_strips_path_parts():
    assert _safe_name("../../evil name") == "evil name"
    assert _safe_name("") == "project"
    assert _safe_name("a" * 200) == "a" * 64


def test_rasterize_without_resvg_keeps_graceful_paths(monkeypatch):
    monkeypatch.setitem(sys.modules, "resvg_py", None)
    assert rasterize(_PLAIN_SVG) is None
    transparent = rasterize(_ZERO_EXTENT)
    assert transparent is not None and transparent.startswith(b"\x89PNG")
