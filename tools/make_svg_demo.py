"""Build build/svg-demo.sb3: sample project with a distinctive SVG costume."""

from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.conftest import _png_bytes, _wav_bytes  # noqa: E402
from tests.helpers import sample_project  # noqa: E402

SVG = (
    b"<svg xmlns='http://www.w3.org/2000/svg' width='120' height='120'>"
    b"<circle cx='60' cy='60' r='58' fill='#2050c0'/>"
    b"<rect x='20' y='52' width='80' height='16' fill='#ff8000'/>"
    b"</svg>"
)


def main() -> None:
    out = Path(__file__).resolve().parents[1] / "build" / "svg-demo.sb3"
    data = sample_project()
    sprite = data["targets"][1]
    sprite["costumes"][0].update(
        {
            "name": "badge",
            "md5ext": "badge.svg",
            "assetId": "badge",
            "rotationCenterX": 60,
            "rotationCenterY": 60,
            "bitmapResolution": 1,
        }
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w") as zf:
        zf.writestr("project.json", json.dumps(data))
        zf.writestr("badge.svg", SVG)
        zf.writestr("abc123.png", _png_bytes(4, 4))
        zf.writestr("def456.wav", _wav_bytes())
    print(out)


if __name__ == "__main__":
    main()
