"""Expression emitter: Scratch reporters become JavaScript expressions.

Mirror of the Python backend's emitter: same dispatch table, same helper
function names (s_add, list_item, ...), JavaScript syntax only. Nothing
depends on operator precedence - every expression is one helper call.
"""

from __future__ import annotations

import json
from collections.abc import Callable

from sb3conv.sb3.model import Block, BlockRef, Literal, Project, Script
from sb3conv.sb3.procedures import Procedure

NUMERIC_TYPE_CODES = {4, 5, 6, 7, 8}  # math number, positive number, integers, angle
STRING_TYPE_CODES = {9, 10, 11, 12, 13, 15}  # colour, text, broadcast, costume, backdrop, sound

Warn = Callable[[str], None]


def js_str(value: str) -> str:
    """A JavaScript string literal."""
    return json.dumps(str(value), ensure_ascii=False)


def format_number(value: float) -> str:
    if value != value:  # NaN
        return "NaN"
    if value == float("inf"):
        return "Infinity"
    if value == float("-inf"):
        return "-Infinity"
    if float(value).is_integer() and abs(value) < 1e15:
        return str(int(value))
    return repr(value)


# opcode -> method name on ExpressionEmitter
EXPR_METHODS: dict[str, str] = {
    # operators
    "operator_add": "op_add",
    "operator_subtract": "op_subtract",
    "operator_multiply": "op_multiply",
    "operator_divide": "op_divide",
    "operator_random": "op_random",
    "operator_gt": "op_gt",
    "operator_lt": "op_lt",
    "operator_equals": "op_equals",
    "operator_and": "op_and",
    "operator_or": "op_or",
    "operator_not": "op_not",
    "operator_join": "op_join",
    "operator_letter_of": "op_letter",
    "operator_length": "op_length",
    "operator_contains": "op_contains",
    "operator_mod": "op_mod",
    "operator_round": "op_round",
    "operator_mathop": "op_mathop",
    # data
    "data_variable": "data_variable",
    "data_listcontents": "data_listcontents",
    "data_itemoflist": "data_itemoflist",
    "data_itemnumoflist": "data_itemnumoflist",
    "data_lengthoflist": "data_lengthoflist",
    "data_listcontainsitem": "data_listcontains",
    # sensing
    "sensing_touchingobject": "sensing_touching",
    "sensing_touchingcolor": "sensing_touching_colour",
    "sensing_coloristouchingcolor": "sensing_colour_touching",
    "sensing_distanceto": "sensing_distance",
    "sensing_keypressed": "sensing_key",
    "sensing_mousedown": "sensing_mouse",
    "sensing_timer": "sensing_timer",
    "sensing_loudness": "sensing_loudness",
    "sensing_username": "sensing_username",
    "sensing_of": "sensing_of",
    "sensing_videoon": "sensing_video",
    # menu shadow blocks
    "looks_costume": "menu_costume",
    "looks_backdrops": "menu_backdrop",
    "sound_sounds_menu": "menu_sound",
    "control_create_clone_of_menu": "menu_clone",
    "sensing_of_object_menu": "menu_object",
    "sensing_touchingobjectmenu": "menu_touching",
    "sensing_distancetomenu": "menu_distance",
    "sensing_keyoptions": "menu_key",
    "motion_goto_menu": "menu_goto",
    "motion_pointtowards_menu": "menu_towards",
    "event_broadcast_menu": "menu_broadcast",
    # state reporters
    "motion_xposition": "x_position",
    "motion_yposition": "y_position",
    "looks_size": "size_report",
    "looks_costumenumbername": "costume_number_name",
    # custom block arguments (only meaningful inside a procedure body)
    "argument_reporter_string_number": "argument_reporter",
    "argument_reporter_boolean": "argument_reporter",
}


