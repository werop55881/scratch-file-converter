"""Build a playable artifact from a converted project directory.

- ``python``   -> one .exe via PyInstaller (onefile, windowed)
- ``c``        -> one .exe via zig + SDL2 (the backend's normal build)
- ``javascript`` -> one self-contained .html with every asset inlined, so it
  runs from a double click without a server (and without canvas tainting)

``ToolchainMissing`` (a :class:`BackendError`) signals that an optional
toolchain is not installed; callers may turn that into a warning instead of a
hard failure.
"""

from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from sb3conv.errors import BackendError

_DATA_URI_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".svg": "image/svg+xml",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
    ".ogg": "audio/ogg",
}


class ToolchainMissing(BackendError):
    """The toolchain needed for the requested build is not installed."""


def _exe_name(name: str) -> str:
    return name + (".exe" if os.name == "nt" else "")


def _runs(command: list[str]) -> bool:
    try:
        proc = subprocess.run(command, capture_output=True, timeout=30, check=False)
    except OSError:
        return False
    return proc.returncode == 0


def _python_build_command() -> list[str] | None:
    """Interpreter prefix that has PyInstaller importable, or None."""
    candidates: list[list[str]] = []
    if not getattr(sys, "frozen", False):
        candidates.append([sys.executable])
    for name in ("python", "python3"):
        executable = shutil.which(name)
        if executable:
            candidates.append([executable])
    py_launcher = shutil.which("py")
    if py_launcher:
        candidates.append([py_launcher, "-3"])
    seen: set[tuple[str, ...]] = set()
    for command in candidates:
        key = tuple(command)
        if key in seen:
            continue
        seen.add(key)
        if _runs([*command, "-c", "import PyInstaller"]):
            return command
    return None


_VERSION_TEMPLATE = """# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=(0, 1, 0, 0),
    prodvers=(0, 1, 0, 0),
    mask=0x3F, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)
  ),
  kids=[
    StringFileInfo(
      [StringTable('040904B0', [
        StringStruct('CompanyName', 'Scratch File Converter'),
        StringStruct('FileDescription', %(desc)r),
        StringStruct('FileVersion', '0.1.0.0'),
        StringStruct('InternalName', %(internal)r),
        StringStruct('OriginalFilename', %(original)r),
        StringStruct('ProductName', %(desc)r),
        StringStruct('ProductVersion', '0.1.0.0'),
      ])]
    ),
    VarFileInfo([VarStruct('Translation', [1033, 1200])]),
  ]
)
"""


def _write_version_file(out_dir: Path, name: str) -> str:
    """Version resource for the .exe (metadata helps antivirus reputation)."""
    path = out_dir / "sb3conv_version_info.txt"
    path.write_text(
        _VERSION_TEMPLATE
        % {"desc": name, "internal": name, "original": _exe_name(name)},
        encoding="utf-8",
    )
    return str(path)


def build_python_exe(out_dir: Path, *, name: str, console: bool = False) -> Path:
    """Package ``out_dir`` (a converted python project) into a single .exe."""
    # resolve(): PyInstaller resolves relative --add-data paths against its
    # temp spec directory, not the working directory, so a relative out_dir
    # would be looked up in the wrong place.
    out_dir = Path(out_dir).resolve()
    if not (out_dir / "main.py").is_file():
        raise BackendError(f"{out_dir} does not look like a converted python project")
    command_prefix = _python_build_command()
    if command_prefix is None:
        raise ToolchainMissing(
            "building an .exe needs Python with PyInstaller (pip install pyinstaller)"
        )
    exe = out_dir / _exe_name(name)
    with tempfile.TemporaryDirectory(prefix="sb3conv-pyi-") as tmp:
        command = [
            *command_prefix,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--onefile",
            "--console" if console else "--windowed",
            "--name",
            name,
            "--version-file",
            _write_version_file(out_dir, name),
            "--distpath",
            str(out_dir),
            "--workpath",
            tmp,
            "--specpath",
            tmp,
            "--add-data",
            f"{out_dir / 'sb3_manifest.json'}{os.pathsep}.",
            "--add-data",
            f"{out_dir / 'assets'}{os.pathsep}assets",
            str(out_dir / "main.py"),
        ]
        # cwd=tmp: PyInstaller refuses to run when the working directory is a
        # system folder (e.g. C:\Windows\system32, which is what you get when
        # the GUI is launched from the Start menu search), and nothing in the
        # command relies on the caller's working directory.
        proc = subprocess.run(
            command, cwd=tmp, capture_output=True, text=True, check=False
        )
    if proc.returncode != 0:
        tail = "\n".join((proc.stderr or proc.stdout or "").splitlines()[-40:])
        raise BackendError(
            f"PyInstaller failed - does that interpreter have pygame-ce installed?\n{tail}"
        )
    if not exe.exists():
        raise BackendError(f"PyInstaller reported success but {exe} is missing")
    return exe


