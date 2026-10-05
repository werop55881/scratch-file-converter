"""Opcode registry: what each Scratch block is, and which categories we target."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Kind(StrEnum):
    HAT = "hat"
    STACK = "stack"
    REPORTER = "reporter"
    BOOLEAN = "boolean"
    CAP = "cap"  # terminates a stack (stop block)

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.value


class Category(StrEnum):
    MOTION = "motion"
    LOOKS = "looks"
    SOUND = "sound"
    EVENT = "event"
    CONTROL = "control"
    SENSING = "sensing"
    OPERATOR = "operator"
    DATA = "data"
    PEN = "pen"
    PROCEDURES = "procedures"
    ARGUMENTS = "argument"
    EXTENSION = "extension"
    UNKNOWN = "unknown"

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.value


# Categories this converter targets (core blocks + sound effects).
SUPPORTED_CATEGORIES = frozenset(
    {
        Category.MOTION,
        Category.LOOKS,
        Category.SOUND,
        Category.EVENT,
        Category.CONTROL,
        Category.SENSING,
        Category.OPERATOR,
        Category.DATA,
    }
)


@dataclass(frozen=True)
class OpcodeInfo:
    opcode: str
    category: Category
    kind: Kind
    label: str = ""

    @property
    def supported(self) -> bool:
        return self.category in SUPPORTED_CATEGORIES


def _entry(category: Category, kind: Kind, *opcodes: str) -> dict[str, OpcodeInfo]:
    return {o: OpcodeInfo(o, category, kind) for o in opcodes}


OPCODES: dict[str, OpcodeInfo] = {}
OPCODES.update(_entry(Category.EVENT, Kind.HAT,
    "event_whenflagclicked",
    "event_whenkeypressed",
    "event_whenthisspriteclicked",
    "event_whenbroadcastreceived",
    "event_whenbackdroptoggles",
    "event_whengreaterthan",
))
OPCODES.update(_entry(Category.CONTROL, Kind.HAT, "control_start_as_clone"))
OPCODES.update(_entry(Category.PROCEDURES, Kind.HAT, "procedures_definition"))

OPCODES.update(_entry(Category.EVENT, Kind.STACK, "event_broadcast", "event_broadcastAndWait"))

OPCODES.update(_entry(Category.MOTION, Kind.STACK,
    "motion_movesteps",
    "motion_turnright",
    "motion_turnleft",
    "motion_goto",
    "motion_gotoxy",
    "motion_glidesecstoxy",
    "motion_glideto",
    "motion_pointindirection",
    "motion_pointtowards",
    "motion_changexby",
    "motion_setx",
    "motion_changeyby",
    "motion_sety",
    "motion_ifonedgebounce",
    "motion_setrotationstyle",
))
OPCODES.update(_entry(Category.MOTION, Kind.REPORTER, "motion_xposition", "motion_yposition"))

OPCODES.update(_entry(Category.LOOKS, Kind.STACK,
    "looks_say",
    "looks_sayforsecs",
    "looks_think",
    "looks_thinkforsecs",
    "looks_show",
    "looks_hide",
    "looks_switchcostumeto",
    "looks_nextcostume",
    "looks_switchbackdropto",
    "looks_nextbackdrop",
    "looks_changesizeby",
    "looks_setsizeto",
    "looks_changeghostby",
    "looks_setghostto",
    "looks_changefilterby",
    "looks_setfilterto",
    "looks_changeeffectby",
    "looks_seteffectto",
    "looks_gotofrontback",
    "looks_golayerbackward",
    "looks_golayerforward",
    "looks_cleargraphicseffects",
))
OPCODES.update(_entry(Category.LOOKS, Kind.REPORTER, "looks_size", "looks_costumenumbername"))

OPCODES.update(_entry(Category.SOUND, Kind.STACK,
    "sound_play",
    "sound_playuntildone",
    "sound_stopallsounds",
    "sound_changevolumeby",
    "sound_setvolumeto",
    "sound_changeeffectby",
    "sound_seteffectto",
    "sound_cleareffects",
    "sound_stopall",
))

OPCODES.update(_entry(Category.CONTROL, Kind.STACK,
    "control_wait",
    "control_wait_until",
    "control_repeat",
    "control_forever",
    "control_if",
    "control_if_else",
    "control_repeat_until",
    "control_stop",
    "control_create_clone_of",
    "control_delete_this_clone",
))

OPCODES.update(_entry(Category.PROCEDURES, Kind.STACK, "procedures_call"))
OPCODES.update(_entry(Category.ARGUMENTS, Kind.REPORTER, "argument_reporter_string_number"))
OPCODES.update(_entry(Category.ARGUMENTS, Kind.BOOLEAN, "argument_reporter_boolean"))

OPCODES.update(_entry(Category.SENSING, Kind.STACK, "sensing_askandwait", "sensing_resettimer"))

OPCODES.update(_entry(Category.SENSING, Kind.BOOLEAN,
    "sensing_touchingobject",
    "sensing_touchingcolor",
    "sensing_coloristouchingcolor",
    "sensing_keypressed",
    "sensing_mousedown",
))
OPCODES.update(_entry(Category.SENSING, Kind.REPORTER,
    "sensing_distanceto",
    "sensing_loudness",
    "sensing_timer",
    "sensing_username",
    "sensing_of",
    "sensing_videoon",
))

OPCODES.update(_entry(Category.OPERATOR, Kind.REPORTER,
    "operator_add",
    "operator_subtract",
    "operator_multiply",
    "operator_divide",
    "operator_random",
    "operator_join",
    "operator_letter_of",
    "operator_length",
    "operator_mod",
    "operator_round",
    "operator_mathop",
))
OPCODES.update(_entry(Category.OPERATOR, Kind.BOOLEAN,
    "operator_gt",
    "operator_lt",
    "operator_equals",
    "operator_and",
    "operator_or",
    "operator_not",
    "operator_contains",
))

OPCODES.update(_entry(Category.DATA, Kind.REPORTER, "data_variable", "data_listcontents"))
OPCODES.update(_entry(Category.DATA, Kind.STACK,
    "data_setvariableto",
    "data_changevariableby",
    "data_showvariable",
    "data_hidevariable",
    "data_addtolist",
    "data_deleteoflist",
    "data_deletealloflist",
    "data_insertatlist",
    "data_replaceitemoflist",
    "data_showlist",
    "data_hidelist",
))
OPCODES.update(_entry(Category.DATA, Kind.REPORTER, "data_itemoflist", "data_itemnumoflist", "data_lengthoflist"))
OPCODES.update(_entry(Category.DATA, Kind.BOOLEAN, "data_listcontainsitem"))

# Common substack (C-shaped input) names.
SUBSTACK_INPUTS = ("SUBSTACK", "SUBSTACK2")

HAT_OPCODES = frozenset(o for o, i in OPCODES.items() if i.kind is Kind.HAT)
STACK_OPCODES = frozenset(o for o, i in OPCODES.items() if i.kind is Kind.STACK)
REPORTER_OPCODES = frozenset(o for o, i in OPCODES.items() if i.kind is Kind.REPORTER)
BOOLEAN_OPCODES = frozenset(o for o, i in OPCODES.items() if i.kind is Kind.BOOLEAN)


def info(opcode: str) -> OpcodeInfo | None:
    return OPCODES.get(opcode)


def is_supported(opcode: str) -> bool:
    found = OPCODES.get(opcode)
    return bool(found and found.supported)


def category_of(opcode: str) -> Category:
    found = OPCODES.get(opcode)
    return found.category if found else Category.UNKNOWN
