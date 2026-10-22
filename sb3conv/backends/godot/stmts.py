"""Statement emitter: Scratch stack blocks become GDScript statements.

Port of the Lua backend's emitter: scripts are plain coroutine functions;
every blocking action (wait, glide, ask, play-until-done,
broadcast-and-wait) awaits, and the runtime scheduler resumes them once
per frame. Conditions are wrapped with ``Scratch.s_bool`` so GDScript
matches JavaScript truthiness (0 and "" are falsy).
"""

from __future__ import annotations

from collections.abc import Callable

from sb3conv.backends.godot.exprs import ExpressionEmitter, gd_ident, godot_str
from sb3conv.sb3.model import Block, BlockRef, Project, Script
from sb3conv.sb3.procedures import Procedure


def hat_comment(hat: Block) -> str:
    """Human readable comment describing what starts a script."""
    op = hat.opcode
    if op == "event_whenkeypressed":
        return f"# when {hat.field('KEY_OPTION', 'space')} key pressed"
    if op == "event_whenbroadcastreceived":
        return f"# when I receive {hat.field('BROADCAST_OPTION', '?')}"
    if op == "event_whenbackdroptoggles":
        return f"# when backdrop switches to {hat.field('BACKDROP', '?')}"
    if op == "event_whengreaterthan":
        op_name = hat.field("WHENGREATERTHANOPERATOR", "loudness")
        value = hat.field("WHENGREATERTHANVALUE", "?")
        return f"# when {op_name} > {value}"
    if op == "event_whenthisspriteclicked":
        return "# when this sprite clicked"
    if op == "event_whenflagclicked":
        return "# when green flag clicked"
    if op == "control_start_as_clone":
        return "# when I start as a clone"
    if op == "procedures_definition":
        return "# custom block definition"
    return f"# {op}"


# opcode -> method name on StatementEmitter
STMT_METHODS: dict[str, str] = {
    # motion
    "motion_movesteps": "st_move",
    "motion_turnright": "st_turn_right",
    "motion_turnleft": "st_turn_left",
    "motion_goto": "st_goto",
    "motion_gotoxy": "st_goto_xy",
    "motion_glidesecstoxy": "st_glide_xy",
    "motion_glideto": "st_glide_to",
    "motion_pointindirection": "st_point_direction",
    "motion_pointtowards": "st_point_towards",
    "motion_changexby": "st_change_x",
    "motion_setx": "st_set_x",
    "motion_changeyby": "st_change_y",
    "motion_sety": "st_set_y",
    "motion_ifonedgebounce": "st_bounce",
    "motion_setrotationstyle": "st_rotation_style",
    # looks
    "looks_say": "st_say",
    "looks_sayforsecs": "st_say_for",
    "looks_think": "st_think",
    "looks_thinkforsecs": "st_think_for",
    "looks_show": "st_show",
    "looks_hide": "st_hide",
    "looks_switchcostumeto": "st_switch_costume",
    "looks_nextcostume": "st_next_costume",
    "looks_switchbackdropto": "st_switch_backdrop",
    "looks_nextbackdrop": "st_next_backdrop",
    "looks_changesizeby": "st_change_size",
    "looks_setsizeto": "st_set_size",
    "looks_changeghostby": "st_change_ghost",
    "looks_setghostto": "st_set_ghost",
    "looks_changefilterby": "st_change_effect",
    "looks_setfilterto": "st_set_effect",
    "looks_changeeffectby": "st_change_effect",
    "looks_seteffectto": "st_set_effect",
    "looks_gotofrontback": "st_go_front_back",
    "looks_golayerbackward": "st_layer_backward",
    "looks_golayerforward": "st_layer_forward",
    "looks_cleargraphicseffects": "st_clear_effects",
    # sound
    "sound_play": "st_sound_play",
    "sound_playuntildone": "st_sound_play_until_done",
    "sound_stopallsounds": "st_sound_stop_all",
    "sound_stopall": "st_sound_stop_all",
    "sound_changevolumeby": "st_sound_change_volume",
    "sound_setvolumeto": "st_sound_set_volume",
    "sound_changeeffectby": "st_sound_change_effect",
    "sound_seteffectto": "st_sound_set_effect",
    "sound_cleareffects": "st_sound_clear_effects",
    # events
    "event_broadcast": "st_broadcast",
    "event_broadcastAndWait": "st_broadcast_wait",
    # control
    "control_wait": "st_wait",
    "control_wait_until": "st_wait_until",
    "control_repeat": "st_repeat",
    "control_forever": "st_forever",
    "control_if": "st_if",
    "control_if_else": "st_if_else",
    "control_repeat_until": "st_repeat_until",
    "control_stop": "st_stop",
    "control_create_clone_of": "st_create_clone",
    "control_delete_this_clone": "st_delete_clone",
    # sensing
    "sensing_askandwait": "st_ask",
    "sensing_resettimer": "st_reset_timer",
    # data
    "data_setvariableto": "st_set_var",
    "data_changevariableby": "st_change_var",
    "data_showvariable": "st_show_var",
    "data_hidevariable": "st_hide_var",
    "data_addtolist": "st_list_add",
    "data_deleteoflist": "st_list_delete",
    "data_deletealloflist": "st_list_clear",
    "data_insertatlist": "st_list_insert",
    "data_replaceitemoflist": "st_list_replace",
    "data_showlist": "st_show_list",
    "data_hidelist": "st_hide_list",
    # procedures
    "procedures_call": "st_procedure_call",
}


