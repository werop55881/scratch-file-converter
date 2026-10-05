"""Phase 1: project.json parsing into the model."""

from __future__ import annotations

from sb3conv.sb3 import load_project
from sb3conv.sb3.model import BlockRef, Literal
from sb3conv.sb3.opcodes import Category, category_of, info, is_supported


def test_targets_and_stage(project) -> None:
    assert project.stage.is_stage is True
    assert [s.name for s in project.sprites] == ["Star"]
    assert project.stage.layer_order == 0
    assert project.sprites[0].x == 10
    assert project.sprites[0].rotation_style == "all around"


def test_broadcasts(project) -> None:
    assert project.broadcasts == {"bcast_boom": "boom"}
    assert project.broadcast_name("bcast_boom") == "boom"
    assert project.broadcast_name("unknown") == "unknown"


def test_variables_and_lists(project) -> None:
    assert project.stage.variables == {"var_dust": ("dust", 0)}
    owner = project.var_owner("var_dust")
    assert owner is not None and owner.name == "Stage"
    assert project.var_owner("nope") is None


def test_scripts_found_in_visual_order(project) -> None:
    sprite = project.sprites[0]
    assert len(sprite.scripts) == 1
    script = sprite.scripts[0]
    assert script.hat.opcode == "event_whenkeypressed"
    assert script.hat.fields["KEY_OPTION"][0] == "space"


def test_comment_language_override(project) -> None:
    script = project.sprites[0].scripts[0]
    assert script.comment.strip() == "lang: js"
    assert script.declared_language() == "js"
    assert project.script_languages[script.script_id] == "js"


def test_stack_links_and_inputs(project) -> None:
    stage = project.stage
    flag = next(s.hat for s in stage.scripts if s.hat.opcode == "event_whenflagclicked")
    assert flag.next_id is not None
    forever = stage.blocks[flag.next_id]
    assert forever.opcode == "control_forever"
    change = stage.blocks[forever.next_id]
    assert change.opcode == "data_changevariableby"
    assert isinstance(change.inputs["VALUE"], Literal)
    assert change.inputs["VALUE"].as_number() == 1
    assert change.fields["VARIABLE"] == ("dust", "var_dust")
    # substack points back at the change block
    substack = forever.inputs["SUBSTACK"]
    assert isinstance(substack, BlockRef)
    assert substack.block_id == change.id
    assert change.parent_id == forever.id


def test_costs_and_sounds_parsed(project) -> None:
    sprite = project.sprites[0]
    assert sprite.costumes[0].name == "star"
    assert sprite.costumes[0].rotation_center_x == 40
    assert sprite.costume_by_ref("abc123") is not None
    assert sprite.costume_by_ref("star") is not None
    assert sprite.costume_by_ref("nope") is None
    assert sprite.sounds[0].name == "ping"
    assert sprite.sound_by_ref("def456") is not None


def test_monitors(project) -> None:
    assert len(project.monitors) == 1
    monitor = project.monitors[0]
    assert monitor.label == "dust"
    assert monitor.target_name == "Star"
    assert monitor.visible is True
    assert monitor.is_list is False


def test_reporter_children_reachable(project_dict) -> None:
    from tests.helpers import BlockFactory, make_sprite

    factory = BlockFactory()
    hat = factory.hat("event_whenflagclicked")
    join = factory.stack("operator_join", inputs={"STRING1": [1, [10, "a"]], "STRING2": [1, [10, "b"]]}, parent=hat)
    factory.chain(hat, join)
    reporter = factory.reporter("operator_length", inputs={"STRING": [1, [10, "x"]]})
    factory.wire_reporter(join, "STRING2", reporter)

    project_dict["targets"][1] = make_sprite("S", blocks=factory.blocks)
    project = load_project(project_dict)
    script = project.sprites[0].scripts[0]
    opcodes = [b.opcode for b in script.iter_stack()]
    assert opcodes == ["event_whenflagclicked", "operator_join", "operator_length"]


def test_opcode_registry() -> None:
    assert category_of("motion_movesteps") is Category.MOTION
    assert category_of("sound_play") is Category.SOUND
    assert category_of("data_setvariableto") is Category.DATA
    assert category_of("totally_made_up") is Category.UNKNOWN
    assert info("control_forever").kind.value == "stack"
    assert is_supported("motion_movesteps") is True
    assert is_supported("procedures_definition") is False
    assert is_supported("totally_made_up") is False
