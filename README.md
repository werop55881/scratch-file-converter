# Scratch File Converter

> Turn Scratch projects into real apps.

[![build-and-sign](https://github.com/werop55881/scratch-file-converter/actions/workflows/build-and-sign.yml/badge.svg)](https://github.com/werop55881/scratch-file-converter/actions/workflows/build-and-sign.yml)
[![Pages](https://github.com/werop55881/scratch-file-converter/actions/workflows/pages.yml/badge.svg)](https://github.com/werop55881/scratch-file-converter/actions/workflows/pages.yml)
[![release](https://img.shields.io/github/v/release/werop55881/scratch-file-converter)](https://github.com/werop55881/scratch-file-converter/releases)

Convert Scratch `.sb3` projects into runnable applications:

- **Python** — a pygame-ce project you run with `python main.py`, optionally
  packaged into a standalone `.exe` with PyInstaller.
- **JavaScript** — a browser project, optionally bundled into a single
  self-contained `.html` file that runs straight from `file://`.
- **TypeScript** — the JavaScript project as `.ts` sources with a
  `tsconfig.json`; `tsc` type-checks the glue and emits the same browser
  bundle.
- **C** — an SDL2 program built with the Zig toolchain, optionally linked
  into a standalone `.exe`.
- **Lua** — a [LÖVE](https://love2d.org) game: coroutines drive the same
  runtime semantics, packed into a single `.love` file (`love project.love`).

## SVG costumes

SVG costumes work in every target, each using the most efficient path:

- **JavaScript** keeps the original `.svg` and renders it natively in the
  browser.
- **C** embeds the `.svg` and rasterizes it at load time with the bundled
  [nanosvg](https://github.com/memononen/nanosvg) header (simple SVGs stay
  vector in the source; complex ones using `<text>`, `<image>` or filters
  are pre-rasterized to PNG with resvg during conversion).
- **Python** rasterizes SVGs to PNG with
  [resvg-py](https://crates.io/crates/resvg) at 2x supersampling, because
  pygame cannot load SVG directly.
- **TypeScript** inherits the JavaScript policy (`.svg` kept for the browser).
- **Lua** rasterizes to PNG like Python — the LÖVE runtime draws bitmaps.

## Usage

```sh
sb3conv convert project.sb3 -o out --lang python    # or javascript / c / ts / lua
sb3conv convert project.sb3 -o out --lang javascript --exe   # single-file html
sb3conv convert project.sb3 -o out --lang lua --exe          # single-file .love
sb3conv pack out -o project.sb3                         # rebuild the .sb3 (round trip)
sb3conv gui                                            # desktop app
```

The GUI has a **Build playable app (.exe / .html)** checkbox (on by default)
that packages the converted project so it can be distributed as one file.

## Round trip

Every conversion embeds the source project as `original.sb3` in the output
directory, so nothing is lost: `sb3conv pack` (or the GUI's **Export
.sb3...** button) rebuilds an archive that opens in Scratch again,
byte-identical to the input. Code you write in the converted project is
not merged back — packing restores the original Scratch project.

## Web app

**Live: https://werop55881.github.io/scratch-file-converter/**

The converter also runs **entirely in your browser** — no server, no upload:
pick a `.sb3`, get an instantly playable HTML page plus a project zip (with
`original.sb3` inside for the round trip). The site (`web/`) loads
[Pyodide](https://pyodide.org) in a Web Worker and installs this repo's
pure-Python wheel; `sb3conv/web.py` is the bridge (tests in
`tests/test_web.py` cover it, `tools/web-e2e/` re-proves the whole pipeline
headless). `.github/workflows/pages.yml` builds and deploys with GitHub
Pages.

Targets: JavaScript gets **Play now**; Python, C and TypeScript download as
project folders (no `.exe`/`tsc` builds in the browser — TypeScript still
emits all `.ts` sources plus a `tsconfig.json`). Lua builds a downloadable
`.love` archive in the browser (pure zip), which plays in LÖVE rather than
the page. SVG costumes rasterize only in the desktop app (Pyodide has no
resvg) — the JavaScript target renders vectors natively anyway.

## Development

```sh
pip install -e .[dev]
ruff check .
pytest
```

## Releases

Prebuilt Windows builds (the GUI `.exe`) are attached to every release and
workflow run. Builds are currently unsigned — machines with Windows Smart
App Control may show a warning until the file builds reputation.

## License

Licensed under your choice of:

- the [MIT License](LICENSE-MIT),
- the [Apache License 2.0](LICENSE-APACHE.txt), or
- the [GNU General Public License v3.0](LICENSE-GPL-3.0.txt).

Scratch is a trademark of the Scratch Foundation. This project is not
affiliated with, endorsed by, or sponsored by the Scratch Foundation.