class StatementEmitter:
    """Emit one script as a GDScript coroutine function driven by awaits."""

    def __init__(
        self,
        project: Project,
        script: Script,
        warn: Callable[[str], None],
        procedures: dict[tuple[str, str], Procedure] | None = None,
        procedure: Procedure | None = None,
    ) -> None:
        self.project = project
        self.script = script
        self.target = script.target
        self.warn = warn
        self.procedures = procedures or {}
        self.procedure = procedure
        self.expr = ExpressionEmitter(project, script, warn, procedure=procedure)
        self.lines: list[str] = []
        self.indent = 1  # inside the function body
        self._visited: set[str] = set()

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def line(self, text: str) -> None:
        self.lines.append("\t" * self.indent + text)

    def substack(self, block: Block, name: str) -> bool:
        value = block.inputs.get(name)
        if isinstance(value, BlockRef) and value.block_id in self.target.blocks:
            self.emit_stack(value.block_id)
            return True
        return False

    def block_open(self, header: str) -> None:
        self.line(header)
        self.indent += 1

    def block_close(self) -> None:
        self.indent -= 1

    # ------------------------------------------------------------------
    # stack walking
    # ------------------------------------------------------------------
    def emit_stack(self, start_id: str) -> None:
        block_id: str | None = start_id
        while block_id and block_id not in self._visited:
            self._visited.add(block_id)
            block = self.target.blocks.get(block_id)
            if block is None:
                return
            self.emit_statement(block)
            block_id = block.next_id

    def emit_statement(self, block: Block) -> None:
        method = STMT_METHODS.get(block.opcode)
        if method is None:
            self.warn(
                f"unsupported block {block.opcode!r} in script at "
                f"{self.target.name}:{round(self.script.hat.y)} - replaced with a no-op"
            )
            self.line(f"rt.unsupported({godot_str(block.opcode)})")
            return
        getattr(self, method)(block)

    # ------------------------------------------------------------------
    # motion
    # ------------------------------------------------------------------
    def st_move(self, b: Block) -> None:
        self.line(f"rt.move(ctx, {self.expr.num_input(b, 'STEPS')})")

    def st_turn_right(self, b: Block) -> None:
        self.line(
            f"ctx.direction = rt.norm_dir(ctx.direction + {self.expr.num_input(b, 'DEGREES')})"
        )

    def st_turn_left(self, b: Block) -> None:
        self.line(
            f"ctx.direction = rt.norm_dir(ctx.direction - {self.expr.num_input(b, 'DEGREES')})"
        )

    def st_goto(self, b: Block) -> None:
        target = self.expr.input_expr(b, "TO", godot_str("_random_"))
        self.line(f"rt.goto_target(ctx, Scratch.s_str({target}))")

    def st_goto_xy(self, b: Block) -> None:
        self.line(f"ctx.x = {self.expr.num_input(b, 'X')}")
        self.line(f"ctx.y = {self.expr.num_input(b, 'Y')}")

    def st_glide_xy(self, b: Block) -> None:
        secs = self.expr.num_input(b, "SECS")
        x = self.expr.num_any(b, ("X", "TO_X"), "0.0")
        y = self.expr.num_any(b, ("Y", "TO_Y"), "0.0")
        self.line(f"await rt.glide_to(ctx, {secs}, {x}, {y})")

    def st_glide_to(self, b: Block) -> None:
        secs = self.expr.num_input(b, "SECS")
        target = self.expr.input_expr(b, "TO", godot_str("_mouse_"))
        self.line(
            f"await rt.glide_to(ctx, {secs}, rt.tx(Scratch.s_str({target})), rt.ty(Scratch.s_str({target})))"
        )

    def st_point_direction(self, b: Block) -> None:
        self.line(f"ctx.direction = rt.norm_dir({self.expr.num_input(b, 'DIRECTION')})")

    def st_point_towards(self, b: Block) -> None:
        target = self.expr.input_expr(b, "TOWARDS", godot_str("_mouse_"))
        self.line(f"rt.point_towards(ctx, Scratch.s_str({target}))")

    def st_change_x(self, b: Block) -> None:
        self.line(f"ctx.x = ctx.x + {self.expr.num_input(b, 'DX')}")

    def st_set_x(self, b: Block) -> None:
        self.line(f"ctx.x = {self.expr.num_input(b, 'X')}")

    def st_change_y(self, b: Block) -> None:
        self.line(f"ctx.y = ctx.y + {self.expr.num_input(b, 'DY')}")

    def st_set_y(self, b: Block) -> None:
        self.line(f"ctx.y = {self.expr.num_input(b, 'Y')}")

    def st_bounce(self, b: Block) -> None:
        self.line("rt.bounce(ctx)")

    def st_rotation_style(self, b: Block) -> None:
        style = self.expr.input_expr(b, "STYLE", godot_str("all around"))
        self.line(f"ctx.rotation_style = Scratch.s_str({style})")

    # ------------------------------------------------------------------
    # looks
    # ------------------------------------------------------------------
    def st_say(self, b: Block) -> None:
        self.line(f"ctx.say = {self.expr.input_expr(b, 'MESSAGE')}")

    def st_say_for(self, b: Block) -> None:
        self.line(f"ctx.say = {self.expr.input_expr(b, 'MESSAGE')}")
        self.line(f"await rt.wait_secs({self.expr.num_input(b, 'SECS')})")
        self.line("ctx.say = null")

    def st_think(self, b: Block) -> None:
        self.line(f"ctx.think = {self.expr.input_expr(b, 'MESSAGE')}")

    def st_think_for(self, b: Block) -> None:
        self.line(f"ctx.think = {self.expr.input_expr(b, 'MESSAGE')}")
        self.line(f"await rt.wait_secs({self.expr.num_input(b, 'SECS')})")
        self.line("ctx.think = null")

    def st_show(self, b: Block) -> None:
        self.line("ctx.visible = true")

    def st_hide(self, b: Block) -> None:
        self.line("ctx.visible = false")

    def st_switch_costume(self, b: Block) -> None:
        costume = self.expr.input_expr(b, "COSTUME", '""')
        self.line(f"ctx.set_costume(Scratch.s_str({costume}))")

    def st_next_costume(self, b: Block) -> None:
        self.line("ctx.next_costume()")

    def st_switch_backdrop(self, b: Block) -> None:
        backdrop = self.expr.input_expr(b, "BACKDROP", '""')
        self.line(f"rt.set_backdrop(Scratch.s_str({backdrop}))")

    def st_next_backdrop(self, b: Block) -> None:
        self.line("rt.next_backdrop()")

    def st_change_size(self, b: Block) -> None:
        self.line(
            f"ctx.size = rt.clamp_size(ctx.size + {self.expr.num_input(b, 'CHANGE')})"
        )

    def st_set_size(self, b: Block) -> None:
        self.line(f"ctx.size = rt.clamp_size({self.expr.num_input(b, 'SIZE')})")

    def st_change_ghost(self, b: Block) -> None:
        self.line(f"rt.change_effect(ctx, \"ghost\", {self.expr.num_input(b, 'CHANGE')})")

    def st_set_ghost(self, b: Block) -> None:
        self.line(f"rt.set_effect(ctx, \"ghost\", {self.expr.num_input(b, 'VALUE')})")

    def st_change_effect(self, b: Block) -> None:
        effect = b.field("EFFECT", "color").lower()
        self.line(f"rt.change_effect(ctx, {godot_str(effect)}, {self.expr.num_input(b, 'CHANGE')})")

    def st_set_effect(self, b: Block) -> None:
        effect = b.field("EFFECT", "color").lower()
        self.line(f"rt.set_effect(ctx, {godot_str(effect)}, {self.expr.num_input(b, 'VALUE')})")

    def st_go_front_back(self, b: Block) -> None:
        where = b.field("FRONT_BACK", "front")
        self.line("rt.go_to_front(ctx)" if where == "front" else "rt.go_to_back(ctx)")

    def st_layer_backward(self, b: Block) -> None:
        self.line("rt.go_layer(ctx, -1)")

    def st_layer_forward(self, b: Block) -> None:
        self.line("rt.go_layer(ctx, 1)")

    def st_clear_effects(self, b: Block) -> None:
        self.line("rt.clear_effects(ctx)")

    # ------------------------------------------------------------------
    # sound
    # ------------------------------------------------------------------
    def st_sound_play(self, b: Block) -> None:
        sound = self.expr.input_expr(b, "SOUND_MENU", '""')
        self.line(f"rt.play_sound(ctx, Scratch.s_str({sound}))")

    def st_sound_play_until_done(self, b: Block) -> None:
        sound = self.expr.input_expr(b, "SOUND_MENU", '""')
        self.line(f"await rt.play_until_done(ctx, Scratch.s_str({sound}))")

    def st_sound_stop_all(self, b: Block) -> None:
        self.line("rt.stop_all_sounds()")

    def st_sound_change_volume(self, b: Block) -> None:
        self.line(
            f"ctx.volume = rt.clamp_volume(ctx.volume + {self.expr.num_input(b, 'VALUE')})"
        )

    def st_sound_set_volume(self, b: Block) -> None:
        self.line(f"ctx.volume = rt.clamp_volume({self.expr.num_input(b, 'VALUE')})")

    def st_sound_change_effect(self, b: Block) -> None:
        effect = b.field("EFFECT", "PITCH")
        self.line(
            f"rt.change_sound_effect(ctx, {godot_str(effect)}, {self.expr.num_input(b, 'VALUE')})"
        )

    def st_sound_set_effect(self, b: Block) -> None:
        effect = b.field("EFFECT", "PITCH")
        self.line(
            f"rt.set_sound_effect(ctx, {godot_str(effect)}, {self.expr.num_input(b, 'VALUE')})"
        )

    def st_sound_clear_effects(self, b: Block) -> None:
        self.line("rt.clear_sound_effects(ctx)")

    # ------------------------------------------------------------------
    # events
    # ------------------------------------------------------------------
    def _broadcast_name(self, b: Block) -> str:
        return self.expr.input_expr(b, "BROADCAST_INPUT", '""')

    def st_broadcast(self, b: Block) -> None:
        name = self._broadcast_name(b)
        self.line(f"rt.broadcast(Scratch.s_str({name}))")

    def st_broadcast_wait(self, b: Block) -> None:
        name = self._broadcast_name(b)
        self.line(f"await rt.broadcast_wait(Scratch.s_str({name}))")

    # ------------------------------------------------------------------
    # control
    # ------------------------------------------------------------------
    def st_wait(self, b: Block) -> None:
        self.line(f"await rt.wait_secs({self.expr.num_input(b, 'DURATION')})")

    def st_wait_until(self, b: Block) -> None:
        cond = self.expr.input_expr(b, "CONDITION", "false")
        self.block_open(f"while not Scratch.s_bool({cond}):")
        self.line("await rt.tick")
        self.block_close()

    def st_repeat(self, b: Block) -> None:
        times = self.expr.num_input(b, "TIMES")
        self.block_open(f"for _i in range(Scratch.repeat_count({times})):")
        if not self.substack(b, "SUBSTACK"):
            self.line("pass")
        self.block_close()

    def st_forever(self, b: Block) -> None:
        # always end the body with an await: Scratch runs one forever iteration
        # per frame, and a conditional wait inside is not enough
        self.block_open("while true:")
        if not self.substack(b, "SUBSTACK"):
            self.line("pass")
        self.line("await rt.tick")
        self.block_close()

    def st_if(self, b: Block) -> None:
        cond = self.expr.input_expr(b, "CONDITION", "false")
        self.block_open(f"if Scratch.s_bool({cond}):")
        if not self.substack(b, "SUBSTACK"):
            self.line("pass")
        self.block_close()

    def st_if_else(self, b: Block) -> None:
        cond = self.expr.input_expr(b, "CONDITION", "false")
        self.block_open(f"if Scratch.s_bool({cond}):")
        if not self.substack(b, "SUBSTACK"):
            self.line("pass")
        self.indent -= 1
        self.line("else:")
        self.indent += 1
        if not self.substack(b, "SUBSTACK2"):
            self.line("pass")
        self.block_close()

    def st_repeat_until(self, b: Block) -> None:
        cond = self.expr.input_expr(b, "CONDITION", "false")
        # same reasoning as st_forever: guarantee one wake-up per frame
        self.block_open(f"while not Scratch.s_bool({cond}):")
        if not self.substack(b, "SUBSTACK"):
            self.line("pass")
        self.line("await rt.tick")
        self.block_close()

    def st_stop(self, b: Block) -> None:
        option = b.field("STOP_OPTION", "this script")
        if option == "all":
            self.line("rt.stop_all()")
            self.line("return")
        elif option == "other scripts in sprite":
            self.line("rt.stop_others(ctx)")
        else:  # "this script"
            self.line("return")

    def st_create_clone(self, b: Block) -> None:
        target = self.expr.input_expr(b, "CLONE_OPTION", godot_str("_myself_"))
        self.line(f"rt.create_clone(ctx, {target})")

    def st_delete_clone(self, b: Block) -> None:
        self.block_open("if ctx.is_clone:")
        self.line("rt.remove_clone(ctx)")
        self.line("return")
        self.block_close()

    # ------------------------------------------------------------------
    # sensing
    # ------------------------------------------------------------------
    def st_ask(self, b: Block) -> None:
        question = self.expr.input_expr(b, "QUESTION", '""')
        self.line(f"await rt.ask(Scratch.s_str({question}))")

    def st_reset_timer(self, b: Block) -> None:
        self.line("rt.reset_timer()")

    # ------------------------------------------------------------------
    # data
    # ------------------------------------------------------------------
    def _var_ref(self, b: Block) -> str:
        name, var_id = b.fields.get("VARIABLE", (b.field("VARIABLE"), None))
        return self.expr.var_ref(var_id, name)

    def _list_ref(self, b: Block) -> str:
        name, list_id = b.fields.get("LIST", (b.field("LIST"), None))
        return self.expr.list_ref(list_id, name)

    def _var_id(self, b: Block) -> str:
        name, var_id = b.fields.get("VARIABLE", (b.field("VARIABLE"), None))
        return var_id or name

    def _list_id(self, b: Block) -> str:
        name, list_id = b.fields.get("LIST", (b.field("LIST"), None))
        return list_id or name

    def st_set_var(self, b: Block) -> None:
        self.line(f"{self._var_ref(b)} = {self.expr.input_expr(b, 'VALUE')}")

    def st_change_var(self, b: Block) -> None:
        ref = self._var_ref(b)
        value = self.expr.input_expr(b, "VALUE")
        self.line(f"{ref} = Scratch.s_add({ref}, {value})")

    def st_show_var(self, b: Block) -> None:
        self.line(f"rt.set_monitor_visible({godot_str(self._var_id(b))}, true)")

    def st_hide_var(self, b: Block) -> None:
        self.line(f"rt.set_monitor_visible({godot_str(self._var_id(b))}, false)")

    def st_list_add(self, b: Block) -> None:
        self.line(f"Scratch.list_add({self._list_ref(b)}, {self.expr.input_expr(b, 'ITEM')})")

    def st_list_delete(self, b: Block) -> None:
        self.line(f"Scratch.list_delete({self._list_ref(b)}, {self.expr.input_expr(b, 'INDEX')})")

    def st_list_clear(self, b: Block) -> None:
        self.line(f"Scratch.list_clear({self._list_ref(b)})")

    def st_list_insert(self, b: Block) -> None:
        lst = self._list_ref(b)
        index = self.expr.input_expr(b, "INDEX")
        item = self.expr.input_expr(b, "ITEM")
        self.line(f"Scratch.list_insert({lst}, {index}, {item})")

    def st_list_replace(self, b: Block) -> None:
        lst = self._list_ref(b)
        index = self.expr.input_expr(b, "INDEX")
        item = self.expr.input_expr(b, "ITEM")
        self.line(f"Scratch.list_replace({lst}, {index}, {item})")

    def st_show_list(self, b: Block) -> None:
        self.line(f"rt.set_list_visible({godot_str(self._list_id(b))}, true)")

    def st_hide_list(self, b: Block) -> None:
        self.line(f"rt.set_list_visible({godot_str(self._list_id(b))}, false)")

    # ------------------------------------------------------------------
    # procedures
    # ------------------------------------------------------------------
    def st_procedure_call(self, b: Block) -> None:
        proccode = b.mutation.get("proccode", "")
        procedure = self.procedures.get((self.target.name, proccode))
        if procedure is None:
            self.warn(
                f"custom block {proccode!r} has no definition in {self.target.name} "
                f"(procedures_call) - replaced with a no-op"
            )
            self.line('rt.unsupported("procedures_call")')
            return
        args = [self.expr.input_expr(b, argid, '""') for argid in procedure.argumentids]
        arguments = f", {', '.join(args)}" if args else ""
        self.line(f"await {procedure.fn_name}(ctx, rt{arguments})")

    # ------------------------------------------------------------------
    # function assembly
    # ------------------------------------------------------------------
    def emit_function(self, function_name: str) -> str | None:
        """Return the full source of one script function (or None to skip).

        Plain method form (``func name(ctx, rt) -> void:``): every function
        lives in the same scripts.gd class so procedures can call each other
        in any definition order.
        """
        hat = self.script.hat
        if hat.opcode == "procedures_definition":
            if self.procedure is None:
                self.warn(
                    f"custom block definition has no prototype block - skipped script in "
                    f"{self.target.name}"
                )
                return None
            params = ", ".join(
                ["ctx, rt", *(gd_ident(name) for name in self.procedure.param_list)]
            )
            self.lines = [f"func {function_name}({params}) -> void:"]
            self.indent = 1
            self.line(hat_comment(hat))
            body = len(self.lines)
            if hat.next_id:
                self.emit_stack(hat.next_id)
            if len(self.lines) == body:
                self.line("pass")
            return "\n".join(self.lines)

        self.lines = [f"func {function_name}(ctx, rt) -> void:"]
        self.indent = 1
        self.line(hat_comment(hat))
        body = len(self.lines)
        if hat.next_id:
            self.emit_stack(hat.next_id)
        if len(self.lines) == body:
            self.line("pass")
        return "\n".join(self.lines)
