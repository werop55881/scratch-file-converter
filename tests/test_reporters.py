"""Newly supported reporters and menus across the three backends."""

from __future__ import annotations

from sb3conv.backends.c import emit_c
from sb3conv.backends.javascript import emit_javascript
from sb3conv.backends.python import emit_python
from sb3conv.sb3 import load_project
from tests.helpers import BlockFactory, make_sprite, make_stage, number, text


def _files(result) -> dict:
    return {f.path: f for f in result.files}


def reporters_project() -> dict:
    """A sprite script touching every reporter/menu added for warning cleanup."""
    factory = BlockFactory()

    flag = factory.hat("event_whenflagclicked", x=0, y=0)

    goto = factory.stack("motion_goto", parent=flag)
    goto_menu = factory.reporter("motion_goto_menu", fields={"TO": ["Sprite2", None]})
    factory.wire_reporter(goto, "TO", goto_menu)

    point = factory.stack("motion_pointtowards", parent=goto)
    point_menu = factory.reporter("motion_pointtowards_menu", fields={"TOWARDS": ["_mouse_", None]})
    factory.wire_reporter(point, "TOWARDS", point_menu)

    set_fx = factory.stack(
        "looks_seteffectto",
        inputs={"VALUE": number(50)},
        fields={"EFFECT": ["GHOST", None]},
        parent=point,
    )
    change_fx = factory.stack(
        "looks_changeeffectby",
        inputs={"CHANGE": number(10)},
        fields={"EFFECT": ["COLOR", None]},
        parent=set_fx,
    )

    key_if = factory.stack("control_if", parent=change_fx)
    key_press = factory.reporter("sensing_keypressed")
    factory.wire_reporter(key_if, "CONDITION", key_press)
    key_menu = factory.reporter("sensing_keyoptions", fields={"KEY_OPTION": ["d", None]})
    factory.wire_reporter(key_press, "KEY_OPTION", key_menu)

    touch_if = factory.stack("control_if", parent=key_if)
    touching = factory.reporter("sensing_touchingobject")
    factory.wire_reporter(touch_if, "CONDITION", touching)
    touch_menu = factory.reporter(
        "sensing_touchingobjectmenu", fields={"TOUCHINGOBJECTMENU": ["Sprite2", None]}
    )
    factory.wire_reporter(touching, "TOUCHINGOBJECTMENU", touch_menu)

    say_x = factory.stack("looks_say", parent=touch_if)
    factory.wire_reporter(say_x, "MESSAGE", factory.reporter("motion_xposition"))
    say_y = factory.stack("looks_say", parent=say_x)
    factory.wire_reporter(say_y, "MESSAGE", factory.reporter("motion_yposition"))
    say_size = factory.stack("looks_say", parent=say_y)
    factory.wire_reporter(say_size, "MESSAGE", factory.reporter("looks_size"))
    say_name = factory.stack("looks_say", parent=say_size)
    factory.wire_reporter(
        say_name,
        "MESSAGE",
        factory.reporter("looks_costumenumbername", fields={"NUMBER_NAME": ["name", None]}),
    )
    say_number = factory.stack("looks_say", parent=say_name)
    factory.wire_reporter(
        say_number,
        "MESSAGE",
        factory.reporter("looks_costumenumbername", fields={"NUMBER_NAME": ["number", None]}),
    )

    factory.chain(
        flag, goto, point, set_fx, change_fx, key_if, touch_if,
        say_x, say_y, say_size, say_name, say_number,
    )

    sprite = make_sprite(
        "Hero",
        blocks=factory.blocks,
        x=10,
        y=20,
        layerOrder=1,
        costumes=[
            {
                "name": "idle",
                "md5ext": "abc123.png",
                "assetId": "abc123",
                "rotationCenterX": 2,
                "rotationCenterY": 2,
                "bitmapResolution": 1,
                "id": "idle-id",
            }
        ],
    )
    other = make_sprite("Sprite2", x=-40, y=-40, layerOrder=2)
    return {
        "targets": [make_stage(), sprite, other],
        "monitors": [],
        "meta": {},
        "extensions": [],
    }