def build_c_app(out_dir: Path, *, name: str) -> Path:
    """Compile ``out_dir`` (a converted C project) into a single .exe."""
    from sb3conv.backends.c import build_executable, find_sdl2_home, find_zig

    out_dir = Path(out_dir)
    if not (out_dir / "main.c").is_file():
        raise BackendError(f"{out_dir} does not look like a converted C project")
    if find_zig() is None:
        raise ToolchainMissing(
            "building an .exe needs zig; install it (https://ziglang.org) or set ZIG"
        )
    if find_sdl2_home() is None:
        raise ToolchainMissing(
            "building an .exe needs SDL2 development files; set SDL2_HOME"
        )
    return build_executable(out_dir, exe_name=_exe_name(name))


def _script_safe(text: str) -> str:
    """Keep literal ``</script`` sequences inside inlined JS from ending the tag."""
    return re.sub(
        r"</script",
        lambda match: match.group(0).replace("</", "<\\/"),
        text,
        flags=re.IGNORECASE,
    )


def build_js_app(out_dir: Path, *, name: str) -> Path:
    """Inline runtime, scripts and every asset into one self-contained .html."""
    out_dir = Path(out_dir)
    index = out_dir / "index.html"
    runtime = out_dir / "runtime.js"
    main = out_dir / "main.js"
    for required in (index, runtime, main):
        if not required.is_file():
            raise BackendError(f"{out_dir} does not look like a converted javascript project")

    assets: dict[str, str] = {}
    assets_dir = out_dir / "assets"
    if assets_dir.is_dir():
        for path in sorted(assets_dir.iterdir()):
            if path.is_file():
                mime = _DATA_URI_TYPES.get(path.suffix.lower(), "application/octet-stream")
                encoded = base64.b64encode(path.read_bytes()).decode("ascii")
                assets[path.name] = f"data:{mime};base64,{encoded}"

    html = index.read_text(encoding="utf-8")
    inline_runtime = _script_safe(runtime.read_text(encoding="utf-8"))
    inline_main = _script_safe(main.read_text(encoding="utf-8"))
    assets_script = f"window.__SB3_ASSETS = {json.dumps(assets, ensure_ascii=False)};"
    html, count1 = re.subn(
        r'<script src="runtime\.js"></script>',
        lambda _match: f"<script>{inline_runtime}</script>",
        html,
    )
    html, count2 = re.subn(
        r'<script src="main\.js"></script>',
        lambda _match: f"<script>{assets_script}\n{inline_main}</script>",
        html,
    )
    if count1 != 1 or count2 != 1:
        raise BackendError(f"unexpected index.html layout in {out_dir}")
    target = out_dir / f"{name}.html"
    target.write_text(html, encoding="utf-8")
    return target


def build_app(out_dir: Path | str, *, lang: str, name: str, console: bool = False) -> Path:
    """Build the playable artifact for a converted project; returns its path."""
    out_dir = Path(out_dir)
    if lang == "python":
        return build_python_exe(out_dir, name=name, console=console)
    if lang == "c":
        return build_c_app(out_dir, name=name)
    if lang in ("js", "javascript"):
        return build_js_app(out_dir, name=name)
    raise BackendError(f"no build step for target {lang!r}")
