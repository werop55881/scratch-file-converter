"""Scratch 3 project model: targets, blocks, scripts, assets."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Assets
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Asset:
    """A file stored in the .sb3 zip (costume image or sound)."""

    asset_id: str
    md5ext: str
    name: str = ""

    @property
    def data_format(self) -> str:
        return self.md5ext.rsplit(".", 1)[-1].lower() if "." in self.md5ext else ""

    @property
    def filename(self) -> str:
        return f"{self.asset_id}.{self.data_format}" if self.data_format else self.asset_id


@dataclass(frozen=True)
class Costume:
    name: str
    asset: Asset
    rotation_center_x: float
    rotation_center_y: float
    bitmap_resolution: float = 1.0
    md5ext: str = ""
    costume_id: str = ""

    def matches(self, ref: str) -> bool:
        """Whether a dropdown/literal value refers to this costume."""
        ref = str(ref)
        return ref in {
            self.name,
            self.costume_id,
            self.md5ext or self.asset.md5ext,
            self.asset.asset_id,
        }


@dataclass(frozen=True)
class Sound:
    name: str
    asset: Asset
    md5ext: str = ""
    sound_id: str = ""

    def matches(self, ref: str) -> bool:
        ref = str(ref)
        return ref in {self.name, self.sound_id, self.md5ext or self.asset.md5ext, self.asset.asset_id}


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Literal:
    """A literal input value (number, string, colour, broadcast id, ...).

    ``id_value`` carries the secondary id for typed primitives: broadcast id
    (type 11), variable id (type 12) and list id (type 13).
    """

    value: str | float
    type_code: int | None = None
    id_value: str | None = None

    @property
    def is_number(self) -> bool:
        if isinstance(self.value, (int, float)):
            return True
        try:
            float(self.value)
        except (TypeError, ValueError):
            return False
        return True

    def as_number(self) -> float:
        try:
            return float(self.value)
        except (TypeError, ValueError):
            return 0.0

    def as_text(self) -> str:
        if isinstance(self.value, float) and self.value.is_integer():
            return str(int(self.value))
        return str(self.value)


@dataclass(frozen=True)
class BlockRef:
    """An input that points at another block (reporter or substack)."""

    block_id: str


InputValue = Literal | BlockRef | None


@dataclass
class Block:
    """One node of a target's block graph."""

    id: str
    opcode: str
    inputs: dict[str, InputValue] = field(default_factory=dict)
    fields: dict[str, tuple[str, str | None]] = field(default_factory=dict)
    mutation: dict[str, str] = field(default_factory=dict)
    next_id: str | None = None
    parent_id: str | None = None
    top_level: bool = False
    x: float = 0.0
    y: float = 0.0

    def input_block(self, name: str) -> Block | None:
        value = self.inputs.get(name)
        return value.block_id if isinstance(value, BlockRef) else None

    def literal(self, name: str, default: str = "") -> str:
        value = self.inputs.get(name)
        if isinstance(value, Literal):
            return value.as_text()
        field_value = self.fields.get(name)
        if field_value is not None:
            return field_value[0]
        return default

    def field(self, name: str, default: str = "") -> str:
        field_value = self.fields.get(name)
        return field_value[0] if field_value is not None else default


# ---------------------------------------------------------------------------
# Scripts and targets
# ---------------------------------------------------------------------------


@dataclass
class Script:
    """A hat block plus everything reachable from it."""

    hat: Block
    target: Target
    comment: str = ""
    script_id: str = ""

    @property
    def name(self) -> str:
        return self.script_id or self.hat.id

    def __post_init__(self) -> None:
        if not self.script_id:
            self.script_id = self.hat.id

    def declared_language(self) -> str | None:
        """Language override written as a comment on the hat block.

        Recognises lines such as ``lang: js`` or ``lang=python``.
        """
        for line in self.comment.splitlines():
            stripped = line.strip().lower()
            if stripped.startswith("lang") and len(stripped) > 4 and stripped[4] in ":=":
                value = stripped[5:].strip().split()[0] if stripped[5:].strip() else ""
                if value:
                    return value
        return None

    def iter_stack(self) -> Iterator[Block]:
        """Yield the blocks of this script in execution order (depth first)."""
        seen: set[str] = set()

        def walk(block_id: str) -> Iterator[Block]:
            block = self.target.blocks.get(block_id)
            while block is not None and block.id not in seen:
                seen.add(block.id)
                yield block
                for value in block.inputs.values():
                    if isinstance(value, BlockRef) and value.block_id not in seen:
                        yield from walk(value.block_id)
                block = self.target.blocks.get(block.next_id) if block.next_id else None

        yield from walk(self.hat.id)


