"""Write Scratch 3 (.sb3) projects.

Mirrors scratch-vm's compact serialisation: input entries ``[1, block]``
(block and shadow are the same), ``[2, block]`` (no shadow), ``[3, block,
shadow]`` (block obscures a shadow), compressed primitive literals
(``[4..13, value, id?]``) for numbers/text/broadcasts/variables/lists, and
menu shadow blocks for costume/sound/backdrop/clone dropdowns.
"""

from __future__ import annotations

import hashlib
import json
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

BOOLEAN_SLOTS = frozenset({"CONDITION", "BOOLEAN", "BOOLEAN1", "BOOLEAN2"})
STRING_SLOTS = frozenset({"MESSAGE", "STRING1", "STRING2", "QUESTION", "ANSWER"})
MENU_SHADOW_SLOTS = frozenset(
    {"COSTUME", "BACKDROP", "SOUND_MENU", "CLONE_OPTION", "OBJECT", "TOUCHINGOBJECTMENU",
     "DISTANCETO"}
)
MENU_OPCODES = {
    "COSTUME": ("looks_costume", "COSTUME"),
    "BACKDROP": ("looks_backdrops", "BACKDROP"),
    "SOUND_MENU": ("sound_sounds_menu", "SOUND_MENU"),
    "CLONE_OPTION": ("control_create_clone_of_menu", "CLONE_OPTION"),
    "OBJECT": ("sensing_of_object_menu", "OBJECT"),
    "TOUCHINGOBJECTMENU": ("sensing_touchingobject_menu", "TOUCHINGOBJECTMENU"),
    "DISTANCETO": ("sensing_distanceto_menu", "DISTANCETO"),
}


def slug(text: str) -> str:
    return re.sub(r"\W+", "_", text)


def fmt_num(value: int | float) -> str:
    if isinstance(value, int):
        return str(value)
    f = float(value)
    if f.is_integer():
        return str(int(f))
    return repr(f)


@dataclass
class Rep:
    """A reporter block used as an input value."""

    opcode: str
    inputs: dict = field(default_factory=dict)
    fields: dict = field(default_factory=dict)


@dataclass
class St:
    """A stack block."""

    opcode: str
    inputs: dict = field(default_factory=dict)
    fields: dict = field(default_factory=dict)
    substacks: dict[str, list[St]] = field(default_factory=dict)


@dataclass
class Script:
    """A hat block with its body."""

    hat: str
    body: list[St]
    fields: dict = field(default_factory=dict)
    x: int = 30
    y: int = 30


