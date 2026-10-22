"""In-browser conversion glue for the static web app (Pyodide).

The web app loads this module inside the browser's Python runtime; the
uploaded .sb3 never leaves the user's machine. Only the standard library is
used here so the wheel installs into Pyodide without native dependencies
(no resvg, no pygame - see :func:`sb3conv.svg.rasterize`'s lazy import).
"""

from __future__ import annotations

import io
import json
import re
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from sb3conv.convert import convert
from sb3conv.errors import Sb3Error

VALID_LANGS = ("python", "javascript", "c", "typescript", "lua", "godot")

# builds that work in the browser (pure Python/zip, no local toolchains)
_BROWSER_BUILDS = ("javascript", "lua")

_MAX_NAME = 64


def _safe_name(name: str) -> str:
    base = re.split(r"[/\\]+", str(name or ""))[-1]
    cleaned = re.sub(r"[^\w .-]+", "_", base).strip(" ._")
    return cleaned[:_MAX_NAME] or "project"


def _zip_tree(out: Path) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(out.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(out).as_posix())
    return buffer.getvalue()


def web_convert(
    data: bytes,
    *,
    lang: str = "javascript",
    scale: int = 2,
    fps: int = 30,
    build: bool = True,
    project_name: str = "project",
) -> dict[str, Any]:
    """Convert an uploaded .sb3 in a temp workspace.

    Returns a bridge-friendly dict (``.toJs`` on the Python side):
    ``files`` {relpath: bytes}, ``zip`` (bytes of the full project archive),
    ``html`` (single-file play page bytes or None), ``entrypoint``,
    ``log`` (progress lines), ``warnings`` (list[str]), ``name``.
    """
    if lang not in VALID_LANGS:
        raise Sb3Error(f"unknown target {lang!r}; pick one of {', '.join(VALID_LANGS)}")
    if not data:
        raise Sb3Error("the uploaded file is empty")
    name = _safe_name(project_name)

    with tempfile.TemporaryDirectory(prefix="sb3conv-web-") as tmp:
        work = Path(tmp)
        src = work / f"{name}.sb3"
        src.write_bytes(data)
        out = work / "out"
        log: list[str] = []
        result = convert(
            src,
            out,
            lang=lang,
            scale=scale,
            fps=fps,
            # .exe builds need local toolchains; the single-file html (and the
            # pure-zip .love archive) are toolchain-free and work in the browser.
            build_exe=build and lang in _BROWSER_BUILDS,
            progress=log.append,
        )
        files = {
            path.relative_to(out).as_posix(): path.read_bytes()
            for path in sorted(out.rglob("*"))
            if path.is_file()
        }
        html: bytes | None = None
        artifact = result.artifact
        if artifact is not None and artifact.is_file() and artifact.suffix == ".html":
            html = artifact.read_bytes()
        return {
            "files": files,
            "zip": _zip_tree(out),
            "html": html,
            "entrypoint": result.entrypoint,
            "log": log,
            "warnings": list(result.warnings),
            "name": name,
        }


def web_run_job(upload_bytes: Any, job_json: str) -> dict[str, Any]:
    """Worker entry point: bytes from JS + a JSON job description."""
    job = json.loads(job_json)
    return web_convert(
        bytes(upload_bytes),
        lang=str(job.get("lang") or "javascript"),
        scale=int(job.get("scale") or 2),
        fps=int(job.get("fps") or 30),
        build=bool(job.get("build", True)),
        project_name=str(job.get("name") or "project"),
    )
