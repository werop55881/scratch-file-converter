"""Python backend emission: main.py, manifest, warnings, language tags."""

from __future__ import annotations

import json

from sb3conv.backends import available_languages, get_backend
from sb3conv.backends.python import emit_python
from sb3conv.sb3 import load_project
from tests.helpers import BlockFactory, make_sprite, make_stage, text


def _files(result) -> dict:
    return {f.path: f for f in result.files}


def test_emit_produces_a_complete_runnable_layout(project):
    result = emit_python(
        project, {"name": "sample", "scale": 3, "fps": 24, "assets": {"abc123.png": b"PNG"}}
    )
    files = _files(result)
    assert set(files) >= {"main.py", "runtime.py", "sb3_manifest.json", "assets/abc123.png"}
    assert result.entrypoint == "main.py"
    compile(files["main.py"].content, "main.py", "exec")
    compile(files["runtime.py"].content, "runtime.py", "exec")

    manifest = json.loads(files["sb3_manifest.json"].content)
    assert manifest["name"] == "sample"
    assert manifest["scale"] == 3
    assert manifest["fps"] == 24
    assert manifest["stage"]["name"] == "Stage"
    assert manifest["stage"]["variables"] == {"dust": 0}
    assert manifest["stage"]["costumes"] == []
    sprite = manifest["sprites"][0]
    assert sprite["name"] == "Star"
    assert sprite["costumes"][0]["file"] == "abc123.png"
    assert sprite["sounds"][0]["file"] == "def456.wav"
    monitor = manifest["monitors"][0]
    assert monitor["label"] == "dust"
    assert monitor["isList"] is False


def test_emit_registers_only_python_scripts(project):
    result = emit_python(project, {})
    main = _files(result)["main.py"].content
    # the sample sprite script carries a "lang: js" comment and must be skipped
    assert main.count("ScriptReg(") == 1
    assert "ScriptReg('Stage', 'event_whenflagclicked'" in main
    assert any("Star" in w and "skipped" in w for w in result.warnings)
    assert result.script_languages  # every script still reports its language


def test_cli_override_beats_hat_comment(project):
    result = emit_python(project, {"script_lang": {"Star": "python"}})
    main = _files(result)["main.py"].content
    assert main.count("ScriptReg(") == 2
    assert "ScriptReg('Star', 'event_whenkeypressed'" in main
    assert not any("skipped" in w for w in result.warnings)


def test_stage_variables_read_rt_sprite_variables_read_ctx(project):
    result = emit_python(project, {"script_lang": {"Star": "python"}})
    main = _files(result)["main.py"].content
    assert "rt.vars['dust']" in main


def test_broadcast_receiver_route_uses_the_broadcast_name():
    factory = BlockFactory()
    hat = factory.hat(
        "event_whenbroadcastreceived",
        fields={"BROADCAST_OPTION": ["bcast_boom", None]},
        x=0,
        y=0,
    )
    say = factory.stack("looks_say", inputs={"MESSAGE": text("hi")}, parent=hat)
    factory.chain(hat, say)
    project = load_project(
        {
            "targets": [
                make_stage(blocks=factory.blocks, broadcasts={"bcast_boom": "boom"}),
                make_sprite("Star"),
            ],
            "monitors": [],
            "meta": {},
            "extensions": [],
        }
    )
    main = _files(emit_python(project, {}))["main.py"].content
    assert (
        "ScriptReg('Stage', 'event_whenbroadcastreceived', "
        '{"BROADCAST_OPTION": "boom"},' in main
    )
    assert "ctx.say = 'hi'" in main


def test_unsupported_blocks_warn_and_become_noops():
    factory = BlockFactory()
    hat = factory.hat("event_whenflagclicked", x=0, y=0)
    call = factory.stack("procedures_call", fields={"PROC_CODE": ["noop %n", None]}, parent=hat)
    factory.chain(hat, call)
    project = load_project(
        {
            "targets": [make_stage(blocks=factory.blocks), make_sprite("Star")],
            "monitors": [],
            "meta": {},
            "extensions": [],
        }
    )
    result = emit_python(project, {})
    assert any("procedures_call" in w for w in result.warnings)
    main = _files(result)["main.py"].content
    assert "rt.unsupported('procedures_call')" in main
    compile(main, "main.py", "exec")


def test_forever_without_yield_gets_a_forced_yield(project):
    main = _files(emit_python(project, {}))["main.py"].content
    assert "while True:" in main
    # the sample forever body only changes a variable: must yield each frame
    assert "yield" in main


def test_available_languages_include_python():
    assert "python" in available_languages()
    assert get_backend("py").name == "python"
