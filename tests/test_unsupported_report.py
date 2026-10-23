#> Unsupported-block report: structured tally + unsupported.txt/.json files.
from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from sb3conv.backends.base import WarningSink
from sb3conv.convert import (
    convert,
    unsupported_report_json,
    unsupported_report_text,
)
from tests.helpers import BlockFactory, make_sprite, make_stage


def _write_project_sb3(path: Path, project: dict) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("project.json", json.dumps(project))
    return path


def _pen_project() -> dict:
    """One sprite: say(videoon) then two pen_clear blocks - all unsupported."""
    factory = BlockFactory()
    flag = factory.hat("event_whenflagclicked", x=50, y=40)
    say = factory.stack("looks_say", parent=flag)
    clear1 = factory.stack("pen_clear", parent=say)
    clear2 = factory.stack("pen_clear", parent=clear1)
    factory.chain(flag, say, clear1, clear2)
    factory.wire_reporter(say, "MESSAGE", factory.reporter("sensing_videoon"))
    return {
        "targets": [
            make_stage(),
            make_sprite("Inky", blocks=factory.blocks, x=0, y=0, layerOrder=1),
        ],
        "monitors": [],
        "extensions": [],
        "meta": {"semver": "3.0.0", "vm": "0.2.0", "agent": "tests"},
    }


@pytest.mark.parametrize(
    "lang", ["python", "javascript", "typescript", "lua", "c", "godot"]
)
def test_report_written_for_unsupported_blocks(tmp_path: Path, lang: str):
    sb3 = _write_project_sb3(tmp_path / "pen.sb3", _pen_project())
    out = tmp_path / lang
    result = convert(sb3, out, lang=lang)

    assert "unsupported.txt" in result.files
    assert "unsupported.json" in result.files
    report = (out / "unsupported.txt").read_text(encoding="utf-8")
    assert "project: pen" in report
    assert f"target: {lang}" in report
    assert "pen_clear (2x)" in report
    assert "sensing_videoon (1x)" in report
    assert "total: 3 unsupported blocks, 2 distinct opcodes" in report

    payload = json.loads((out / "unsupported.json").read_text(encoding="utf-8"))
    assert payload["project"] == "pen"
    assert payload["target"] == lang
    assert payload["total"] == 3
    codes = {entry["opcode"]: entry["count"] for entry in payload["opcodes"]}
    assert codes == {"pen_clear": 2, "sensing_videoon": 1}

    assert any(
        warning.endswith("- see unsupported.txt") for warning in result.warnings
    ), result.warnings


def test_supported_project_has_no_report(sb3_path: Path, tmp_path: Path):
    out = tmp_path / "python"
    result = convert(sb3_path, out, lang="python")

    assert not (out / "unsupported.txt").exists()
    assert not (out / "unsupported.json").exists()
    assert not any("unsupported.txt" in warning for warning in result.warnings)


def test_warning_sink_classifies_both_message_shapes():
    sink = WarningSink()
    sink("unsupported reporter 'sensing_videoon' in script at Stage:50")
    sink("unsupported block 'pen_clear' in script at Inky:40 - replaced with a no-op")
    sink("asset foo.png for costume 'x' is missing from the archive")

    assert sink.warnings[0].startswith("unsupported reporter")
    assert sink.unsupported == [
        ("sensing_videoon", "Stage:50"),
        ("pen_clear", "Inky:40"),
    ]


def test_report_text_sorts_by_count_then_name():
    text = unsupported_report_text(
        "game",
        "lua",
        [
            ("pen_down", "A:1"),
            ("pen_down", "A:1"),
            ("pen_down", "B:2"),
            ("pen_up", "A:1"),
            ("zebra_op", "A:1"),
        ],
    )
    # pen_down has the highest total; its hottest location shows "x2"
    assert text.index("pen_down (3x)") < text.index("pen_up (1x)")
    assert "A:1 x2" in text
    assert text.index("pen_up") < text.index("zebra_op")  # ties break on name
    payload = json.loads(unsupported_report_json("game", "lua", [("pen_up", "A:1")]))
    assert payload["opcodes"][0]["locations"] == [{"where": "A:1", "count": 1}]