class Target:
    """One stage/sprite: variables, costumes, sounds, scripts, block table."""

    def __init__(
        self,
        project: Project,
        name: str,
        *,
        is_stage: bool = False,
        layer_order: int = 0,
        x: int = 0,
        y: int = 0,
        direction: float = 90.0,
        size: float = 100.0,
        visible: bool = True,
        rotation_style: str = "all around",
    ) -> None:
        self.project = project
        self.name = name
        self.is_stage = is_stage
        self.layer_order = layer_order
        self.x = x
        self.y = y
        self.direction = direction
        self.size = size
        self.visible = visible
        self.rotation_style = rotation_style
        self.variables: dict[str, str] = {}
        self.variable_values: dict[str, object] = {}
        self.lists: dict[str, str] = {}
        self.list_values: dict[str, list] = {}
        self.costumes: list[dict] = []
        self.costume_names: list[str] = []
        self.sounds: list[dict] = []
        self.sound_names: list[str] = []
        self.scripts: list[Script] = []
        self.blocks: dict[str, dict] = {}
        self._counter = 0
        self._materialised = False
        self._prefix = slug(name).lower()[:8] + "_"

    # -- declarations ---------------------------------------------------
    def add_var(self, name: str, value: object = 0) -> str:
        var_id = f"{self._prefix}{slug(name)}"
        self.variables[var_id] = name
        self.variable_values[var_id] = value
        return var_id

    def add_list(self, name: str, items: list) -> str:
        list_id = f"{self._prefix}{slug(name)}"
        self.lists[list_id] = name
        self.list_values[list_id] = list(items)
        return list_id

    def add_costume(self, name: str, data: bytes, cx: float, cy: float) -> None:
        digest = hashlib.md5(data).hexdigest()
        self.project.assets[f"{digest}.png"] = data
        self.costumes.append(
            {
                "name": name,
                "bitmapResolution": 1,
                "dataFormat": "png",
                "assetId": digest,
                "md5ext": f"{digest}.png",
                "rotationCenterX": cx,
                "rotationCenterY": cy,
            }
        )
        self.costume_names.append(name)

    def add_sound(self, name: str, data: bytes, rate: int, frames: int) -> None:
        digest = hashlib.md5(data).hexdigest()
        self.project.assets[f"{digest}.wav"] = data
        self.sounds.append(
            {
                "name": name,
                "assetId": digest,
                "dataFormat": "wav",
                "format": "wav",
                "rate": rate,
                "sampleCount": frames,
                "md5ext": f"{digest}.wav",
            }
        )
        self.sound_names.append(name)

    def add_script(self, script: Script) -> None:
        self.scripts.append(script)

    # -- id lookup -------------------------------------------------------
    def var_id(self, name: str) -> str:
        for target in (self, self.project.stage):
            if target is None:
                continue
            for var_id, known in target.variables.items():
                if known == name:
                    return var_id
        raise KeyError(f"unknown variable {name!r} referenced from {self.name!r}")

    def list_id(self, name: str) -> str:
        for target in (self, self.project.stage):
            if target is None:
                continue
            for list_id, known in target.lists.items():
                if known == name:
                    return list_id
        raise KeyError(f"unknown list {name!r} referenced from {self.name!r}")

    # -- block materialisation -------------------------------------------
    def _new_block(
        self, opcode: str, *, parent: str | None, top: bool = False, x: int = 0, y: int = 0,
        shadow: bool = False,
    ) -> tuple[str, dict]:
        self._counter += 1
        block_id = f"{self._prefix}b{self._counter}"
        obj: dict = {
            "opcode": opcode,
            "next": None,
            "parent": parent,
            "inputs": {},
            "fields": {},
            "shadow": shadow,
            "topLevel": top,
        }
        if top:
            obj["x"] = x
            obj["y"] = y
        self.blocks[block_id] = obj
        return block_id, obj

    def _field_entry(self, spec) -> list:
        if isinstance(spec, tuple):
            kind, name = spec[0], spec[1]
            if kind == "var":
                return [name, self.var_id(name)]
            if kind == "list":
                return [name, self.list_id(name)]
            if kind == "bcast":
                return [name, self.project.broadcast_id(name)]
        return [spec]

    def _menu_block(self, slot: str, value: str, consumer: str) -> str:
        opcode, field_name = MENU_OPCODES[slot]
        block_id, obj = self._new_block(opcode, parent=consumer, shadow=True)
        obj["fields"][field_name] = [value]
        return block_id

    def _menu_default(self, slot: str) -> str:
        if slot == "COSTUME" and self.costume_names:
            return self.costume_names[0]
        if slot == "SOUND_MENU" and self.sound_names:
            return self.sound_names[0]
        if slot == "BACKDROP" and self.project.stage is not None:
            names = self.project.stage.costume_names
            if names:
                return names[0]
        if slot == "CLONE_OPTION":
            return "_myself_"
        return "_mouse_"

    def _shadow(self, slot: str, consumer: str) -> list | str:
        if slot in STRING_SLOTS:
            return [10, ""]
        if slot in MENU_SHADOW_SLOTS:
            # an obscured shadow serialises as the shadow's block id (scratch-vm
            # writes `[3, block, shadow]`; a bare entry like [1, id] fails the
            # Scratch schema, which wants a string or a primitive literal here)
            return self._menu_block(slot, self._menu_default(slot), consumer)
        return [4, "0"]

    def _emit_rep(self, rep: Rep, consumer: str) -> str:
        block_id, obj = self._new_block(rep.opcode, parent=consumer)
        obj["fields"] = {k: self._field_entry(v) for k, v in rep.fields.items()}
        for slot, spec in rep.inputs.items():
            obj["inputs"][slot] = self._input_entry(spec, slot=slot, consumer=block_id)
        return block_id

    def _input_entry(self, spec, *, slot: str, consumer: str) -> list:
        if isinstance(spec, bool):
            raise TypeError(f"boolean literals are not valid inputs ({slot})")
        if isinstance(spec, (int, float)):
            return [1, [4, fmt_num(spec)]]
        if isinstance(spec, str):
            return [1, [10, spec]]
        if isinstance(spec, tuple):
            kind = spec[0]
            name = spec[1]
            if kind == "var":
                return [3, [12, name, self.var_id(name)], self._shadow(slot, consumer)]
            if kind == "list":
                return [3, [13, name, self.list_id(name)], self._shadow(slot, consumer)]
            if kind == "bcast":
                return [1, [11, name, self.project.broadcast_id(name)]]
            if kind == "menu":
                _, menu_slot, value = spec
                return [1, self._menu_block(menu_slot, value, consumer)]
            raise TypeError(f"unknown input tag {kind!r} ({slot})")
        if isinstance(spec, Rep):
            if slot in BOOLEAN_SLOTS:
                return [2, self._emit_rep(spec, consumer)]
            block_id = self._emit_rep(spec, consumer)
            return [3, block_id, self._shadow(slot, consumer)]
        raise TypeError(f"cannot use {spec!r} as input {slot}")

    def _emit_st(self, st: St, parent: str | None) -> str:
        block_id, obj = self._new_block(st.opcode, parent=parent)
        obj["fields"] = {k: self._field_entry(v) for k, v in st.fields.items()}
        for slot, spec in st.inputs.items():
            obj["inputs"][slot] = self._input_entry(spec, slot=slot, consumer=block_id)
        for slot, chain in st.substacks.items():
            if not chain:
                continue
            previous = block_id
            first = True
            for inner in chain:
                inner_id = self._emit_st(inner, parent=previous)
                if first:
                    obj["inputs"][slot] = [2, inner_id]
                    first = False
                else:
                    self.blocks[previous]["next"] = inner_id
                previous = inner_id
        return block_id

    def _materialise(self) -> None:
        if self._materialised:
            return
        self._materialised = True
        for script in self.scripts:
            hat_id, hat = self._new_block(
                script.hat, parent=None, top=True, x=script.x, y=script.y
            )
            hat["fields"] = {k: self._field_entry(v) for k, v in script.fields.items()}
            previous = hat_id
            for st in script.body:
                st_id = self._emit_st(st, parent=previous)
                self.blocks[previous]["next"] = st_id
                previous = st_id

    # -- serialisation ----------------------------------------------------
    def to_json(self) -> dict:
        self._materialise()
        data: dict = {
            "isStage": self.is_stage,
            "name": self.name,
            "variables": {
                vid: [self.variables[vid], self.variable_values[vid]]
                for vid in self.variables
            },
            "lists": {
                lid: [self.lists[lid], self.list_values[lid]] for lid in self.lists
            },
            "broadcasts": dict(self.project.broadcasts),
            "blocks": self.blocks,
            "comments": {},
            "currentCostume": 0,
            "costumes": self.costumes,
            "sounds": self.sounds,
            "volume": 100,
            "layerOrder": self.layer_order,
        }
        if self.is_stage:
            data.update(
                tempo=60, videoTransparency=50, videoState="on", textToSpeechLanguage=None
            )
        else:
            data.update(
                x=self.x,
                y=self.y,
                direction=self.direction,
                draggable=False,
                rotationStyle=self.rotation_style,
                visible=self.visible,
                size=self.size,
            )
        return data