def test_python_reporters_and_effects():
    project = load_project(reporters_project())
    result = emit_python(project, {"assets": {"abc123.png": b"PNG"}})
    main = _files(result)["main.py"].content

    assert result.warnings == []
    assert "rt.goto(ctx, s_str('Sprite2'))" in main
    assert "rt.point_towards(ctx, s_str('_mouse_'))" in main
    assert "rt.set_effect(ctx, 'ghost', 50)" in main  # EFFECT lowercased
    assert "rt.change_effect(ctx, 'color', 10)" in main
    assert "rt.key_down(s_str('d'))" in main
    assert "rt.touching(ctx, s_str('Sprite2'))" in main
    assert "ctx.say = ctx.x" in main
    assert "ctx.say = ctx.y" in main
    assert "ctx.say = ctx.size" in main
    assert 'ctx.say = (ctx.costume.name if ctx.costume else "")' in main
    assert "ctx.say = (ctx.current_costume + 1)" in main
    compile(main, "main.py", "exec")


def test_javascript_reporters_and_effects():
    project = load_project(reporters_project())
    result = emit_javascript(project, {"assets": {"abc123.png": b"PNG"}})
    main = _files(result)["main.js"].content

    assert result.warnings == []
    assert 'rt.goto(ctx, s_str("Sprite2"));' in main
    assert 'rt.point_towards(ctx, s_str("_mouse_"));' in main
    assert 'rt.set_effect(ctx, "ghost", 50);' in main
    assert 'rt.change_effect(ctx, "color", 10);' in main
    assert 'rt.key_down(s_str("d"))' in main
    assert 'rt.touching(ctx, s_str("Sprite2"))' in main
    assert "ctx.say = ctx.x;" in main
    assert "ctx.say = ctx.y;" in main
    assert "ctx.say = ctx.size;" in main
    assert 'ctx.say = (ctx.costume ? ctx.costume.name : "");' in main
    assert "ctx.say = (ctx.current_costume + 1);" in main


def test_c_reporters_and_effects():
    project = load_project(reporters_project())
    result = emit_c(project, {"assets": {"abc123.png": b"PNG"}})
    main = _files(result)["main.c"].content

    assert result.warnings == []
    assert 'sb_goto(rt, ctx, s_str(S("Sprite2")));' in main
    assert 'sb_point_towards(rt, ctx, s_str(S("_mouse_")));' in main
    assert 'sb_set_effect(rt, ctx, S("ghost"), N(50));' in main
    assert 'sb_change_effect(rt, ctx, S("color"), N(10));' in main
    assert 'sb_key_down(rt, s_str(S("d")))' in main
    assert 'sb_touching(rt, ctx, s_str(S("Sprite2")))' in main
    assert "sb_set_say(ctx, N(ctx->x));" in main
    assert "sb_set_say(ctx, N(ctx->y));" in main
    assert "sb_set_say(ctx, N(ctx->size));" in main
    assert "sb_set_say(ctx, sb_costume_name(ctx));" in main
    assert "sb_set_say(ctx, N(ctx->current_costume + 1));" in main


