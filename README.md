# Scratch File Converter

Convert Scratch `.sb3` projects into runnable applications:

- **Python** — a pygame-ce project you run with `python main.py`, optionally
  packaged into a standalone `.exe` with PyInstaller.
- **JavaScript** — a browser project, optionally bundled into a single
  self-contained `.html` file that runs straight from `file://`.
- **C** — an SDL2 program built with the Zig toolchain, optionally linked
  into a standalone `.exe`.

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

## Usage

```sh
sb3conv convert project.sb3 -o out --lang python       # or javascript / c
sb3conv convert project.sb3 -o out --lang javascript --exe   # single-file html
sb3conv gui                                            # desktop app
```

The GUI has a **Build playable app (.exe / .html)** checkbox (on by default)
that packages the converted project so it can be distributed as one file.

## Development

```sh
pip install -e .[dev]
ruff check .
pytest
```

## Releases

Windows builds are code-signed through
[SignPath](https://signpath.io)'s free Open Source Code Signing program.
The `build-and-sign` GitHub Actions workflow builds the GUI `.exe` and
submits it for signing; signed artifacts are attached to the workflow run.

## License

Licensed under your choice of:

- the [MIT License](LICENSE-MIT),
- the [Apache License 2.0](LICENSE-APACHE.txt), or
- the [GNU General Public License v3.0](LICENSE-GPL-3.0.txt).

Scratch is a trademark of the Scratch Foundation. This project is not
affiliated with, endorsed by, or sponsored by the Scratch Foundation.