class Project:
    """A whole .sb3: targets, broadcasts, monitors, assets."""

    def __init__(self, name: str = "Star Game") -> None:
        self.name = name
        self.stage: Target | None = None
        self.sprites: list[Target] = []
        self.broadcasts: dict[str, str] = {}
        self.monitors: list[dict] = []
        self.assets: dict[str, bytes] = {}

    def add_stage(self, name: str = "Stage") -> Target:
        self.stage = Target(self, name, is_stage=True, layer_order=0)
        return self.stage

    def add_sprite(self, name: str, **kwargs) -> Target:
        target = Target(self, name, **kwargs)
        self.sprites.append(target)
        return target

    def broadcast_id(self, name: str) -> str:
        for broadcast_id, known in self.broadcasts.items():
            if known == name:
                return broadcast_id
        broadcast_id = f"bcast_{slug(name)}"
        self.broadcasts[broadcast_id] = name
        return broadcast_id

    def add_monitor(self, var_name: str, x: int, y: int) -> None:
        if self.stage is None:
            raise RuntimeError("stage must exist before monitors are added")
        var_id = self.stage.var_id(var_name)
        self.monitors.append(
            {
                "id": var_id,
                "mode": "default",
                "opcode": "data_variable",
                "params": {"VARIABLE": var_name},
                "spriteName": None,
                "value": self.stage.variable_values.get(var_id, 0),
                "width": 0,
                "height": 0,
                "x": x,
                "y": y,
                "visible": True,
                "sliderMin": 0,
                "sliderMax": 100,
                "isDiscrete": True,
            }
        )

    def to_json(self) -> dict:
        if self.stage is None:
            raise RuntimeError("project has no stage")
        return {
            "targets": [self.stage.to_json(), *(s.to_json() for s in self.sprites)],
            "monitors": self.monitors,
            "extensions": [],
            "meta": {"semver": "3.0.0", "vm": "2.32.2", "agent": "sb3conv"},
        }

    def write(self, path: Path) -> Path:
        data = json.dumps(self.to_json(), ensure_ascii=False, separators=(",", ":"))
        path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as bundle:
            bundle.writestr("project.json", data)
            for filename, payload in sorted(self.assets.items()):
                bundle.writestr(filename, payload)
        return path
