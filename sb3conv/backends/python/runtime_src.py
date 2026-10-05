"""Scratch runtime for converted projects (pygame).

This module is copied next to the generated ``main.py`` as ``runtime.py``.
It must stay self-contained: standard library + pygame only.

Generated scripts are generator functions ``fn(ctx, rt)``; the scheduler steps
them once per frame. A bare ``yield`` waits one frame, ``yield from rt.wait...``
waits longer.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import math
import os
import random
import sys
import time
import traceback
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

import pygame

STAGE_W = 480
STAGE_H = 360
DEFAULT_FPS = 30
MAX_CLONES = 300
MAX_STEPS_PER_FRAME = 20000

# ---------------------------------------------------------------------------
# Scratch-flavoured helper functions (used by generated code)
# ---------------------------------------------------------------------------


def s_num(value) -> float:
    """Scratch-style cast to number."""
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return float("nan") if value.strip() in ("inf", "-inf") else 0.0
    return 0.0


def s_str(value) -> str:
    """Scratch-style cast to string (used for display and joins)."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        if value != value:
            return "NaN"
        if value == float("inf"):
            return "Infinity"
        if value == float("-inf"):
            return "-Infinity"
        if value.is_integer():
            return str(int(value))
        return str(value)
    if isinstance(value, list):
        return ", ".join(s_str(v) for v in value)
    return str(value)


def _looks_numeric(value) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return True
    if isinstance(value, str):
        try:
            float(value.strip())
            return True
        except ValueError:
            return False
    return False


def _both_numeric(a, b) -> bool:
    return _looks_numeric(a) and _looks_numeric(b)


