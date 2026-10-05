"""Command line interface: ``sb3conv convert`` and ``sb3conv run``."""

from __future__ import annotations

import argparse
import subprocess
import sys

from sb3conv.backends import available_languages, get_backend
from sb3conv.convert import convert
from sb3conv.errors import BackendError, Sb3Error

PROG = "sb3conv"


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

    run_parser = sub.add_parser("run", help="convert an .sb3 and run it")
    _add_common(run_parser)
    run_parser.add_argument(
        "--smoke", type=int, default=0, metavar="N", help="run N frames headless, then exit"
    )

    sub.add_parser("languages", help="list available target languages")

    gui_parser = sub.add_parser("gui", help="open the graphical converter")
    gui_parser.add_argument("input", nargs="?", default=None, help="optional .sb3 to pre-load")
    return parser


def _do_convert(args: argparse.Namespace):
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
        if args.command == "gui":
            from sb3conv.gui import main as gui_main

            return gui_main([args.input] if args.input else [])
    except Sb3Error as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
