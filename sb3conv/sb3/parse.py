"""Turn raw project.json data into the typed model."""

from __future__ import annotations

from sb3conv.sb3.model import (
    Asset,
    Block,
    BlockRef,
    Costume,
    InputValue,
    Literal,
    Monitor,
    Project,
    Script,
    Sound,
    Target,
)
from sb3conv.sb3.opcodes import HAT_OPCODES


def _number(value: object, default: float = 0.0) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _parse_value(value: object) -> InputValue:
    if value is None:
        return None
    if isinstance(value, str):
        return BlockRef(value)
    if isinstance(value, list):
        if len(value) >= 2 and isinstance(value[0], int):
            # [type_code, payload] e.g. [4, "10"], [10, "hello"],
            # [11, "msg name", "msg id"], [12, "var name", "var id"]
            type_code = value[0]
            id_value = None
            if type_code in (11, 12, 13) and len(value) > 2 and isinstance(value[2], str):
                id_value = value[2]
            return Literal(value[1], type_code=type_code, id_value=id_value)
        if len(value) == 1:
            return _parse_value(value[0])
        return None
    return Literal(value)


def _parse_inputs(raw: dict) -> dict[str, InputValue]:
    inputs: dict[str, InputValue] = {}
    for name, entry in raw.items():
        if not isinstance(entry, list) or not entry:
            continue
        kind = entry[0]
        if not isinstance(kind, int):
            continue
        # 1 = no shadow, 2 = shadow only, 3 = block covering a shadow
        if kind == 3 and len(entry) >= 2 or len(entry) >= 2:
            inputs[name] = _parse_value(entry[1])
        else:
            inputs[name] = None
    return inputs


def _parse_fields(raw: dict) -> dict[str, tuple[str, str | None]]:
    fields: dict[str, tuple[str, str | None]] = {}
    for name, entry in raw.items():
        if isinstance(entry, list) and entry:
            value = entry[0]
            field_id = entry[1] if len(entry) > 1 else None
            fields[name] = (str(value), str(field_id) if field_id is not None else None)
    return fields


def _parse_mutation(raw: object) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    return {str(k): str(v) for k, v in raw.items() if isinstance(v, str)}


def _parse_blocks(raw_blocks: dict) -> dict[str, Block]:
    blocks: dict[str, Block] = {}
    for block_id, raw in raw_blocks.items():
        if not isinstance(raw, dict) or "opcode" not in raw:
            continue  # some extensions emit shadow-only stubs
        block = Block(
            id=block_id,
            opcode=str(raw["opcode"]),
            inputs=_parse_inputs(raw.get("inputs", {})),
            fields=_parse_fields(raw.get("fields", {})),
            mutation=_parse_mutation(raw.get("mutation")),
            next_id=raw.get("next"),
            parent_id=raw.get("parent"),
            top_level=bool(raw.get("topLevel", False)),
            x=_number(raw.get("x")),
            y=_number(raw.get("y")),
        )
        blocks[block_id] = block
    return blocks


def _parse_costumes(raw_costumes: list) -> list[Costume]:
    costumes: list[Costume] = []
    for index, raw in enumerate(raw_costumes):
        asset_id = str(raw.get("assetId") or raw.get("md5ext", f"costume{index}"))
        md5ext = str(raw.get("md5ext") or f"{asset_id}.png")
        costumes.append(
            Costume(
                name=str(raw.get("name", f"costume{index}")),
                asset=Asset(asset_id=asset_id, md5ext=md5ext, name=str(raw.get("name", ""))),
                rotation_center_x=_number(raw.get("rotationCenterX")),
                rotation_center_y=_number(raw.get("rotationCenterY")),
                bitmap_resolution=_number(raw.get("bitmapResolution", 1), 1.0) or 1.0,
                md5ext=md5ext,
                costume_id=str(raw.get("id", asset_id)),
            )
        )
    return costumes


def _parse_sounds(raw_sounds: list) -> list[Sound]:
    sounds: list[Sound] = []
    for index, raw in enumerate(raw_sounds):
        asset_id = str(raw.get("assetId") or raw.get("md5ext", f"sound{index}"))
        md5ext = str(raw.get("md5ext") or f"{asset_id}.wav")
        sounds.append(
            Sound(
                name=str(raw.get("name", f"sound{index}")),
                asset=Asset(asset_id=asset_id, md5ext=md5ext, name=str(raw.get("name", ""))),
                md5ext=md5ext,
                sound_id=str(raw.get("id", asset_id)),
            )
        )
    return sounds