def _truthy(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0 and value == value
    if isinstance(value, str):
        return value != ""
    if isinstance(value, list):
        return len(value) > 0
    return bool(value)


def s_add(a, b) -> float:
    return s_num(a) + s_num(b)


def s_sub(a, b) -> float:
    return s_num(a) - s_num(b)


def s_mul(a, b) -> float:
    return s_num(a) * s_num(b)


def s_div(a, b):
    bn, an = s_num(b), s_num(a)
    if bn == 0:
        if an != an:
            return "NaN"
        return "-Infinity" if an < 0 else "Infinity"
    return an / bn


def _is_whole(value) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return True
    if isinstance(value, float):
        return value.is_integer()
    if isinstance(value, str):
        try:
            return float(value).is_integer()
        except ValueError:
            return False
    return False


def s_random(a, b):
    lo, hi = s_num(a), s_num(b)
    if hi < lo:
        lo, hi = hi, lo
    if _is_whole(a) and _is_whole(b):
        return float(random.randint(int(lo), int(hi)))
    return random.uniform(lo, hi)


def s_gt(a, b) -> bool:
    if _both_numeric(a, b):
        return s_num(a) > s_num(b)
    return s_str(a) > s_str(b)


def s_lt(a, b) -> bool:
    if _both_numeric(a, b):
        return s_num(a) < s_num(b)
    return s_str(a) < s_str(b)


def s_eq(a, b) -> bool:
    if _both_numeric(a, b):
        x, y = s_num(a), s_num(b)
        if x != x or y != y:
            return False
        return x == y
    return s_str(a).casefold() == s_str(b).casefold()


def s_not(value) -> bool:
    return not _truthy(value)


def s_join(a, b) -> str:
    return s_str(a) + s_str(b)


def s_letter(index, text) -> str:
    string = s_str(text)
    try:
        i = int(s_num(index))
    except (ValueError, OverflowError):
        return ""
    if i < 1 or i > len(string):
        return ""
    return string[i - 1]


def s_length(value) -> int:
    return len(s_str(value))


def s_contains(haystack, needle) -> bool:
    return s_str(needle).casefold() in s_str(haystack).casefold()


def s_mod(a, b) -> float:
    an, bn = s_num(a), s_num(b)
    if bn == 0:
        return float("nan")
    return an - bn * math.floor(an / bn)


def s_round(value) -> float:
    return float(math.floor(s_num(value) + 0.5))


def s_mathop(op: str, value) -> float:
    n = s_num(value)
    try:
        if op == "abs":
            return abs(n)
        if op == "ceiling":
            return float(math.ceil(n))
        if op == "floor":
            return float(math.floor(n))
        if op == "sqrt":
            return math.sqrt(n) if n >= 0 else float("nan")
        if op == "sin":
            return math.sin(math.radians(n))
        if op == "cos":
            return math.cos(math.radians(n))
        if op == "tan":
            return math.tan(math.radians(n))
        if op == "asin":
            return math.degrees(math.asin(n)) if -1 <= n <= 1 else float("nan")
        if op == "acos":
            return math.degrees(math.acos(n)) if -1 <= n <= 1 else float("nan")
        if op == "atan":
            return math.degrees(math.atan(n))
        if op == "ln":
            return math.log(n) if n > 0 else float("nan")
        if op == "log":
            return math.log10(n) if n > 0 else float("nan")
        if op in ("e ^", "e^"):
            return math.exp(n)
        if op in ("10 ^", "10^"):
            return 10.0**n
    except ValueError:
        return float("nan")
    return 0.0


def repeat_count(value) -> int:
    """How often Scratch's repeat loop runs (rounded, never negative)."""
    return max(0, int(s_round(value)))


# --- list helpers -----------------------------------------------------------


def _list_index(lst, index) -> int | None:
    """Resolve a Scratch list index ("last", numbers, negatives) to 0-based."""
    if not isinstance(lst, list):
        return None
    size = len(lst)
    if s_str(index) == "last":
        return size - 1 if size else None
    try:
        k = int(s_num(index))
    except (ValueError, OverflowError):
        return None
    if k == 0:
        return None
    pos = k - 1 if k > 0 else size + k
    if 0 <= pos < size:
        return pos
    return None


def list_item(lst, index):
    pos = _list_index(lst, index)
    if pos is None:
        return ""
    return lst[pos]


def list_delete(lst, index) -> None:
    if not isinstance(lst, list):
        return
    if s_str(index) == "all":
        lst.clear()
        return
    pos = _list_index(lst, index)
    if pos is not None:
        del lst[pos]


def list_clear(lst) -> None:
    if isinstance(lst, list):
        lst.clear()


def list_add(lst, item) -> None:
    if isinstance(lst, list):
        lst.append(item)


def list_insert(lst, index, item) -> None:
    if not isinstance(lst, list):
        return
    size = len(lst)
    if s_str(index) == "last":
        lst.append(item)
        return
    try:
        k = int(s_num(index))
    except (ValueError, OverflowError):
        return
    if k < 1 or k > size + 1:
        return
    lst.insert(k - 1, item)


def list_replace(lst, index, item) -> None:
    pos = _list_index(lst, index)
    if pos is not None:
        lst[pos] = item


def list_index_of(lst, item):
    if not isinstance(lst, list):
        return ""
    for i, existing in enumerate(lst, start=1):
        if s_eq(existing, item):
            return float(i)
    return ""


def list_length(value) -> float:
    if isinstance(value, list):
        return float(len(value))
    if isinstance(value, str):
        return float(len(value))
    return 0.0


def list_contains(lst, item) -> bool:
    if not isinstance(lst, list):
        return False
    return any(s_eq(existing, item) for existing in lst)


# ---------------------------------------------------------------------------
# Key mapping
# ---------------------------------------------------------------------------

KEYMAP: dict[str, int] = {
    "space": pygame.K_SPACE,
    "left arrow": pygame.K_LEFT,
    "right arrow": pygame.K_RIGHT,
    "up arrow": pygame.K_UP,
    "down arrow": pygame.K_DOWN,
    "enter": pygame.K_RETURN,
    "any": -1,
}
for _ch in "abcdefghijklmnopqrstuvwxyz":
    KEYMAP[_ch] = ord(_ch)
for _ch in "0123456789":
    KEYMAP[_ch] = ord(_ch)


def pygame_key_to_scratch(key: int) -> str | None:
    if key == pygame.K_SPACE:
        return "space"
    if key == pygame.K_LEFT:
        return "left arrow"
    if key == pygame.K_RIGHT:
        return "right arrow"
    if key == pygame.K_UP:
        return "up arrow"
    if key == pygame.K_DOWN:
        return "down arrow"
    if key == pygame.K_RETURN:
        return "enter"
    if pygame.K_a <= key <= pygame.K_z:
        return chr(ord("a") + key - pygame.K_a)
    if pygame.K_0 <= key <= pygame.K_9:
        return chr(ord("0") + key - pygame.K_0)
    if pygame.K_KP0 <= key <= pygame.K_KP9:
        return chr(ord("0") + key - pygame.K_KP0)
    return None


# ---------------------------------------------------------------------------
# Assets
# ---------------------------------------------------------------------------


class Costume:
    """One costume/backdrop: a surface in stage units plus its anchor."""

    def __init__(self, data: dict, assets_dir: Path, fallback_colour=(120, 120, 160)) -> None:
        self.name = str(data.get("name", "costume"))
        self.costume_id = str(data.get("id", self.name))
        path = assets_dir / str(data.get("file", ""))
        self.resolution = float(data.get("resolution", 1) or 1)
        self.cx = float(data.get("cx", 0)) / self.resolution
        self.cy = float(data.get("cy", 0)) / self.resolution
        self.missing = False
        surface: pygame.Surface | None = None
        suffix = path.suffix.lower()
        if suffix == ".svg":
            print(f"warning: SVG costume {self.name!r} cannot be rendered by the pygame runtime; "
                  "re-export it as PNG", file=sys.stderr)
            self.missing = True
        elif path.exists():
            try:
                surface = pygame.image.load(str(path))
            except pygame.error as exc:
                print(f"warning: could not load costume {path.name}: {exc}", file=sys.stderr)
                self.missing = True
            else:
                # no video mode yet; run() converts after set_mode()
                with contextlib.suppress(pygame.error):
                    surface = surface.convert_alpha()
        if surface is None:
            surface = pygame.Surface((32, 32), pygame.SRCALPHA)
            surface.fill((*fallback_colour, 255))
            self.missing = True
        if self.resolution and self.resolution != 1:
            w = max(1, int(surface.get_width() / self.resolution))
            h = max(1, int(surface.get_height() / self.resolution))
            surface = pygame.transform.smoothscale(surface, (w, h))
        self.surface = surface
        # tight alpha bounds: Scratch collides on non-transparent pixels, not
        # the full costume canvas (character art often sits in padded canvases)
        bbox = surface.get_bounding_rect()
        if bbox.width <= 0 or bbox.height <= 0:
            bbox = surface.get_rect()
        self.tight = bbox
        # per-pixel collision mask for Scratch-faithful touching tests
        self.mask = pygame.mask.from_surface(surface, 1)

    @property
    def width(self) -> float:
        return float(self.surface.get_width())

    @property
    def height(self) -> float:
        return float(self.surface.get_height())


class SoundAsset:
    def __init__(self, data: dict, assets_dir: Path, available: bool) -> None:
        self.name = str(data.get("name", "sound"))
        self.sound: pygame.mixer.Sound | None = None
        if not available:
            return
        path = assets_dir / str(data.get("file", ""))
        if not path.exists():
            print(f"warning: sound file {path.name} missing", file=sys.stderr)
            return
        try:
            self.sound = pygame.mixer.Sound(str(path))
        except pygame.error as exc:
            print(f"warning: could not load sound {path.name}: {exc}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Actors
# ---------------------------------------------------------------------------


@dataclass
class TargetDef:
    """Static description of a sprite/stage loaded from the manifest."""

    name: str
    is_stage: bool = False
    x: float = 0.0
    y: float = 0.0
    direction: float = 90.0
    size: float = 100.0
    visible: bool = True
    rotation_style: str = "all around"
    layer_order: int = 0
    volume: float = 100.0
    current_costume: int = 0
    costumes: list[Costume] = field(default_factory=list)
    sounds: dict[str, SoundAsset] = field(default_factory=dict)
    variables: dict = field(default_factory=dict)
    lists: dict[str, list] = field(default_factory=dict)


class Actor:
    """A stage, a sprite, or a clone: everything with runtime state."""

    def __init__(self, runtime: Runtime, target: TargetDef, is_clone: bool = False) -> None:
        self.rt = runtime
        self.target = target
        self.is_clone = is_clone
        self.x = target.x
        self.y = target.y
        self.direction = target.direction
        self.size = target.size
        self.visible = target.visible
        self.rotation_style = target.rotation_style
        self.volume = target.volume
        self.current_costume = target.current_costume
        self.effects = {"ghost": 0.0, "color": 0.0, "fisheye": 0.0, "whirl": 0.0,
                        "pixelate": 0.0, "mosaic": 0.0, "brightness": 0.0}
        self.sound_effects = {"PITCH": 0.0, "PAN": 0.0}
        self.say = None
        self.think = None
        self.dead = False
        # "for this sprite only" variables are per-instance: every clone gets
        # its own copy (Scratch copies the creator's current values, see
        # Runtime.create_clone), the original shares the target's storage
        if is_clone:
            self.vars = dict(target.variables)
            self.lists = {k: list(v) for k, v in target.lists.items()}
        else:
            self.vars = target.variables
            self.lists = target.lists
        self._draw_cache: dict = {}

    # -- costumes ---------------------------------------------------------
    @property
    def costume(self) -> Costume | None:
        costumes = self.target.costumes
        if not costumes:
            return None
        return costumes[int(self.current_costume) % len(costumes)]

    def set_costume(self, ref) -> None:
        costumes = self.target.costumes
        if not costumes:
            return
        text = s_str(ref)
        for i, costume in enumerate(costumes):
            if text in (costume.name, costume.costume_id):
                if i != self.current_costume:
                    self.current_costume = i
                    self._draw_cache.clear()
                return
        if _looks_numeric(text):
            index = int(s_num(text)) - 1  # Scratch counts costumes from 1
            new = max(0, min(index, len(costumes) - 1))
            if new != self.current_costume:
                self.current_costume = new
                self._draw_cache.clear()
            return
        self.rt.warn_once(f"unknown costume {text!r} for sprite {self.target.name!r}")

    def next_costume(self) -> None:
        costumes = self.target.costumes
        if costumes:
            new = (int(self.current_costume) + 1) % len(costumes)
            if new != self.current_costume:
                self.current_costume = new
                self._draw_cache.clear()

    def remove_clone(self) -> None:
        self.rt.remove_clone(self)

    # -- geometry ---------------------------------------------------------
    def half_size(self) -> tuple[float, float]:
        costume = self.costume
        if costume is None:
            return 0.0, 0.0
        scale = self.size / 100.0
        return costume.width * scale / 2.0, costume.height * scale / 2.0

    def rect(self) -> pygame.Rect:
        costume = self.costume
        if costume is None:
            return pygame.Rect(int(self.x), int(self.y), 1, 1)
        scale = self.size / 100.0
        t = costume.tight
        left = self.x + (t.left - costume.cx) * scale
        top = self.y + (costume.cy - t.bottom) * scale
        width = t.width * scale
        height = t.height * scale
        return pygame.Rect(int(left), int(top), max(1, int(width)), max(1, int(height)))

    def opaque_at(self, sx: float, sy: float) -> bool:
        """True when stage point (sx, sy) lands on one of our opaque pixels."""
        costume = self.costume
        if costume is None:
            return False
        scale = self.size / 100.0
        if scale <= 0:
            return False
        px = int((sx - self.x) / scale + costume.cx)
        py = int(costume.cy - (sy - self.y) / scale)
        w = costume.surface.get_width()
        h = costume.surface.get_height()
        if not (0 <= px < w and 0 <= py < h):
            return False
        return bool(costume.mask.get_at((px, py)))

    def overlaps(self, other: Actor) -> bool:
        """Scratch-style pixel-perfect collision (rotation ignored)."""
        if not self.rect().colliderect(other.rect()):
            return False
        a, b = self.costume, other.costume
        if a is None or b is None:
            return True
        sa = self.size / 100.0
        sb = other.size / 100.0
        if sa <= 0 or sb <= 0:
            return False
        # stage position of each mask's pixel (0, 0) corner
        ax = self.x - a.cx * sa
        ay = self.y + a.cy * sa
        bx = other.x - b.cx * sb
        by = other.y + b.cy * sb
        dx = int(round((bx - ax) / sa))
        dy = int(round((ay - by) / sa))
        return a.mask.overlap(b.mask, (dx, dy)) is not None


# ---------------------------------------------------------------------------
# Scripts and threads
# ---------------------------------------------------------------------------


@dataclass
class ScriptReg:
    sprite: str
    hat: str
    fields: dict
    fn: Callable


class Thread:
    __slots__ = ("generator", "actor", "reg", "done", "stepped_frame")

    def __init__(self, generator, actor: Actor, reg: ScriptReg) -> None:
        self.generator = generator
        self.actor = actor
        self.reg = reg
        self.done = False
        self.stepped_frame = -1


# ---------------------------------------------------------------------------
# Runtime
# ---------------------------------------------------------------------------


class Runtime:
    """Everything a converted project needs: state, scheduler and renderer."""

    def __init__(
        self,
        manifest: dict,
        scripts: list[ScriptReg],
        *,
        manifest_path: Path | None = None,
        scale: int | None = None,
        fps: int | None = None,
        seed: int | None = None,
        smoke: int = 0,
    ) -> None:
        base = manifest_path.parent if manifest_path else Path(".")
        self.assets_dir = base / manifest.get("assetDir", "assets")
        self.scale = max(1, int(scale or manifest.get("scale", 2)))
        self.fps = max(1, int(fps or manifest.get("fps", DEFAULT_FPS)))
        self.smoke = smoke
        if seed is not None:
            random.seed(seed)

        self.warned: set[str] = set()
        self.errors: list[str] = []

        # target definitions
        stage_def = self._load_target(manifest["stage"], is_stage=True)
        sprite_defs = [self._load_target(d) for d in manifest.get("sprites", [])]
        self.stage_def = stage_def
        self.sprite_defs = {d.name: d for d in sprite_defs}
        self.target_defs = [stage_def, *sprite_defs]

        # actors
        self.stage_actor = Actor(self, stage_def)
        self.actors: list[Actor] = [self.stage_actor]
        for definition in sprite_defs:
            self.actors.append(Actor(self, definition))
        self.layers: list[Actor] = [
            a for a in self.actors if not a.target.is_stage
        ]
        self.layers.sort(key=lambda a: a.target.layer_order)

        # global state
        self.vars = stage_def.variables
        self.lists = stage_def.lists
        self.timer = 0.0
        self.answer = ""
        self.loudness = 100.0
        self.username = ""
        self.mouse_x = 0.0
        self.mouse_y = 0.0
        self.mouse_down = False
        self.down_keys: set[str] = set()
        self.frame = 0
        self.frame_time = 1.0 / self.fps
        self.quitting = False

        # monitors
        self.monitors = {m["id"]: m for m in manifest.get("monitors", [])}
        self.monitor_visible = {
            m["id"]: bool(m.get("visible", True)) for m in manifest.get("monitors", [])
        }
        self.list_visible = {
            m["id"]: bool(m.get("visible", True))
            for m in manifest.get("monitors", [])
            if m.get("isList")
        }

        # ask UI
        self.asking = False
        self.ask_question = ""
        self.ask_buffer = ""

        # threads
        self.threads: list[Thread] = []
        self.current_thread: Thread | None = None
        self.routes = self._build_routes(scripts)

        # audio
        self.audio_available = False
        self.channels: list = []

        # drawing
        self.screen: pygame.Surface | None = None
        self.clock = None
        self.font = None
        self.big_font = None
        self.hud_font = None
        # debug HUD: live fps / held keys / focus, on for real runs so input
        # problems are visible; off for smoke runs. F2 toggles it.
        self.hud_on = not smoke
        self._hud_prev = 0.0
        self._hud_fps = 0.0
        self.last_latch_dt: float | None = None
        self.manifest = manifest
        self.manifest_path = manifest_path

    # ------------------------------------------------------------------
    # construction helpers
    # ------------------------------------------------------------------
    def _load_target(self, data: dict, is_stage: bool = False) -> TargetDef:
        costume_list = [
            Costume(c, self.assets_dir) for c in data.get("costumes", [])
        ]
        sounds: dict[str, SoundAsset] = {}
        # sounds are registered lazily in run() once the mixer is up
        variables = dict(data.get("variables", {}))
        lists = {k: list(v) for k, v in data.get("lists", {}).items()}
        return TargetDef(
            name=str(data.get("name", "Stage" if is_stage else "Sprite")),
            is_stage=is_stage,
            x=float(data.get("x", 0)),
            y=float(data.get("y", 0)),
            direction=float(data.get("direction", 90)),
            size=float(data.get("size", 100)),
            visible=bool(data.get("visible", True)),
            rotation_style=str(data.get("rotationStyle", "all around")),
            layer_order=int(data.get("layerOrder", 0)),
            volume=float(data.get("volume", 100)),
            current_costume=int(data.get("currentCostume", 0)),
            costumes=costume_list,
            sounds=sounds,
            variables=variables,
            lists=lists,
        )

    def _build_routes(self, scripts: list[ScriptReg]) -> dict:
        routes = {
            "flag": [],
            "key": {},        # key name -> [ScriptReg]
            "click": {},      # sprite name -> [ScriptReg]
            "broadcast": {},  # broadcast name -> [ScriptReg]
            "backdrop": {},   # backdrop name -> [ScriptReg]
            "clone": {},      # sprite name -> [ScriptReg]
            "greater": [],    # (op, threshold, ScriptReg, latch_state)
        }
        for reg in scripts:
            if reg.hat == "event_whenflagclicked":
                routes["flag"].append(reg)
            elif reg.hat == "event_whenkeypressed":
                routes["key"].setdefault(reg.fields.get("KEY_OPTION", "space"), []).append(reg)
            elif reg.hat == "event_whenthisspriteclicked":
                routes["click"].setdefault(reg.sprite, []).append(reg)
            elif reg.hat == "event_whenbroadcastreceived":
                routes["broadcast"].setdefault(reg.fields.get("BROADCAST_OPTION", ""), []).append(reg)
            elif reg.hat == "event_whenbackdroptoggles":
                routes["backdrop"].setdefault(reg.fields.get("BACKDROP", ""), []).append(reg)
            elif reg.hat == "control_start_as_clone":
                routes["clone"].setdefault(reg.sprite, []).append(reg)
            elif reg.hat == "event_whengreaterthan":
                op = str(reg.fields.get("WHENGREATERTHANOPERATOR", "loudness"))
                threshold = s_num(reg.fields.get("WHENGREATERTHANVALUE", 100))
                routes["greater"].append({"op": op, "threshold": threshold,
                                          "reg": reg, "latched": False})
            else:
                self.warn_once(f"script hat {reg.hat!r} ({reg.sprite}) is not routed and will never run")
        return routes

    # ------------------------------------------------------------------
    # warnings
    # ------------------------------------------------------------------
    def warn_once(self, message: str) -> None:
        if message not in self.warned:
            self.warned.add(message)
            print(f"warning: {message}", file=sys.stderr)

    def unsupported(self, opcode: str) -> str:
        self.warn_once(f"block {opcode!r} is not supported by this conversion")
        return ""

    # ------------------------------------------------------------------
    # threading
    # ------------------------------------------------------------------
    def spawn(self, reg: ScriptReg, actor: Actor) -> Thread | None:
        if actor.dead:
            return None
        try:
            produced = reg.fn(actor, self)
        except Exception:
            print(f"error: script {reg.fn.__name__} crashed on start:", file=sys.stderr)
            traceback.print_exc()
            return None
        if isinstance(produced, Iterator):
            thread = Thread(produced, actor, reg)
        else:
            # plain function: ran to completion without waiting
            return None
        self.threads.append(thread)
        return thread

    def spawn_regs(self, regs: list[ScriptReg]) -> list[Thread]:
        """Start a script on every live actor of its sprite (originals + clones).

        Iterates a snapshot: a script that creates clones while running (plain
        functions run to completion at spawn time) must not receive the event
        it is itself causing, and the actor list must not mutate under us.
        """
        started: list[Thread] = []
        for reg in regs:
            for actor in list(self.actors):
                if actor.dead or actor.target.name != reg.sprite:
                    continue
                thread = self.spawn(reg, actor)
                if thread is not None:
                    started.append(thread)
        return started

    def green_flag(self) -> None:
        self.spawn_regs(self.routes["flag"])

    def broadcast(self, name: str) -> None:
        self.spawn_regs(self.routes.get("broadcast", {}).get(name, []))

    def broadcast_wait(self, name: str) -> Iterator[None]:
        started = self.spawn_regs(self.routes.get("broadcast", {}).get(name, []))
        if not started:
            return
        while any(not t.done for t in started):
            yield

    def stop_all(self) -> None:
        for thread in self.threads:
            thread.done = True
        self.stop_all_sounds()

    def stop_others(self, actor: Actor) -> None:
        for thread in self.threads:
            if thread is self.current_thread:
                continue
            if thread.actor is actor and not thread.done:
                thread.done = True

    def stop_script(self, actor: Actor) -> None:
        for thread in self.threads:
            if thread.actor is actor:
                thread.done = True

    def step(self) -> None:
        self.frame += 1
        self.timer += self.frame_time
        self._check_greater_than()
        steps = 0
        index = 0
        while index < len(self.threads):
            thread = self.threads[index]
            index += 1
            if thread.done or thread.stepped_frame == self.frame:
                continue
            thread.stepped_frame = self.frame
            steps += 1
            if steps > MAX_STEPS_PER_FRAME:
                self.warn_once("frame step limit reached (possible broadcast loop)")
                break
            self.current_thread = thread
            try:
                next(thread.generator)
            except StopIteration:
                thread.done = True
            except Exception:
                name = getattr(thread.reg.fn, "__name__", "?")
                print(f"error: script {name} crashed:", file=sys.stderr)
                traceback.print_exc()
                thread.done = True
            finally:
                self.current_thread = None
        if any(t.done for t in self.threads):
            self.threads = [t for t in self.threads if not t.done]

    def _check_greater_than(self) -> None:
        for route in self.routes["greater"]:
            value = self.timer if route["op"] == "timer" else self.loudness
            if value > route["threshold"]:
                if not route["latched"]:
                    route["latched"] = True
                    self.spawn(route["reg"], self._actor_for(route["reg"].sprite))
            else:
                route["latched"] = False

    def _actor_for(self, sprite_name: str) -> Actor:
        for actor in self.actors:
            if not actor.dead and actor.target.name == sprite_name:
                return actor
        return self.stage_actor

    # ------------------------------------------------------------------
    # waits
    # ------------------------------------------------------------------
    def wait_secs(self, seconds) -> Iterator[None]:
        frames = max(1, int(round(s_num(seconds) * self.fps)))
        for _ in range(frames):
            yield

    def glide_to(self, actor: Actor, seconds, x, y) -> Iterator[None]:
        frames = max(1, int(round(s_num(seconds) * self.fps)))
        x0, y0 = actor.x, actor.y
        tx, ty = s_num(x), s_num(y)
        for i in range(frames):
            t = (i + 1) / frames
            actor.x = x0 + (tx - x0) * t
            actor.y = y0 + (ty - y0) * t
            yield

    def ask(self, question: str) -> Iterator[None]:
        self.ask_question = question
        self.ask_buffer = ""
        self.asking = True
        while self.asking:
            yield
        # self.answer already set by the event loop

    # ------------------------------------------------------------------
    # motion
    # ------------------------------------------------------------------
    def norm_dir(self, direction: float) -> float:
        d = (s_num(direction) + 180.0) % 360.0 - 180.0
        return d

    def move(self, actor: Actor, steps) -> None:
        amount = s_num(steps)
        radians = math.radians(actor.direction)
        actor.x += amount * math.sin(radians)
        actor.y += amount * math.cos(radians)

    def point_towards(self, actor: Actor, ref: str) -> None:
        tx, ty = self.tx(ref), self.ty(ref)
        actor.direction = self.norm_dir(math.degrees(math.atan2(tx - actor.x, ty - actor.y)))

    def tx(self, ref: str) -> float:
        if ref == "_mouse_":
            return self.mouse_x
        target = self._find_sprite(ref)
        return target.x if target else 0.0

    def ty(self, ref: str) -> float:
        if ref == "_mouse_":
            return self.mouse_y
        target = self._find_sprite(ref)
        return target.y if target else 0.0

    def _find_sprite(self, name: str) -> Actor | None:
        for actor in self.layers:
            if actor.target.name == name and not actor.dead:
                return actor
        return None

    def goto(self, actor: Actor, ref: str) -> None:
        if ref == "_mouse_":
            actor.x, actor.y = self.mouse_x, self.mouse_y
        elif ref == "_random_":
            actor.x = random.uniform(-STAGE_W / 2, STAGE_W / 2)
            actor.y = random.uniform(-STAGE_H / 2, STAGE_H / 2)
        else:
            target = self._find_sprite(ref)
            if target is None:
                self.warn_once(f"goto target {ref!r} not found")
                return
            actor.x, actor.y = target.x, target.y

    def bounce(self, actor: Actor) -> None:
        hw, hh = actor.half_size()
        if hw * 2 >= STAGE_W or hh * 2 >= STAGE_H:
            return
        left, right = -STAGE_W / 2 + hw, STAGE_W / 2 - hw
        bottom, top = -STAGE_H / 2 + hh, STAGE_H / 2 - hh
        hit_x = actor.x < left or actor.x > right
        hit_y = actor.y < bottom or actor.y > top
        if not (hit_x or hit_y):
            return
        actor.x = max(left, min(right, actor.x))
        actor.y = max(bottom, min(top, actor.y))
        direction = actor.direction
        if hit_x:
            direction = -direction
        if hit_y:
            direction = 180.0 - direction
        actor.direction = self.norm_dir(direction)

    # ------------------------------------------------------------------
    # looks
    # ------------------------------------------------------------------
    @staticmethod
    def clamp_size(value: float) -> float:
        return max(15.0, min(150.0, s_num(value)))

    @staticmethod
    def clamp_volume(value: float) -> float:
        return max(0.0, min(100.0, s_num(value)))

    def set_effect(self, actor: Actor, effect: str, value: float) -> None:
        new = s_num(value)
        old = actor.effects.get(effect)
        actor.effects[effect] = new
        if old != new:
            actor._draw_cache.clear()
        if effect != "ghost":
            self.warn_once(f"visual effect {effect!r} is stored but not rendered by the pygame runtime")

    def change_effect(self, actor: Actor, effect: str, delta: float) -> None:
        self.set_effect(actor, effect, actor.effects.get(effect, 0.0) + s_num(delta))

    def clear_effects(self, actor: Actor) -> None:
        changed = False
        for key in actor.effects:
            if actor.effects[key] != 0.0:
                actor.effects[key] = 0.0
                changed = True
        if changed:
            actor._draw_cache.clear()

    def go_to_front(self, actor: Actor) -> None:
        if actor in self.layers:
            self.layers.remove(actor)
            self.layers.append(actor)

    def go_to_back(self, actor: Actor) -> None:
        if actor in self.layers:
            self.layers.remove(actor)
            self.layers.insert(0, actor)

    def go_layer(self, actor: Actor, delta: int) -> None:
        if actor not in self.layers:
            return
        index = self.layers.index(actor)
        new_index = max(0, min(len(self.layers) - 1, index + int(delta)))
        if new_index != index:
            self.layers.remove(actor)
            self.layers.insert(new_index, actor)

    # ------------------------------------------------------------------
    # stage
    # ------------------------------------------------------------------
    def set_backdrop(self, ref: str) -> None:
        costumes = self.stage_def.costumes
        if not costumes:
            return
        previous = self.stage_def.current_costume
        for i, costume in enumerate(costumes):
            if ref in (costume.name, costume.costume_id):
                self.stage_def.current_costume = i
                break
        else:
            if _looks_numeric(ref):
                index = int(s_num(ref)) - 1
                self.stage_def.current_costume = max(0, min(index, len(costumes) - 1))
            else:
                self.warn_once(f"unknown backdrop {ref!r}")
                return
        if self.stage_def.current_costume != previous:
            self._fire_backdrop_hats()

    def next_backdrop(self) -> None:
        costumes = self.stage_def.costumes
        if not costumes:
            return
        self.stage_def.current_costume = (self.stage_def.current_costume + 1) % len(costumes)
        self._fire_backdrop_hats()

    def _fire_backdrop_hats(self) -> None:
        costumes = self.stage_def.costumes
        name = costumes[self.stage_def.current_costume].name
        regs = self.routes.get("backdrop", {}).get(name, [])
        if regs:
            self.spawn_regs(regs)

    # ------------------------------------------------------------------
    # sound
    # ------------------------------------------------------------------
    def play_sound(self, actor: Actor, name: str):
        if not self.audio_available:
            return None
        sound = actor.target.sounds.get(name)
        if sound is None or sound.sound is None:
            self.warn_once(f"sound {name!r} not found for {actor.target.name!r}")
            return None
        volume = max(0.0, min(1.0, actor.volume / 100.0))
        pan = actor.sound_effects.get("PAN", 0.0) / 100.0
        left = max(0.0, min(1.0, volume * (1.0 - pan))) if pan > 0 else volume
        right = max(0.0, min(1.0, volume * (1.0 + pan))) if pan < 0 else volume
        channel = sound.sound.play()
        if channel is not None:
            channel.set_volume(left, right)
            self.channels.append(channel)
        return channel

    def play_until_done(self, actor: Actor, name: str) -> Iterator[None]:
        channel = self.play_sound(actor, name)
        if channel is None:
            return
        while channel.get_busy():
            yield

    def stop_all_sounds(self) -> None:
        if self.audio_available:
            pygame.mixer.stop()

    def change_sound_effect(self, actor: Actor, effect: str, delta: float) -> None:
        effect = effect.upper()
        actor.sound_effects[effect] = actor.sound_effects.get(effect, 0.0) + s_num(delta)
        if effect not in ("PAN", "STEREO", "LEFT", "RIGHT"):
            self.warn_once(f"sound effect {effect!r} has no audible effect in this runtime")

    def set_sound_effect(self, actor: Actor, effect: str, value: float) -> None:
        actor.sound_effects[effect.upper()] = s_num(value)

    def clear_sound_effects(self, actor: Actor) -> None:
        for key in actor.sound_effects:
            actor.sound_effects[key] = 0.0

    # ------------------------------------------------------------------
    # sensing
    # ------------------------------------------------------------------
    def key_down(self, key: str) -> bool:
        key = s_str(key)
        if key == "any":
            return bool(self.down_keys)
        return key in self.down_keys

    def touching(self, actor: Actor, ref: str) -> bool:
        rect = actor.rect()
        if ref == "_edge_":
            return (
                rect.left <= -STAGE_W / 2
                or rect.right >= STAGE_W / 2
                or rect.top >= STAGE_H / 2
                or rect.bottom <= -STAGE_H / 2
            )
        if ref == "_mouse_":
            return actor.opaque_at(self.mouse_x, self.mouse_y)
        other = self._visible_actor(ref, exclude=actor)
        if other is None:
            return False
        return actor.overlaps(other)

    def _visible_actor(self, name: str, exclude: Actor | None = None) -> Actor | None:
        for actor in reversed(self.layers):
            if actor is exclude or actor.dead or not actor.visible:
                continue
            if actor.target.name == name:
                return actor
        return None

    def distance_to(self, actor: Actor, ref: str) -> float:
        return math.hypot(self.tx(ref) - actor.x, self.ty(ref) - actor.y)

    def touching_colour(self, actor: Actor, colour: str) -> bool:
        target = _parse_colour(colour)
        if target is None:
            return False
        return self._probe(actor, lambda rgb: rgb == target, target)

    def colour_touching_colour(self, actor: Actor, first: str, second: str) -> bool:
        c1 = _parse_colour(first)
        c2 = _parse_colour(second)
        if c1 is None or c2 is None:
            return False
        return self._probe(actor, lambda rgb: rgb == c1, c2)

    def _probe(self, actor: Actor, match_actor_pixel, target_rgb) -> bool:
        """Cheap pixel probe: does this sprite touch a matching colour?"""
        prepared = self._prepare_draw(actor)
        if prepared is None:
            return False
        surface, ax, ay = prepared
        origin_x, origin_y = self._stage_origin(actor, ax, ay)
        step = 4
        width, height = surface.get_size()
        backdrop = self._backdrop_surface()
        for py in range(0, height, step):
            for px in range(0, width, step):
                r, g, b, a = surface.get_at((px, py))
                if a < 128:
                    continue
                if not match_actor_pixel((r, g, b)):
                    continue
                sx = origin_x + px
                sy = origin_y + py
                if self._colour_at(int(sx), int(sy), backdrop) == target_rgb:
                    return True
        return False

    def _colour_at(self, x: float, y: float, backdrop: pygame.Surface | None) -> tuple | None:
        sx = int(x + STAGE_W / 2)
        sy = int(STAGE_H / 2 - y)
        if backdrop is not None and 0 <= sx < backdrop.get_width() and 0 <= sy < backdrop.get_height():
            colour = backdrop.get_at((sx, sy))
            if colour.a >= 128:
                return (colour.r, colour.g, colour.b)
        for other in reversed(self.layers):
            if other.dead or not other.visible:
                continue
            prepared = self._prepare_draw(other)
            if prepared is None:
                continue
            surface, ax, ay = prepared
            ox, oy = self._stage_origin(other, ax, ay)
            px, py = int(sx - ox), int(sy - oy)
            if 0 <= px < surface.get_width() and 0 <= py < surface.get_height():
                colour = surface.get_at((px, py))
                if colour.a >= 128:
                    return (colour.r, colour.g, colour.b)
        return None

    def of(self, attribute: str, obj: str) -> str:
        if obj == "_mouse_":
            if attribute == "x position":
                return self.mouse_x
            if attribute == "y position":
                return self.mouse_y
            return 0
        actor = self._visible_actor(obj)
        if attribute == "backdrop":
            costumes = self.stage_def.costumes
            if costumes:
                return costumes[self.stage_def.current_costume].name
            return ""
        if actor is None:
            return ""
        if attribute == "x position":
            return actor.x
        if attribute == "y position":
            return actor.y
        if attribute == "direction":
            return actor.direction
        if attribute == "size":
            return actor.size
        if attribute == "volume":
            return actor.volume
        if attribute == "costume #":
            return float(actor.current_costume + 1)
        if attribute == "costume name":
            costume = actor.costume
            return costume.name if costume else ""
        if attribute == "loudness":
            return self.loudness
        return ""

    def reset_timer(self) -> None:
        self.timer = 0.0

    # ------------------------------------------------------------------
    # variables and lists
    # ------------------------------------------------------------------
    def set_monitor_visible(self, monitor_id: str, visible: bool) -> None:
        if monitor_id in self.monitor_visible:
            self.monitor_visible[monitor_id] = visible
        else:
            self.warn_once(f"no monitor for id {monitor_id!r}")

    def set_list_visible(self, monitor_id: str, visible: bool) -> None:
        if monitor_id in self.list_visible:
            self.list_visible[monitor_id] = visible
        else:
            # fall back to matching by list name
            for known in self.monitors.values():
                if known.get("isList") and known.get("label"):
                    self.list_visible.setdefault(known["id"], True)

    # ------------------------------------------------------------------
    # clones
    # ------------------------------------------------------------------
    def create_clone(self, actor: Actor, target_name: str) -> None:
        if target_name == "_myself_":
            source_actor, definition = actor, actor.target
        else:
            definition = self.sprite_defs.get(target_name)
            source_actor = None
            if definition is None:
                self.warn_once(f"cannot clone unknown sprite {target_name!r}")
                return
            for existing in self.actors:
                if not existing.dead and existing.target.name == target_name and not existing.is_clone:
                    source_actor = existing
                    break
        clone_count = sum(1 for a in self.actors if a.is_clone and not a.dead)
        if clone_count >= MAX_CLONES:
            self.warn_once("clone limit (300) reached")
            return
        clone = Actor(self, definition, is_clone=True)
        if source_actor is not None:
            clone.x, clone.y = source_actor.x, source_actor.y
            clone.direction = source_actor.direction
            clone.size = source_actor.size
            clone.current_costume = source_actor.current_costume
            # Scratch clones inherit the creator's current local variable values
            clone.vars = dict(source_actor.vars)
            clone.lists = {k: list(v) for k, v in source_actor.lists.items()}
        self.actors.append(clone)
        if source_actor is not None and source_actor in self.layers:
            index = self.layers.index(source_actor)
            self.layers.insert(index + 1, clone)
        else:
            self.layers.append(clone)
        for reg in self.routes.get("clone", {}).get(definition.name, []):
            self.spawn(reg, clone)

    def remove_clone(self, actor: Actor) -> None:
        actor.dead = True
        if actor in self.layers:
            self.layers.remove(actor)
        for thread in self.threads:
            if thread.actor is actor:
                thread.done = True

    # ------------------------------------------------------------------
    # colour helpers
    # ------------------------------------------------------------------
    def _backdrop_surface(self) -> pygame.Surface | None:
        costumes = self.stage_def.costumes
        if not costumes:
            return None
        cached = getattr(self, "_backdrop_cache", None)
        index = self.stage_def.current_costume
        if cached is not None and cached[0] == index:
            return cached[1]
        base = costumes[index].surface
        scaled = pygame.transform.smoothscale(base, (STAGE_W, STAGE_H))
        self._backdrop_cache = (index, scaled)
        return scaled

    def _prepare_draw(self, actor: Actor):
        """Return (surface, ax, ay): rotated/scaled surface plus the costume
        anchor's offset into it.

        Only costume geometry (index/size/direction/rotation) is cached —
        NEVER the actor's position: baking actor.x/y into the cached value
        (as an earlier version did) made every cache hit blit at a stale
        position, so sprites froze mid-motion and teleported whenever the
        costume changed: the game logic ran at 30fps while the rendering
        stood still, which reads as stutter.
        """
        costume = actor.costume
        if costume is None:
            return None
        scale = actor.size / 100.0
        key = (
            int(actor.current_costume),
            round(actor.size, 3),
            round(actor.direction, 3),
            actor.rotation_style,
        )
        cached = actor._draw_cache.get("prepared")
        if cached is not None and cached[0] == key:
            return cached[1], cached[2], cached[3]

        base = costume.surface
        if scale != 1.0:
            width = max(1, int(base.get_width() * scale))
            height = max(1, int(base.get_height() * scale))
            base = pygame.transform.smoothscale(base, (width, height))
        ax = costume.cx * scale
        ay = costume.cy * scale

        style = actor.rotation_style
        if style == "left-right" and actor.direction < 0:
            base = pygame.transform.flip(base, True, False)
            ax = base.get_width() - ax
            rotated = base
        elif style == "all around":
            angle = -(actor.direction - 90.0)
            padded_w = base.get_width() + 2
            padded_h = base.get_height() + 2
            canvas = pygame.Surface((padded_w * 2, padded_h * 2), pygame.SRCALPHA)
            canvas.blit(base, (padded_w - ax, padded_h - ay))
            rotated = pygame.transform.rotate(canvas, angle)
            ax, ay = rotated.get_width() / 2, rotated.get_height() / 2
        else:
            rotated = base

        actor._draw_cache["prepared"] = (key, rotated, ax, ay)
        return rotated, ax, ay

    def _stage_origin(self, actor: Actor, ax: float, ay: float) -> tuple[float, float]:
        """Top-left of the prepared surface in stage pixel space (live x/y)."""
        return actor.x - ax, STAGE_H - (actor.y + ay)

    def _prepare_screen(self, actor: Actor):
        """Stage-space prepared surface scaled/ghosted for the screen (cached).

        draw() must not re-run transform.scale per frame: at 30fps a full
        backdrop + ~12 sprite rescales blew the frame budget and dropped the
        game to single-digit fps (most visible while jumping).
        """
        prepared = self._prepare_draw(actor)
        if prepared is None:
            return None
        stage_surface, ax, ay = prepared
        ghost = actor.effects.get("ghost", 0.0)
        alpha = max(0, min(255, int(255 * (1.0 - ghost / 100.0))))
        key = (actor._draw_cache["prepared"][0], self.scale, alpha)
        cached = actor._draw_cache.get("screen")
        if cached is not None and cached[0] == key:
            return cached[1], cached[2], cached[3]
        surface = stage_surface
        if self.scale != 1:
            target_size = (
                max(1, int(surface.get_width() * self.scale)),
                max(1, int(surface.get_height() * self.scale)),
            )
            surface = pygame.transform.scale(surface, target_size)
        if alpha != 255:
            surface = surface.copy()
            surface.set_alpha(alpha)
        actor._draw_cache["screen"] = (key, surface, ax, ay)
        return surface, ax, ay

    # ------------------------------------------------------------------
    # rendering
    # ------------------------------------------------------------------
    def _scale_point(self, x: float, y: float) -> tuple[int, int]:
        return int((x + STAGE_W / 2) * self.scale), int((STAGE_H / 2 - y) * self.scale)

    def draw(self) -> None:
        if self.screen is None:
            return
        surface = self.screen
        surface.fill((15, 15, 30))
        backdrop = self._backdrop_surface()
        if backdrop is not None:
            size = surface.get_size()
            cached_bd = getattr(self, "_backdrop_scaled_cache", None)
            if (
                cached_bd is None
                or cached_bd[0] != size
                or cached_bd[1] != self.stage_def.current_costume
            ):
                scaled_backdrop = pygame.transform.scale(backdrop, size)
                self._backdrop_scaled_cache = (
                    size,
                    self.stage_def.current_costume,
                    scaled_backdrop,
                )
            else:
                scaled_backdrop = cached_bd[2]
            surface.blit(scaled_backdrop, (0, 0))

        for actor in self.layers:
            if actor.dead or not actor.visible:
                continue
            prepared = self._prepare_screen(actor)
            if prepared is None:
                continue
            sprite_surface, ax, ay = prepared
            dest = self._scale_point(actor.x - ax, actor.y + ay)
            surface.blit(sprite_surface, dest)

        for actor in [*self.layers, self.stage_actor]:
            if actor.dead or actor.say is None and actor.think is None:
                continue
            self._draw_bubble(actor)

        self._draw_monitors()
        if self.asking:
            self._draw_ask()
        self._draw_hud()

    def _draw_hud(self) -> None:
        if not self.hud_on or self.screen is None or self.hud_font is None:
            return
        now = time.perf_counter()
        if self._hud_prev:
            dt = now - self._hud_prev
            if dt > 0:
                inst = 1.0 / dt
                self._hud_fps = inst if not self._hud_fps else self._hud_fps * 0.9 + inst * 0.1
        self._hud_prev = now
        keys = ",".join(sorted(self.down_keys)) or "-"
        try:
            focus = int(bool(pygame.key.get_focused()))
        except pygame.error:
            focus = -1
        lat = "" if self.last_latch_dt is None else f"  lat {self.last_latch_dt * 1e3:.1f}"
        text = f"fps {self._hud_fps:4.1f}{lat}  keys {keys}  focus {focus}  frame {self.frame}  [F2]"
        label = self.hud_font.render(text, True, (255, 235, 59))
        box = pygame.Rect(4, 4, label.get_width() + 8, label.get_height() + 4)
        lines = [label]
        # players sit on top (highest layer_order); show the top layers so
        # they are always included
        spots = [a for a in self.layers if not a.dead and a.visible][-8:]
        for i in range(0, len(spots), 4):
            chunk = spots[i : i + 4]
            pos = "  ".join(f"{a.target.name[:7]}@{a.x:.0f},{a.y:.0f}" for a in chunk)
            lines.append(self.hud_font.render(pos, True, (130, 226, 120)))
        vels = [f"{k}={v:.1f}" for k, v in self.vars.items() if "vel" in str(k).lower()]
        if vels:
            lines.append(self.hud_font.render("  ".join(vels), True, (120, 200, 255)))
        for line in lines:
            box.width = max(box.width, line.get_width() + 8)
        box.height = sum(line.get_height() for line in lines) + 4 * (len(lines) + 1)
        pygame.draw.rect(self.screen, (0, 0, 0), box)
        pygame.draw.rect(self.screen, (90, 90, 90), box, width=1)
        y = box.y + 2
        for line in lines:
            self.screen.blit(line, (box.x + 4, y))
            y += line.get_height()

    def _draw_bubble(self, actor: Actor) -> None:
        text = s_str(actor.say if actor.say is not None else actor.think)
        if not text:
            return
        lines = _wrap_text(text, 24)
        line_h = 16
        width = max(self.font.size(line)[0] for line in lines) + 14
        height = line_h * len(lines) + 8
        bx, by = self._scale_point(actor.x, actor.y + actor.half_size()[1])
        bx = max(4, min(self.screen.get_width() - width - 4, bx - width // 2))
        by = max(4, by - height - 12)
        rect = pygame.Rect(int(bx), int(by), int(width * self.scale / max(self.scale, 1)), int(height))
        rect = pygame.Rect(rect.x, rect.y, int(width), int(height))
        pygame.draw.rect(self.screen, (255, 255, 255), rect, border_radius=6)
        pygame.draw.rect(self.screen, (180, 180, 180), rect, width=1, border_radius=6)
        for i, line in enumerate(lines):
            label = self.font.render(line, True, (20, 20, 20))
            self.screen.blit(label, (rect.x + 7, rect.y + 4 + i * line_h))
        pygame.draw.polygon(
            self.screen,
            (255, 255, 255),
            [(rect.centerx - 6, rect.bottom), (rect.centerx + 6, rect.bottom),
             (rect.centerx, rect.bottom + 8)],
        )

    def _draw_monitors(self) -> None:
        for monitor in self.monitors.values():
            monitor_id = monitor["id"]
            if monitor.get("isList"):
                if not self.list_visible.get(monitor_id, True):
                    continue
            elif not self.monitor_visible.get(monitor_id, True):
                continue
            value = self._monitor_value(monitor)
            mx, my = self._scale_point(float(monitor.get("x", 0)), float(monitor.get("y", 0)))
            mode = monitor.get("mode", "default")
            if mode == "large":
                label = self.big_font.render(s_str(value), True, (110, 230, 255))
                outline = self.big_font.render(s_str(value), True, (255, 255, 255))
                for dx, dy in ((-2, 0), (2, 0), (0, -2), (0, 2)):
                    self.screen.blit(outline, (mx + dx, my + dy))
                self.screen.blit(label, (mx, my))
                continue
            text = s_str(value)
            label_surface = self.font.render(monitor.get("label", ""), True, (60, 60, 60))
            value_surface = self.font.render(text, True, (20, 20, 20))
            box = pygame.Rect(int(mx), int(my), label_surface.get_width() + value_surface.get_width() + 22,
                              max(20, value_surface.get_height() + 6))
            pygame.draw.rect(self.screen, (245, 245, 245), box, border_radius=4)
            pygame.draw.rect(self.screen, (176, 176, 176), box, width=1, border_radius=4)
            self.screen.blit(label_surface, (box.x + 6, box.y + 3))
            self.screen.blit(value_surface, (box.right - value_surface.get_width() - 6, box.y + 3))

    def _monitor_value(self, monitor: dict):
        label = monitor.get("label", "")
        target_name = monitor.get("target")
        for definition in self.target_defs:
            if target_name is not None and definition.name != target_name:
                continue
            if monitor.get("isList") and label in definition.lists:
                return definition.lists[label]
            if not monitor.get("isList") and label in definition.variables:
                return definition.variables[label]
        if monitor.get("isList"):
            return []
        return self.vars.get(label, monitor.get("value", 0))

    def _draw_ask(self) -> None:
        height = 60
        rect = pygame.Rect(0, self.screen.get_height() - height, self.screen.get_width(), height)
        pygame.draw.rect(self.screen, (245, 245, 245), rect)
        pygame.draw.rect(self.screen, (160, 160, 160), rect, width=1)
        question = self.font.render(s_str(self.ask_question)[:90], True, (20, 20, 20))
        self.screen.blit(question, (10, rect.y + 8))
        answer = self.font.render(self.ask_buffer + "_", True, (20, 20, 20))
        self.screen.blit(answer, (10, rect.y + 32))

    # ------------------------------------------------------------------
    # events
    # ------------------------------------------------------------------
    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.QUIT:
            self.quitting = True
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_F2:
                self.hud_on = not self.hud_on
                return
            if event.key == pygame.K_ESCAPE:
                self.quitting = True
                return
            if self.asking:
                if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    self.answer = self.ask_buffer
                    self.asking = False
                elif event.key == pygame.K_BACKSPACE:
                    self.ask_buffer = self.ask_buffer[:-1]
                elif event.unicode and event.unicode.isprintable():
                    self.ask_buffer += event.unicode
                return
            name = pygame_key_to_scratch(event.key)
            if name is not None:
                self.down_keys.add(name)
            if name is not None:
                for key in (name, "any"):
                    for reg in self.routes["key"].get(key, []):
                        self.spawn(reg, self._actor_for(reg.sprite))
        elif event.type == pygame.KEYUP:
            name = pygame_key_to_scratch(event.key)
            if name is not None:
                self.down_keys.discard(name)
        elif event.type == pygame.MOUSEMOTION:
            self._update_mouse(event.pos)
        elif event.type == pygame.MOUSEBUTTONDOWN:
            self._update_mouse(event.pos)
            self.mouse_down = True
            self._fire_click()
        elif event.type == pygame.MOUSEBUTTONUP:
            self.mouse_down = False

    def _update_mouse(self, pos: tuple[int, int]) -> None:
        self.mouse_x = pos[0] / self.scale - STAGE_W / 2
        self.mouse_y = STAGE_H / 2 - pos[1] / self.scale

    def _fire_click(self) -> None:
        for actor in reversed(self.layers):
            if actor.dead or not actor.visible:
                continue
            if actor.rect().collidepoint(int(self.mouse_x), int(self.mouse_y)):
                for reg in self.routes["click"].get(actor.target.name, []):
                    self.spawn(reg, actor)
                return

    # ------------------------------------------------------------------
    # main loop
    # ------------------------------------------------------------------
    def run(self) -> int:
        os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
        # Windows' default 15.6ms Sleep quantum can overshoot our frame
        # pacing budget by more than half a frame; request 1ms so the
        # sleep+spin pacing at the bottom of the loop stays exact.
        winmm = None
        dwmapi = None
        if sys.platform == "win32":
            with contextlib.suppress(Exception):
                import ctypes

                winmm = ctypes.WinDLL("winmm")
                winmm.timeBeginPeriod(1)
            with contextlib.suppress(Exception):
                import ctypes

                dwmapi = ctypes.WinDLL("dwmapi")
                dwmapi.DwmFlush.argtypes = []
                dwmapi.DwmFlush.restype = ctypes.c_long
        pygame.init()
        try:
            pygame.mixer.init()
            self.audio_available = True
        except pygame.error:
            self.audio_available = False
            if not self.smoke:
                self.warn_once("audio device unavailable; sound is disabled")

        # load sounds now that the mixer exists
        for data in [self.manifest.get("stage", {}), *self.manifest.get("sprites", [])]:
            definition = next((d for d in self.target_defs if d.name == data.get("name")), None)
            if definition is None:
                continue
            for sound_data in data.get("sounds", []):
                asset = SoundAsset(sound_data, self.assets_dir, self.audio_available)
                definition.sounds[asset.name] = asset

        size = (STAGE_W * self.scale, STAGE_H * self.scale)
        try:
            self.screen = pygame.display.set_mode(size)
        except pygame.error:
            self.screen = pygame.display.set_mode(size, pygame.HIDDEN)
        pygame.display.set_caption(str(self.manifest.get("name", "Scratch project")))
        # costumes were loaded before a video mode existed; convert them now
        for definition in self.target_defs:
            for costume in definition.costumes:
                if not costume.missing:
                    with contextlib.suppress(pygame.error):
                        costume.surface = costume.surface.convert_alpha()
        self.clock = pygame.time.Clock()
        self.font = pygame.font.Font(None, 18 * self.scale)
        self.big_font = pygame.font.Font(None, 64 * self.scale)
        self.hud_font = pygame.font.Font(None, 13 * self.scale)

        self.green_flag()

        smoke_t0 = time.perf_counter()
        next_deadline = smoke_t0
        prev_latch: float | None = None
        # Estimated panel vblank time of the most recent DwmFlush return.
        # DwmFlush lands on the panel's vblank grid, but two failure modes
        # corrupt a naive re-anchor at each return:
        #   * a frame can present a slot EARLY (the submission races the
        #     previous vblank's composition cutoff) — following that pulls
        #     the grid backwards and oscillates between short and long
        #     frames;
        #   * a frame can present one or more slots LATE (compositor stall
        #     or a missed acceptance under load) — rejecting that leaves the
        #     deadline stranded in the past and a burst of catch-up flips.
        # So: reject early returns (keep the grid), follow late returns (the
        # latch IS a real vblank; re-anchor so one stretched frame is all a
        # stall costs). Falls back to a nominal grid when DwmFlush is
        # unavailable or fails.
        vblank_est: float | None = None
        # present this far BEFORE the deadline (tunable for measurement:
        # SB3_FLIP_LEAD overrides in seconds). Measured against this panel:
        # 6ms clears DwmFlush's composition cutoff under load without
        # arriving early enough to race the previous vblank (that race
        # presents the frame a slot early; the early-reject above handles
        # the residue, but a larger lead makes it frequent).
        flip_lead = float(os.environ.get("SB3_FLIP_LEAD", "0.006"))
        running = True
        while running:
            for event in pygame.event.get():
                self.handle_event(event)
            if self.quitting:
                break
            self.step()
            self.draw()
            # Pacing: wait for the deadline, present ~flip_lead BEFORE it,
            # then update the vblank estimate from the DwmFlush return (see
            # vblank_est above).
            frame_dt = 1.0 / self.fps
            target = next_deadline - flip_lead
            now = time.perf_counter()
            remaining = target - now
            if remaining > 0:
                if remaining > 0.002:
                    time.sleep(remaining - 0.001)
                while (now := time.perf_counter()) < target:
                    pass
            pygame.display.flip()
            if dwmapi is not None and dwmapi.DwmFlush() == 0:
                latch = time.perf_counter()
                if prev_latch is not None:
                    self.last_latch_dt = latch - prev_latch
                prev_latch = latch
                if vblank_est is None:
                    vblank_est = latch
                elif latch < vblank_est + frame_dt - 0.004:
                    vblank_est += frame_dt  # early present: hold the grid
                else:
                    vblank_est = latch  # on time or late: re-anchor
                next_deadline = vblank_est + frame_dt
            else:
                if vblank_est is not None:
                    vblank_est += frame_dt
                    next_deadline = vblank_est + frame_dt
                else:
                    next_deadline += frame_dt
                now = time.perf_counter()
                if now - next_deadline > frame_dt:
                    next_deadline = now  # large overrun; don't spiral
            if self.smoke and self.frame >= self.smoke:
                running = False

        if self.smoke:
            elapsed = max(1e-9, time.perf_counter() - smoke_t0)
            print(
                f"SMOKE OK frames={self.frame} threads={len(self.threads)} "
                f"elapsed={elapsed:.2f}s fps={self.frame / elapsed:.1f}"
            )
        if winmm is not None:
            with contextlib.suppress(Exception):
                winmm.timeEndPeriod(1)
        pygame.quit()
        return 0


def _parse_colour(text: str) -> tuple | None:
    text = s_str(text).strip()
    if not text:
        return None
    if text.startswith("#") and len(text) in (4, 7):
        try:
            if len(text) == 4:
                return tuple(int(c * 2, 16) for c in text[1:])
            return tuple(int(text[i : i + 2], 16) for i in (1, 3, 5))
        except ValueError:
            return None
    return None


def _wrap_text(text: str, width: int) -> list[str]:
    words = text.split()
    if not words:
        return [""]
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        if len(current) + 1 + len(word) <= width:
            current += " " + word
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _app_base() -> Path:
    """Directory holding manifest + assets: the bundle root when frozen, else this file's dir."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent


def run_cli(scripts: list[ScriptReg]) -> int:
    """Entry point used by generated main.py."""
    # windowed/frozen builds may have no console attached
    if sys.stdout is None or sys.stderr is None:
        with contextlib.suppress(OSError):
            # the stream must outlive run_cli, so it is deliberately not closed
            devnull = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115
            if sys.stdout is None:
                sys.stdout = devnull
            if sys.stderr is None:
                sys.stderr = devnull
    parser = argparse.ArgumentParser(description="Run a converted Scratch project")
    parser.add_argument("--manifest", default=str(_app_base() / "sb3_manifest.json"))
    parser.add_argument("--smoke", type=int, default=0, metavar="N",
                        help="run N frames headless and exit (for testing)")
    parser.add_argument("--scale", type=int, default=None, help="window scale factor")
    parser.add_argument("--fps", type=int, default=None, help="frames per second")
    parser.add_argument("--seed", type=int, default=None, help="random seed")
    args = parser.parse_args()

    if args.smoke:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

    manifest_path = Path(args.manifest)
    if not manifest_path.exists():
        print(f"error: manifest {manifest_path} not found", file=sys.stderr)
        return 2
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    runtime = Runtime(
        manifest,
        scripts,
        manifest_path=manifest_path,
        scale=args.scale,
        fps=args.fps,
        seed=args.seed,
        smoke=args.smoke,
    )
    return runtime.run()