def compound_conditions_project() -> dict:
    """if (key d and key w), if (not key a), if (key s or key e)."""
    factory = BlockFactory()

    flag = factory.hat("event_whenflagclicked", x=0, y=0)

    if_and = factory.stack("control_if", parent=flag)
    and_block = factory.reporter("operator_and")
    factory.wire_reporter(if_and, "CONDITION", and_block)
    for input_name, letter in (("OPERAND1", "d"), ("OPERAND2", "w")):
        key = factory.reporter("sensing_keypressed")
        factory.wire_reporter(and_block, input_name, key)
        factory.wire_reporter(
            key, "KEY_OPTION", factory.reporter("sensing_keyoptions",
                                                fields={"KEY_OPTION": [letter, None]})
        )
    move_x = factory.stack("motion_changexby", inputs={"DX": number(10)}, parent=if_and)

    if_not = factory.stack("control_if", parent=if_and)
    not_block = factory.reporter("operator_not")
    factory.wire_reporter(if_not, "CONDITION", not_block)
    key_a = factory.reporter("sensing_keypressed")
    factory.wire_reporter(not_block, "OPERAND", key_a)
    factory.wire_reporter(
        key_a, "KEY_OPTION", factory.reporter("sensing_keyoptions",
                                              fields={"KEY_OPTION": ["a", None]})
    )
    move_y = factory.stack("motion_changeyby", inputs={"DY": number(5)}, parent=if_not)

    if_or = factory.stack("control_if", parent=if_not)
    or_block = factory.reporter("operator_or")
    factory.wire_reporter(if_or, "CONDITION", or_block)
    for input_name, letter in (("OPERAND1", "s"), ("OPERAND2", "e")):
        key = factory.reporter("sensing_keypressed")
        factory.wire_reporter(or_block, input_name, key)
        factory.wire_reporter(
            key, "KEY_OPTION", factory.reporter("sensing_keyoptions",
                                                fields={"KEY_OPTION": [letter, None]})
        )
    move_or = factory.stack("motion_changexby", inputs={"DX": number(3)}, parent=if_or)

    factory.chain(flag, if_and, if_not, if_or)
    factory.substack(if_and, "SUBSTACK", move_x)
    factory.substack(if_not, "SUBSTACK", move_y)
    factory.substack(if_or, "SUBSTACK", move_or)

    sprite = make_sprite("Hero", blocks=factory.blocks, x=0, y=0, layerOrder=1)
    return {"targets": [make_stage(), sprite], "monitors": [], "meta": {}, "extensions": []}


def test_python_compound_conditions_emit_operands():
    # regression: and/or/not must read OPERAND1/OPERAND2/OPERAND inputs;
    # looking them up under BOOLEAN* silently emitted constant False
    project = load_project(compound_conditions_project())
    result = emit_python(project, {"assets": {}})
    main = _files(result)["main.py"].content

    assert result.warnings == []
    assert "if (rt.key_down(s_str('d')) and rt.key_down(s_str('w'))):" in main
    assert "if s_not(rt.key_down(s_str('a'))):" in main
    assert "if (rt.key_down(s_str('s')) or rt.key_down(s_str('e'))):" in main
    assert "and False" not in main
    assert "s_not(False)" not in main


def test_javascript_compound_conditions_emit_operands():
    project = load_project(compound_conditions_project())
    result = emit_javascript(project, {"assets": {}})
    main = _files(result)["main.js"].content

    assert result.warnings == []
    assert 's_and(rt.key_down(s_str("d")), rt.key_down(s_str("w")))' in main
    assert 's_not(rt.key_down(s_str("a")))' in main
    assert 's_or(rt.key_down(s_str("s")), rt.key_down(s_str("e")))' in main
    assert 'and false' not in main
    assert "s_not(false)" not in main


def test_c_compound_conditions_emit_operands():
    project = load_project(compound_conditions_project())
    result = emit_c(project, {"assets": {}})
    main = _files(result)["main.c"].content

    assert result.warnings == []
    assert 's_and(sb_key_down(rt, s_str(S("d"))), sb_key_down(rt, s_str(S("w"))))' in main
    assert 's_not(sb_key_down(rt, s_str(S("a"))))' in main
    assert 's_or(sb_key_down(rt, s_str(S("s"))), sb_key_down(rt, s_str(S("e"))))' in main
    assert "N(0) and" not in main
    assert "s_not(N(0))" not in main


def alias_inputs_project() -> dict:
    """Blocks whose input/field names differ between handler and editor."""
    factory = BlockFactory()
    flag = factory.hat("event_whenflagclicked", x=0, y=0)

    say = factory.stack("looks_say", parent=flag)
    contains = factory.reporter(
        "operator_contains", inputs={"STRING1": text("hello"), "STRING2": text("ell")}
    )
    factory.wire_reporter(say, "MESSAGE", contains)

    say_of = factory.stack("looks_say", parent=say)
    of = factory.reporter("sensing_of", fields={"PROPERTY": ["x position", None]})
    object_menu = factory.reporter("sensing_of_object_menu", fields={"OBJECT": ["Sprite2", None]})
    factory.wire_reporter(of, "OBJECT", object_menu)
    factory.wire_reporter(say_of, "MESSAGE", of)

    glide = factory.stack(
        "motion_glidesecstoxy",
        inputs={"SECS": number(1), "X": number(10), "Y": number(20)},
        parent=say_of,
    )
    factory.chain(flag, say, say_of, glide)

    sprite = make_sprite("Hero", blocks=factory.blocks, x=0, y=0, layerOrder=1)
    return {"targets": [make_stage(), sprite], "monitors": [], "meta": {}, "extensions": []}