def _parse_target(raw: dict) -> Target:
    is_stage = bool(raw.get("isStage", False))
    target = Target(
        is_stage=is_stage,
        name=str(raw.get("name", "Stage" if is_stage else "Sprite")),
        variables={k: (str(v[0]), v[1]) for k, v in raw.get("variables", {}).items() if isinstance(v, list) and v},
        lists={k: (str(v[0]), list(v[1]) if len(v) > 1 else []) for k, v in raw.get("lists", {}).items() if isinstance(v, list) and v},
        blocks=_parse_blocks(raw.get("blocks", {})),
        costumes=_parse_costumes(raw.get("costumes", [])),
        sounds=_parse_sounds(raw.get("sounds", [])),
        comments={
            str(cid): str(raw_comment.get("text", ""))
            for cid, raw_comment in raw.get("comments", {}).items()
            if isinstance(raw_comment, dict)
        },
        current_costume=int(_number(raw.get("currentCostume"))),
        x=_number(raw.get("x")),
        y=_number(raw.get("y")),
        direction=_number(raw.get("direction", 90), 90.0),
        size=_number(raw.get("size", 100), 100.0),
        visible=bool(raw.get("visible", True)),
        rotation_style=str(raw.get("rotationStyle", "all around")),
        layer_order=int(_number(raw.get("layerOrder"))),
        volume=int(_number(raw.get("volume", 100), 100.0)),
        draggable=bool(raw.get("draggable", False)),
        tempo=int(_number(raw.get("tempo", 60), 60.0)),
        video_state=str(raw.get("videoState", "on")),
    )
    return target


def _find_scripts(target: Target, raw_comments: dict) -> list[Script]:
    scripts: list[Script] = []
    comment_by_block: dict[str, str] = {}
    for raw in raw_comments.values():
        if isinstance(raw, dict) and raw.get("blockId"):
            comment_by_block[str(raw["blockId"])] = str(raw.get("text", ""))

    for block in target.blocks.values():
        if not block.top_level or block.opcode not in HAT_OPCODES:
            continue
        scripts.append(
            Script(
                hat=block,
                target=target,
                comment=comment_by_block.get(block.id, ""),
            )
        )
    scripts.sort(key=lambda s: (round(s.hat.y), round(s.hat.x)))
    return scripts


def load_project(data: dict) -> Project:
    """Build a :class:`Project` from parsed project.json data."""
    targets = [_parse_target(raw) for raw in data.get("targets", [])]

    broadcasts: dict[str, str] = {}
    for raw in data.get("targets", []):
        for broadcast_id, name in raw.get("broadcasts", {}).items():
            broadcasts[str(broadcast_id)] = str(name)

    project = Project(
        targets=targets,
        broadcasts=broadcasts,
        meta=dict(data.get("meta", {})),
        extensions=list(data.get("extensions", [])),
    )

    # Scripts (needs the raw comment dicts for block linkage)
    for target, raw in zip(targets, data.get("targets", []), strict=False):
        target.scripts = _find_scripts(target, raw.get("comments", {}))

    project.monitors = _parse_monitors(data.get("monitors", []), project)

    for script in project.all_scripts():
        language = script.declared_language()
        if language:
            project.script_languages[script.script_id] = language

    return project


def _parse_monitors(raw_monitors: list, project: Project) -> list[Monitor]:
    monitors: list[Monitor] = []
    for raw in raw_monitors:
        if not isinstance(raw, dict):
            continue
        monitor_id = str(raw.get("id", ""))
        is_list = bool(raw.get("isList", False))
        if not is_list:
            is_list = project.list_owner(monitor_id) is not None and project.var_owner(monitor_id) is None
        owner = project.var_owner(monitor_id) if not is_list else project.list_owner(monitor_id)
        monitors.append(
            Monitor(
                monitor_id=monitor_id,
                mode=str(raw.get("mode", "default")),
                x=_number(raw.get("x")) - 240,
                y=180 - _number(raw.get("y")),
                visible=bool(raw.get("visible", True)),
                target_name=raw.get("target"),
                label=str(raw.get("variable", raw.get("list", monitor_id))),
                is_list=is_list,
                value=raw.get("value", 0),
            )
        )
        _ = owner  # ownership resolved again at render time
    return monitors
