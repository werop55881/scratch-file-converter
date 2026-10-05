"""Helpers that build Scratch project.json structures the way the editor does."""

from __future__ import annotations

from typing import Any


class BlockFactory:
    """Small DSL for writing block graphs in tests."""

    def __init__(self) -> None:
        self.blocks: dict[str, dict[str, Any]] = {}
        self._counter = 0

    def _new_id(self) -> str:
        self._counter += 1
        return f"block{self._counter}"

    def hat(self, opcode: str, *, fields: dict | None = None, x: int = 0, y: int = 0) -> str:
        block_id = self._new_id()
        self.blocks[block_id] = {
            "opcode": opcode,
            "next": None,
            "parent": None,
            "inputs": {},
            "fields": fields or {},
            "topLevel": True,
            "x": x,
            "y": y,
        }
        return block_id

    def stack(
        self,
        opcode: str,
        *,
        inputs: dict | None = None,
        fields: dict | None = None,
        parent: str | None = None,
    ) -> str:
        block_id = self._new_id()
        self.blocks[block_id] = {
            "opcode": opcode,
            "next": None,
            "parent": parent,
            "inputs": inputs or {},
            "fields": fields or {},
            "topLevel": False,
            "x": 0,
            "y": 0,
        }
        return block_id

    def reporter(self, opcode: str, *, inputs: dict | None = None, fields: dict | None = None) -> str:
        """A standalone reporter block (parent is set when it is used as input)."""
        block_id = self._new_id()
        self.blocks[block_id] = {
            "opcode": opcode,
            "next": None,
            "parent": None,
            "inputs": inputs or {},
            "fields": fields or {},
            "topLevel": False,
            "x": 0,
            "y": 0,
        }
        return block_id

    def chain(self, *block_ids: str) -> None:
        """Link blocks into a straight stack, parenting each to the previous."""
        for previous, current in zip(block_ids, block_ids[1:], strict=False):
            self.blocks[previous]["next"] = current
            self.blocks[current]["parent"] = previous

    def substack(self, parent_id: str, input_name: str, first_block_id: str) -> None:
        """Attach a C-shaped body to a control block."""
        self.blocks[parent_id]["inputs"][input_name] = [1, first_block_id]
        self.blocks[first_block_id]["parent"] = parent_id

    def wire_reporter(self, parent_id: str, input_name: str, reporter_id: str) -> None:
        """Use a reporter as an input of a block."""
        self.blocks[parent_id]["inputs"][input_name] = [3, reporter_id, [10, ""]]
        self.blocks[reporter_id]["parent"] = parent_id


def number(value: str | float) -> list:
    """A numeric literal input."""
    return [1, [4, str(value)]]


def text(value: str) -> list:
    """A string literal input."""
    return [1, [10, value]]


def broadcast_input(broadcast_id: str) -> list:
    """A broadcast literal input (type 11, as scratch-vm serialises it)."""
    return [1, [11, broadcast_id]]


def variable_input(var_name: str, var_id: str) -> list:
    """A variable getter compressed into an input (type 12)."""
    return [1, [12, var_name, var_id]]


def make_stage(**overrides: Any) -> dict[str, Any]:
    stage = {
        "isStage": True,
        "name": "Stage",
        "variables": {},
        "lists": {},
        "broadcasts": {},
        "blocks": {},
        "costumes": [],
        "sounds": [],
        "currentCostume": 0,
        "backdrops": [],
        "volume": 100,
        "layerOrder": 0,
        "tempo": 60,
        "videoTransparency": 50,
        "videoState": "on",
        "textToSpeechLanguage": None,
        "comments": {},
    }
    stage.update(overrides)
    return stage


def make_sprite(name: str = "Sprite1", **overrides: Any) -> dict[str, Any]:
    sprite = {
        "isStage": False,
        "name": name,
        "variables": {},
        "lists": {},
        "broadcasts": {},
        "blocks": {},
        "costumes": [],
        "sounds": [],
        "currentCostume": 0,
        "x": 0,
        "y": 0,
        "direction": 90,
        "draggable": False,
        "rotationStyle": "all around",
        "volume": 100,
        "visible": True,
        "size": 100,
        "layerOrder": 1,
        "comments": {},
    }
    sprite.update(overrides)
    return sprite


def sample_project() -> dict[str, Any]:
    """A tiny but realistic project: variable counter, broadcast, clone, sound."""
    stage_factory = BlockFactory()
    sprite_factory = BlockFactory()

    # Stage: when green flag -> forever: change [dust] by 1
    flag = stage_factory.hat("event_whenflagclicked", x=50, y=50)
    forever = stage_factory.stack("control_forever", parent=flag)
    change = stage_factory.stack(
        "data_changevariableby",
        inputs={"VALUE": number(1)},
        fields={"VARIABLE": ["dust", "var_dust"]},
        parent=forever,
    )
    stage_factory.chain(flag, forever, change)
    stage_factory.substack(forever, "SUBSTACK", change)

    # Sprite: when key pressed -> broadcast "boom" and wait
    key = sprite_factory.hat(
        "event_whenkeypressed", fields={"KEY_OPTION": ["space", None]}, x=50, y=200
    )
    say = sprite_factory.stack(
        "event_broadcastAndWait",
        inputs={"BROADCAST_INPUT": broadcast_input("bcast_boom")},
        parent=key,
    )
    sprite_factory.chain(key, say)

    sprite = make_sprite(
        "Star",
        blocks=sprite_factory.blocks,
        comments={"c1": {"blockId": key, "text": "lang: js", "x": 0, "y": 0, "minimize": False}},
        x=10,
        y=20,
        layerOrder=1,
        costumes=[
            {
                "name": "star",
                "md5ext": "abc123.png",
                "assetId": "abc123",
                "rotationCenterX": 40,
                "rotationCenterY": 40,
                "bitmapResolution": 1,
                "id": "star-id",
            }
        ],
        sounds=[{"name": "ping", "md5ext": "def456.wav", "assetId": "def456", "sampleRate": 44100, "sampleCount": 10}],
    )
    stage = make_stage(
        broadcasts={"bcast_boom": "boom"},
        blocks=stage_factory.blocks,
        variables={"var_dust": ["dust", 0]},
    )
    return {
        "targets": [stage, sprite],
        "monitors": [
            {
                "id": "var_dust",
                "mode": "default",
                "x": 8,
                "y": 6,
                "width": 0,
                "height": 0,
                "visible": True,
                "sliderMin": 0,
                "sliderMax": 100,
                "sliderStep": 1,
                "value": 0,
                "variable": "dust",
                "target": "Star",
            }
        ],
        "extensions": [],
        "meta": {"semver": "3.0.0", "vm": "0.2.0", "agent": "tests"},
    }