def test_python_alias_input_names():
    # regression: contains read FIRST/SECOND, sensing_of read ATTRIBUTE as a
    # field, glide read TO_X/TO_Y - all silently defaulted to garbage
    project = load_project(alias_inputs_project())
    result = emit_python(project, {"assets": {}})
    main = _files(result)["main.py"].content

    assert result.warnings == []
    assert "s_contains('hello', 'ell')" in main
    assert "rt.of('x position', 'Sprite2')" in main
    assert "yield from rt.glide_to(ctx, 1, 10, 20)" in main
    compile(main, "main.py", "exec")


def test_javascript_alias_input_names():
    project = load_project(alias_inputs_project())
    result = emit_javascript(project, {"assets": {}})
    main = _files(result)["main.js"].content

    assert result.warnings == []
    assert 's_contains("hello", "ell")' in main
    assert 'rt.of("x position", "Sprite2")' in main
    assert "yield* rt.glide_to(ctx, 1, 10, 20);" in main


def test_c_alias_input_names():
    project = load_project(alias_inputs_project())
    result = emit_c(project, {"assets": {}})
    main = _files(result)["main.c"].content

    assert result.warnings == []
    assert 's_contains(S("hello"), S("ell"))' in main
    assert 'sb_of(rt, S("x position"), S("Sprite2"))' in main
    assert "sb_glide(rt, ctx, 1, 10, 20);" in main


def forever_after_repeat_project() -> dict:
    """forever { repeat(2) { change x }  if <key d> { change y } }."""
    factory = BlockFactory()
    flag = factory.hat("event_whenflagclicked", x=0, y=0)
    forever = factory.stack("control_forever", parent=flag)
    repeat = factory.stack("control_repeat", inputs={"TIMES": number(2)}, parent=forever)
    change_x = factory.stack("motion_changexby", inputs={"DX": number(1)}, parent=repeat)
    if_d = factory.stack("control_if", parent=repeat)
    key = factory.reporter("sensing_keypressed")
    factory.wire_reporter(if_d, "CONDITION", key)
    factory.wire_reporter(
        key, "KEY_OPTION", factory.reporter("sensing_keyoptions", fields={"KEY_OPTION": ["d", None]})
    )
    change_y = factory.stack("motion_changeyby", inputs={"DY": number(1)}, parent=if_d)

    factory.chain(flag, forever)
    factory.substack(forever, "SUBSTACK", repeat)
    factory.substack(repeat, "SUBSTACK", change_x)
    factory.chain(repeat, if_d)
    factory.substack(if_d, "SUBSTACK", change_y)

    sprite = make_sprite("Hero", blocks=factory.blocks, x=0, y=0, layerOrder=1)
    return {"targets": [make_stage(), sprite], "monitors": [], "meta": {}, "extensions": []}


def test_python_forever_yield_stays_at_loop_level():
    # regression: st_repeat forgot indent -= 1, so the forever trailing yield
    # was emitted inside the following if - when the if was false the loop
    # spun forever without ever yielding (game froze)
    project = load_project(forever_after_repeat_project())
    result = emit_python(project, {"assets": {}})
    main = _files(result)["main.py"].content

    lines = main.splitlines()
    while_line = next(i for i, line in enumerate(lines) if line.strip() == "while True:")
    body_indent = len(lines[while_line + 1]) - len(lines[while_line + 1].lstrip())
    if_line = next(
        i for i in range(while_line, len(lines)) if lines[i].strip().startswith("if rt.key_down")
    )
    yield_indents = [
        len(lines[i]) - len(lines[i].lstrip())
        for i in range(if_line, len(lines))
        if lines[i].strip() == "yield"
    ]
    assert yield_indents, "forever must end with a yield"
    assert all(indent == body_indent for indent in yield_indents), (
        f"yield indents {yield_indents} != while body level {body_indent}"
    )
    compile(main, "main.py", "exec")