class ExpressionEmitter:
    """Emit JavaScript expressions for one script."""

    def __init__(
        self,
        project: Project,
        script: Script,
        warn: Warn,
        procedure: Procedure | None = None,
    ) -> None:
        self.project = project
        self.script = script
        self.target = script.target
        self.warn = warn
        self.procedure = procedure
        self._unsupported: set[str] = set()

    # ------------------------------------------------------------------
    # inputs
    # ------------------------------------------------------------------
    def input_expr(self, block: Block, name: str, default: str = '""') -> str:
        value = block.inputs.get(name)
        if value is None:
            if name in block.fields:
                return js_str(self.field_str(block, name))
            return default
        if isinstance(value, Literal):
            return self.literal_expr(value)
        child = self.target.blocks.get(value.block_id)
        if child is None:
            return default
        return self.block_expr(child)

    def num_input(self, block: Block, name: str, default: str = "0") -> str:
        value = block.inputs.get(name)
        if value is None:
            if name in block.fields:
                text = self.field_str(block, name)
                try:
                    return format_number(float(text))
                except ValueError:
                    return f"s_num({js_str(text)})"
            return default
        if isinstance(value, Literal):
            if value.is_number:
                return format_number(value.as_number())
            return f"s_num({self.literal_expr(value)})"
        return f"s_num({self.input_expr(block, name, default)})"

    def field_str(self, block: Block, name: str, default: str = "") -> str:
        field_value = block.fields.get(name)
        return field_value[0] if field_value is not None else default

    def input_any(self, block: Block, names: tuple[str, ...], default: str) -> str:
        """First of ``names`` present on the block (opcodes renamed inputs)."""
        for name in names:
            if name in block.inputs or name in block.fields:
                return self.input_expr(block, name, default)
        return self.input_expr(block, names[0], default)

    def num_any(self, block: Block, names: tuple[str, ...], default: str) -> str:
        for name in names:
            if name in block.inputs or name in block.fields:
                return self.num_input(block, name, default)
        return self.num_input(block, names[0], default)

    def field_any(self, block: Block, names: tuple[str, ...], default: str) -> str:
        for name in names:
            if name in block.fields:
                return self.field_str(block, name, default)
        return self.field_str(block, names[0], default)

    def literal_expr(self, lit: Literal) -> str:
        code = lit.type_code
        if code == 11:  # broadcast name (or id for hand-written projects)
            return js_str(self.project.broadcast_name(str(lit.value)))
        if code == 12:  # variable getter compressed into an input
            return self.var_ref(lit.id_value, str(lit.value))
        if code == 13:  # list getter compressed into an input
            return self.list_ref(lit.id_value, str(lit.value))
        if code in NUMERIC_TYPE_CODES:
            return format_number(lit.as_number())
        if isinstance(lit.value, (int, float)) and not isinstance(lit.value, bool):
            return format_number(float(lit.value))
        if code in (None, 10) and lit.is_number:
            return format_number(lit.as_number())
        return js_str(str(lit.value))

    # ------------------------------------------------------------------
    # dispatch
    # ------------------------------------------------------------------
    def block_expr(self, block: Block) -> str:
        method = EXPR_METHODS.get(block.opcode)
        if method is None:
            self.mark_unsupported(block.opcode)
            return f"rt.unsupported({js_str(block.opcode)})"
        return getattr(self, method)(block)

    def mark_unsupported(self, opcode: str) -> None:
        if opcode not in self._unsupported:
            self._unsupported.add(opcode)
            where = f"{self.target.name}:{round(self.script.hat.y)}"
            self.warn(f"unsupported reporter {opcode!r} in script at {where}")

    # ------------------------------------------------------------------
    # operators
    # ------------------------------------------------------------------
    def op_add(self, b: Block) -> str:
        return f"s_add({self.input_expr(b, 'NUM1')}, {self.input_expr(b, 'NUM2')})"

    def op_subtract(self, b: Block) -> str:
        return f"s_sub({self.input_expr(b, 'NUM1')}, {self.input_expr(b, 'NUM2')})"

    def op_multiply(self, b: Block) -> str:
        return f"s_mul({self.input_expr(b, 'NUM1')}, {self.input_expr(b, 'NUM2')})"

    def op_divide(self, b: Block) -> str:
        return f"s_div({self.input_expr(b, 'NUM1')}, {self.input_expr(b, 'NUM2')})"

    def op_random(self, b: Block) -> str:
        return f"s_random({self.input_expr(b, 'FROM')}, {self.input_expr(b, 'TO')})"

    def op_gt(self, b: Block) -> str:
        return f"s_gt({self.input_expr(b, 'OPERAND1')}, {self.input_expr(b, 'OPERAND2')})"

    def op_lt(self, b: Block) -> str:
        return f"s_lt({self.input_expr(b, 'OPERAND1')}, {self.input_expr(b, 'OPERAND2')})"

    def op_equals(self, b: Block) -> str:
        return f"s_eq({self.input_expr(b, 'OPERAND1')}, {self.input_expr(b, 'OPERAND2')})"

    def op_and(self, b: Block) -> str:
        left = self.input_any(b, ("OPERAND1", "BOOLEAN1"), "false")
        right = self.input_any(b, ("OPERAND2", "BOOLEAN2"), "false")
        return f"s_and({left}, {right})"

    def op_or(self, b: Block) -> str:
        left = self.input_any(b, ("OPERAND1", "BOOLEAN1"), "false")
        right = self.input_any(b, ("OPERAND2", "BOOLEAN2"), "false")
        return f"s_or({left}, {right})"

    def op_not(self, b: Block) -> str:
        return f"s_not({self.input_any(b, ('OPERAND', 'BOOLEAN'), 'false')})"

    def op_join(self, b: Block) -> str:
        return f"s_join({self.input_expr(b, 'STRING1')}, {self.input_expr(b, 'STRING2')})"

    def op_letter(self, b: Block) -> str:
        return f"s_letter({self.input_expr(b, 'LETTER')}, {self.input_expr(b, 'STRING')})"

    def op_length(self, b: Block) -> str:
        return f"s_length({self.input_expr(b, 'STRING')})"

    def op_contains(self, b: Block) -> str:
        left = self.input_any(b, ("STRING1", "STRING", "FIRST"), '""')
        right = self.input_any(b, ("STRING2", "THINGS", "SECOND"), '""')
        return f"s_contains({left}, {right})"

    def op_mod(self, b: Block) -> str:
        return f"s_mod({self.input_expr(b, 'NUM1')}, {self.input_expr(b, 'NUM2')})"

    def op_round(self, b: Block) -> str:
        return f"s_round({self.input_expr(b, 'NUM')})"

    def op_mathop(self, b: Block) -> str:
        return f"s_mathop({js_str(self.field_str(b, 'OPERATOR', 'abs'))}, {self.input_expr(b, 'NUM')})"

    # ------------------------------------------------------------------
    # data
    # ------------------------------------------------------------------
    def var_ref(self, var_id: str | None, var_name: str) -> str:
        owner = self.project.var_owner(var_id or "")
        if owner is None or owner.is_stage:
            return f"rt.vars[{js_str(var_name)}]"
        if owner.name != self.target.name:
            self.warn(
                f"variable {var_name!r} belongs to {owner.name!r} but is read from "
                f"{self.target.name!r}; using the reader's own copy"
            )
        return f"ctx.vars[{js_str(var_name)}]"

    def list_ref(self, list_id: str | None, list_name: str) -> str:
        owner = self.project.list_owner(list_id or "")
        if owner is None or owner.is_stage:
            return f"rt.lists[{js_str(list_name)}]"
        if owner.name != self.target.name:
            self.warn(
                f"list {list_name!r} belongs to {owner.name!r} but is used from "
                f"{self.target.name!r}; using the reader's own copy"
            )
        return f"ctx.lists[{js_str(list_name)}]"

    def _var_field(self, b: Block) -> str:
        name, var_id = b.fields.get("VARIABLE", (b.field("VARIABLE"), None))
        return self.var_ref(var_id, name)

    def _list_field(self, b: Block) -> str:
        name, list_id = b.fields.get("LIST", (b.field("LIST"), None))
        return self.list_ref(list_id, name)

    def data_variable(self, b: Block) -> str:
        return self._var_field(b)

    def data_listcontents(self, b: Block) -> str:
        return self._list_field(b)

    def _list_arg(self, b: Block) -> str:
        value = b.inputs.get("LIST")
        if isinstance(value, BlockRef):
            child = self.target.blocks.get(value.block_id)
            if child is not None:
                return self.block_expr(child)
        return self._list_field(b)

    def data_itemoflist(self, b: Block) -> str:
        return f"list_item({self._list_arg(b)}, {self.input_expr(b, 'INDEX')})"

    def data_itemnumoflist(self, b: Block) -> str:
        return f"list_index_of({self._list_arg(b)}, {self.input_expr(b, 'ITEM')})"

    def data_lengthoflist(self, b: Block) -> str:
        return f"list_length({self._list_arg(b)})"

    def data_listcontains(self, b: Block) -> str:
        return f"list_contains({self._list_arg(b)}, {self.input_expr(b, 'ITEM')})"

    # ------------------------------------------------------------------
    # sensing
    # ------------------------------------------------------------------
    def sensing_touching(self, b: Block) -> str:
        ref = self.input_expr(b, "TOUCHINGOBJECTMENU", js_str("_mouse_"))
        return f"rt.touching(ctx, s_str({ref}))"

    def sensing_touching_colour(self, b: Block) -> str:
        colour = self.input_expr(b, "COLOR")
        return f"rt.touching_colour(ctx, s_str({colour}))"

    def sensing_colour_touching(self, b: Block) -> str:
        c1 = self.input_expr(b, "COLOR1")
        c2 = self.input_expr(b, "COLOR2")
        return f"rt.colour_touching_colour(ctx, s_str({c1}), s_str({c2}))"

    def sensing_distance(self, b: Block) -> str:
        ref = self.input_any(b, ("DISTANCETO", "DISTANCETOMENU"), js_str("_mouse_"))
        return f"rt.distance_to(ctx, s_str({ref}))"

    def sensing_key(self, b: Block) -> str:
        key = self.input_expr(b, "KEY_OPTION", js_str("space"))
        return f"rt.key_down(s_str({key}))"

    def sensing_mouse(self, b: Block) -> str:
        return "rt.mouse_down"

    def sensing_timer(self, b: Block) -> str:
        return "rt.timer"

    def sensing_loudness(self, b: Block) -> str:
        return "rt.loudness"

    def sensing_username(self, b: Block) -> str:
        return "rt.username"

    def sensing_of(self, b: Block) -> str:
        attribute = self.field_any(b, ("PROPERTY", "ATTRIBUTE"), "x position")
        obj = self.input_any(b, ("OBJECT",), js_str("_mouse_"))
        return f"rt.of({js_str(attribute)}, {obj})"

    def sensing_video(self, b: Block) -> str:
        self.mark_unsupported("sensing_videoon")
        return 'rt.unsupported("sensing_videoon")'

    # ------------------------------------------------------------------
    # menu shadow blocks
    # ------------------------------------------------------------------
    def menu_costume(self, b: Block) -> str:
        name = self.field_str(b, "COSTUME")
        costume = self.target.costume_by_ref(name)
        return js_str(costume.name if costume else name)

    def menu_backdrop(self, b: Block) -> str:
        name = self.field_str(b, "BACKDROP")
        costume = self.project.stage.costume_by_ref(name)
        return js_str(costume.name if costume else name)

    def menu_sound(self, b: Block) -> str:
        name = self.field_str(b, "SOUND_MENU")
        sound = self.target.sound_by_ref(name)
        return js_str(sound.name if sound else name)

    def menu_clone(self, b: Block) -> str:
        return js_str(self.field_str(b, "CLONE_OPTION", "_myself_"))

    def menu_object(self, b: Block) -> str:
        return js_str(self.field_str(b, "OBJECT", "_mouse_"))

    def menu_touching(self, b: Block) -> str:
        return js_str(self.field_str(b, "TOUCHINGOBJECTMENU", "_mouse_"))

    def menu_distance(self, b: Block) -> str:
        return js_str(self.field_any(b, ("DISTANCETO", "DISTANCETOMENU"), "_mouse_"))

    def menu_key(self, b: Block) -> str:
        return js_str(self.field_str(b, "KEY_OPTION", "space"))

    def menu_goto(self, b: Block) -> str:
        return js_str(self.field_str(b, "TO", "_random_"))

    def menu_towards(self, b: Block) -> str:
        return js_str(self.field_str(b, "TOWARDS", "_mouse_"))

    def menu_broadcast(self, b: Block) -> str:
        return js_str(self.project.broadcast_name(self.field_str(b, "BROADCAST_OPTION")))

    # ------------------------------------------------------------------
    # state reporters
    # ------------------------------------------------------------------
    def x_position(self, b: Block) -> str:
        return "ctx.x"

    def y_position(self, b: Block) -> str:
        return "ctx.y"

    def size_report(self, b: Block) -> str:
        return "ctx.size"

    def costume_number_name(self, b: Block) -> str:
        if self.field_str(b, "NUMBER_NAME", "name").lower() == "number":
            return "(ctx.current_costume + 1)"
        return '(ctx.costume ? ctx.costume.name : "")'

    # ------------------------------------------------------------------
    # custom block arguments
    # ------------------------------------------------------------------
    def argument_reporter(self, b: Block) -> str:
        name = self.field_str(b, "VALUE")
        if self.procedure is not None and name in self.procedure.params:
            return self.procedure.params[name]
        self.mark_unsupported(b.opcode)
        return f"rt.unsupported({js_str(b.opcode)})"
