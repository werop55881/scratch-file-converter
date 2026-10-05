"""Custom blocks (procedures): discovery, emission and calls in all backends."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from sb3conv.backends.c import emit_c
from sb3conv.backends.javascript import emit_javascript
from sb3conv.backends.python import emit_python
from sb3conv.sb3 import load_project
from tests.helpers import BlockFactory, make_sprite, make_stage


def _files(result) -> dict:
    return {f.path: f for f in result.files}


def procedures_project() -> dict:
    """One sprite with a definition (one Costume argument) and a call site.

    The definition body uses the argument as a string (switch costume) and as
    a number (set size), so both coercion paths get exercised.
    """
    factory = BlockFactory()

    # when green flag clicked -> call "switch to <Walking>"
    flag = factory.hat("event_whenflagclicked", x=10, y=10)
    call = factory.stack("procedures_call", parent=flag)
    factory.blocks[call]["mutation"] = {
        "tagName": "mutation",
        "children": [],
        "proccode": "switch to %s",
        "argumentids": '["arg-costume"]',
        "warp": "false",
    }
    menu = factory.reporter("looks_costume", fields={"COSTUME": ["Walking", None]})
    factory.wire_reporter(call, "arg-costume", menu)
    factory.chain(flag, call)

    # custom block definition: switch costume to <Costume>; set size to <Costume>
    hat = factory.hat("procedures_definition", x=10, y=120)
    prototype = factory.reporter("procedures_prototype")
    factory.blocks[prototype]["mutation"] = {
        "tagName": "mutation",
        "children": [],
        "proccode": "switch to %s",
        "argumentids": '["arg-costume"]',
        "argumentnames": '["Costume"]',
        "argumentdefaults": '[""]',
        "warp": "false",
    }
    factory.blocks[hat]["inputs"]["custom_block"] = [2, prototype]
    factory.blocks[prototype]["parent"] = hat

    switch = factory.stack("looks_switchcostumeto", parent=hat)
    as_text = factory.reporter("argument_reporter_string_number", fields={"VALUE": ["Costume", None]})
    factory.wire_reporter(switch, "COSTUME", as_text)
    set_size = factory.stack("looks_setsizeto", parent=switch)
    as_number = factory.reporter("argument_reporter_string_number", fields={"VALUE": ["Costume", None]})
    factory.wire_reporter(set_size, "SIZE", as_number)
    factory.chain(hat, switch, set_size)

    sprite = make_sprite(
        "Hero",
        blocks=factory.blocks,
        x=0,
        y=0,
        layerOrder=1,
        costumes=[
            {
                "name": "Walking",
                "md5ext": "abc123.png",
                "assetId": "abc123",
                "rotationCenterX": 20,
                "rotationCenterY": 20,
                "bitmapResolution": 1,
                "id": "walking-id",
            }
        ],
    )
    return {
        "targets": [make_stage(), sprite],
        "monitors": [],
        "meta": {},
        "extensions": [],
    }


@pytest.fixture
def procedures_pb():
    return load_project(procedures_project())


def _write_sb3(path: Path, project: dict) -> Path:
    from tests.conftest import _png_bytes

    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("project.json", json.dumps(project))
        zf.writestr("abc123.png", _png_bytes(4, 4))
    return path


def test_python_emits_procedure_definition_and_call(procedures_pb):
    result = emit_python(procedures_pb, {"assets": {"abc123.png": b"PNG"}})
    main = _files(result)["main.py"].content

    assert "def proc_0(ctx, rt, _a0):" in main
    assert "if False: yield" in main
    assert "yield from proc_0(ctx, rt, " in main
    assert "ctx.set_costume(s_str(_a0))" in main  # argument as a string
    assert "s_num(_a0)" in main  # argument as a number
    # the definition is a function, not a registered hat route
    assert main.count("ScriptReg(") == 1
    assert "ScriptReg('Hero', 'event_whenflagclicked'" in main
    assert not any("custom block" in warning for warning in result.warnings)
    compile(main, "main.py", "exec")


def test_javascript_emits_procedure_definition_and_call(procedures_pb):
    result = emit_javascript(procedures_pb, {"assets": {"abc123.png": b"PNG"}})
    main = _files(result)["main.js"].content

    assert "function* proc_0(ctx, rt, _a0) {" in main
    assert 'yield* proc_0(ctx, rt, "Walking");' in main
    assert "ctx.set_costume(s_str(_a0));" in main
    assert "s_num(_a0)" in main
    assert main.count("new ScriptReg(") == 1
    assert not any("custom block" in warning for warning in result.warnings)


def test_c_emits_procedure_with_forward_declaration(procedures_pb):
    result = emit_c(procedures_pb, {"assets": {"abc123.png": b"PNG"}})
    main = _files(result)["main.c"].content

    decl = "static void proc_0(Actor *ctx, Rt *rt, Value _a0);"
    assert decl in main
    # the call site lives in an earlier script than the definition, so the
    # declaration must come first (emit_c compiles main.c as part of emit)
    assert main.index(decl) < main.index('proc_0(ctx, rt, S("Walking"));')
    assert "static void proc_0(Actor *ctx, Rt *rt, Value _a0) {" in main
    assert "sb_set_costume(rt, ctx, s_str(_a0));" in main
    assert "s_numd(_a0)" in main
    assert main.count(".fn = script_") == 1
    assert not any("custom block" in warning for warning in result.warnings)


@pytest.mark.slow
def test_python_procedure_runs_in_smoke(tmp_path: Path):
    """End-to-end: convert, then run the generated app (yield from a call)."""
    sb3 = _write_sb3(tmp_path / "procs.sb3", procedures_project())
    out = tmp_path / "out"
    from sb3conv.convert import convert

    result = convert(sb3, out, lang="python")
    assert not any("custom block" in warning for warning in result.warnings)

    env = {
        **os.environ,
        "SDL_VIDEODRIVER": "dummy",
        "SDL_AUDIODRIVER": "dummy",
        "PYGAME_HIDE_SUPPORT_PROMPT": "1",
    }
    proc = subprocess.run(
        [sys.executable, "main.py", "--smoke", "5"],
        cwd=out,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    assert "SMOKE OK" in proc.stdout
    assert "Traceback" not in proc.stderr