@dataclass
class Target:
    """A stage or a sprite."""

    is_stage: bool
    name: str
    variables: dict[str, tuple[str, object]] = field(default_factory=dict)
    lists: dict[str, tuple[str, list]] = field(default_factory=dict)
    blocks: dict[str, Block] = field(default_factory=dict)
    scripts: list[Script] = field(default_factory=list)
    costumes: list[Costume] = field(default_factory=list)
    sounds: list[Sound] = field(default_factory=list)
    comments: dict[str, str] = field(default_factory=dict)
    current_costume: int = 0
    x: float = 0.0
    y: float = 0.0
    direction: float = 90.0
    size: float = 100.0
    visible: bool = True
    rotation_style: str = "all around"
    layer_order: int = 0
    volume: int = 100
    draggable: bool = False
    tempo: int = 60
    video_state: str = "on"

    # convenience -----------------------------------------------------------
    @property
    def sprite_name(self) -> str:
        return "Stage" if self.is_stage else self.name

    @property
    def variable_owner_ids(self) -> set[str]:
        return set(self.variables)

    @property
    def list_owner_ids(self) -> set[str]:
        return set(self.lists)

    def costume_by_ref(self, ref: str) -> Costume | None:
        for costume in self.costumes:
            if costume.matches(ref):
                return costume
        return None

    def sound_by_ref(self, ref: str) -> Sound | None:
        for sound in self.sounds:
            if sound.matches(ref):
                return sound
        return None

    def sorted_scripts(self) -> list[Script]:
        """Scripts in visual order (top to bottom, left to right)."""
        return sorted(self.scripts, key=lambda s: (round(s.hat.y), round(s.hat.x)))


@dataclass
class Monitor:
    """A variable/list watcher drawn on the stage."""

    monitor_id: str
    mode: str = "default"
    x: float = 0.0
    y: float = 0.0
    visible: bool = True
    target_name: str | None = None
    label: str = ""
    is_list: bool = False
    value: object = 0


@dataclass
class Project:
    """A whole .sb3 project."""

    targets: list[Target] = field(default_factory=list)
    broadcasts: dict[str, str] = field(default_factory=dict)
    monitors: list[Monitor] = field(default_factory=list)
    meta: dict = field(default_factory=dict)
    extensions: list[str] = field(default_factory=list)
    # script id (hat block id) -> language name, from ``lang:`` comments
    script_languages: dict[str, str] = field(default_factory=dict)

    @property
    def stage(self) -> Target:
        for target in self.targets:
            if target.is_stage:
                return target
        raise ValueError("project has no stage target")

    @property
    def sprites(self) -> list[Target]:
        sprites = [t for t in self.targets if not t.is_stage]
        return sorted(sprites, key=lambda t: t.layer_order)

    @property
    def render_order(self) -> list[Target]:
        return sorted(self.targets, key=lambda t: t.layer_order)

    def all_scripts(self) -> Iterator[Script]:
        for target in self.render_order:
            yield from target.sorted_scripts()

    def broadcast_name(self, broadcast_id: str) -> str:
        return self.broadcasts.get(broadcast_id, broadcast_id)

    def find_target(self, name: str) -> Target | None:
        for target in self.targets:
            if target.name == name:
                return target
        return None

    def var_owner(self, var_id: str) -> Target | None:
        for target in self.targets:
            if var_id in target.variables:
                return target
        return None

    def list_owner(self, list_id: str) -> Target | None:
        for target in self.targets:
            if list_id in target.lists:
                return target
        return None
