"""Command line interface: ``sb3conv convert`` and ``sb3conv run``."""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

from sb3conv.backends import available_languages, get_backend
from sb3conv.convert import convert
from sb3conv.errors import BackendError, Sb3Error

PROG = "sb3conv"
_WATCH_POLL_SECONDS = 0.5


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("input", help="path to the .sb3 project")
    parser.add_argument("-o", "--output", default=None, help="output directory")
    parser.add_argument("--lang", default="python", help="target language (default: python)")
    parser.add_argument("--scale", type=int, default=2, help="window scale factor (default: 2)")
    parser.add_argument("--fps", type=int, default=30, help="frame rate (default: 30)")
    parser.add_argument(
        "--script-lang",
        action="append",
        default=[],
        metavar="Sprite=LANG",
        help="force a language for one sprite's scripts (repeatable)",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=PROG, description="Convert Scratch .sb3 projects")
    sub = parser.add_subparsers(dest="command")

    convert_parser = sub.add_parser("convert", help="convert an .sb3 to a runnable project")
    _add_common(convert_parser)
    convert_parser.add_argument(
        "--exe",
        action="store_true",
        help="also build a playable app (.exe for python/c, one .html for js)",
    )
    convert_parser.add_argument(
        "--watch",
        action="store_true",
        help="keep re-converting when the .sb3 changes (Ctrl+C to stop)",
    )

    run_parser = sub.add_parser("run", help="convert an .sb3 and run it")
    _add_common(run_parser)
    run_parser.add_argument(
        "--smoke", type=int, default=0, metavar="N", help="run N frames headless, then exit"
    )

    sub.add_parser("languages", help="list available target languages")

    pack_parser = sub.add_parser("pack", help="rebuild a .sb3 from a converted directory")
    pack_parser.add_argument("project_dir", help="a directory produced by sb3conv convert")
    pack_parser.add_argument("-o", "--output", default=None, help="output .sb3 path")

    gui_parser = sub.add_parser("gui", help="open the graphical converter")
    gui_parser.add_argument("input", nargs="?", default=None, help="optional .sb3 to pre-load")
    return parser


def _convert_once(args: argparse.Namespace):
    result = convert(
        args.input,
        args.output,
        lang=args.lang,
        scale=args.scale,
        fps=args.fps,
        script_lang=args.script_lang,
        build_exe=args.exe,
        progress=lambda message: print(message, file=sys.stderr),
    )
    for warning in result.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    print(f"converted {args.input} -> {result.output_dir}")
    print(f"  entrypoint: {result.entrypoint}")
    print(f"  files: {len(result.files)}")
    if result.artifact is not None:
        print(f"  app: {result.artifact}")
    backend_name = get_backend(args.lang).name
    skipped = {lang for lang in result.languages.values() if lang != backend_name}
    if skipped:
        print(f"  script languages present: {', '.join(sorted(skipped))} (skipped by {backend_name} backend)")
    return 0


def _file_stamp(path: Path) -> tuple[int, int]:
    stat = path.stat()
    return (stat.st_mtime_ns, stat.st_size)


def _watch_loop(
    source: Path,
    convert_once: Callable[[], int],
    *,
    poll: float = _WATCH_POLL_SECONDS,
) -> int:
    """Re-run ``convert_once`` whenever ``source`` changes; Ctrl+C stops."""
    print(f"watching {source} for changes (Ctrl+C to stop)", file=sys.stderr)
    try:
        while True:
            stamp = _file_stamp(source)
            while _file_stamp(source) == stamp:
                time.sleep(poll)
            print("--- change detected, re-converting ---", file=sys.stderr)
            try:
                code = convert_once()
            except (Sb3Error, OSError) as exc:
                # the editor may be mid-save; keep watching instead of dying
                print(f"error: {exc} (still watching)", file=sys.stderr)
                continue
            if code:
                return code
    except KeyboardInterrupt:
        print("\nstopped watching", file=sys.stderr)
        return 0


def _do_convert(args: argparse.Namespace):
    code = _convert_once(args)
    if code or not args.watch:
        return code
    return _watch_loop(Path(args.input), lambda: _convert_once(args))


def _do_run(args: argparse.Namespace) -> int:
    result = convert(
        args.input,
        args.output,
        lang=args.lang,
        scale=args.scale,
        fps=args.fps,
        script_lang=args.script_lang,
    )
    for warning in result.warnings:
        print(f"warning: {warning}", file=sys.stderr)

    entry = (result.output_dir / result.entrypoint).resolve()
    extra = list(args.script_args)
    if extra and extra[0] == "--":
        extra = extra[1:]

    if entry.suffix == ".c":
        # native target: build with zig + SDL2, then run the executable
        from sb3conv.backends.c import build_executable, runtime_env

        try:
            exe = build_executable(result.output_dir)
        except BackendError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        command = [str(exe)]
        if args.smoke:
            command += ["--smoke", str(args.smoke)]
        command += extra
        env = runtime_env(smoke=bool(args.smoke))
        return subprocess.run(command, cwd=result.output_dir, env=env, check=False).returncode

    if entry.suffix != ".py":
        # browser target: there is no portable way to launch it from the CLI
        print(f"open this in a browser to play: {entry}")
        if args.smoke:
            print(f"  headless smoke needs a browser: {entry}?smoke={args.smoke}")
        return 0
    command = [sys.executable, str(entry)]
    if args.smoke:
        command += ["--smoke", str(args.smoke)]
    command += extra
    return subprocess.run(command, cwd=result.output_dir, check=False).returncode


def _do_pack(args: argparse.Namespace) -> int:
    from sb3conv.sb3 import pack_project

    out = pack_project(args.project_dir, args.output)
    print(f"packed {args.project_dir} -> {out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args, extra = parser.parse_known_args(argv)

    if args.command == "run":
        # unknown arguments are handed to the generated main.py
        args.script_args = extra
    elif extra:
        parser.error(f"unrecognized arguments: {' '.join(extra)}")

    if args.command is None:
        parser.print_help()
        return 2
    try:
        if args.command == "convert":
            return _do_convert(args)
        if args.command == "run":
            return _do_run(args)
        if args.command == "languages":
            for name in available_languages():
                backend = get_backend(name)
                print(f"{backend.name:12} {backend.label}")
            return 0
        if args.command == "pack":
            return _do_pack(args)
        if args.command == "gui":
            from sb3conv.gui import main as gui_main

            return gui_main([args.input] if args.input else [])
    except Sb3Error as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
