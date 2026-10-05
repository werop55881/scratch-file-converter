"""Build the star game as a Scratch project (star-game.sb3).

Game rules:
- Click the star to earn star dust (click power). Planets bought generate
  passive income every second.
- Background stars slowly grow; when one reaches full size it goes supernova,
  pays a bonus and is replaced by a fresh small star.
- The shop shows three upcoming items; only the first slot is buyable.
- Five planets, then one global upgrade that doubles click power and income.
"""

from __future__ import annotations

from pathlib import Path

from .assets import (
    backdrop_png,
    bgstar_nova_png,
    bgstar_png,
    buy_wav,
    click_wav,
    nova_wav,
    planet_png,
    shop_row_png,
    star_nova_png,
    star_png,
)
from .builder import Project, Rep, Script, St

RATE = 22050

PLANET_NAMES = ["Sunlet", "Ringo", "Glacia", "Voltra", "Core"]
PLANET_COSTS = [10, 50, 250, 1200, 6000, 20000]
PLANET_INCOME = [1, 5, 25, 120, 600, 0]
PLANET_COSTUMES = ["planet1", "planet2", "planet3", "planet4", "planet5"]


def V(name: str):
    return ("var", name)


def L(name: str):
    return ("list", name)


def BC(name: str):
    return ("bcast", name)


def MENU(slot: str, value: str):
    return ("menu", slot, value)


def REP(opcode: str, *, fields: dict | None = None, **inputs) -> Rep:
    return Rep(opcode, inputs=inputs, fields=fields or {})


def ST(opcode: str, *, fields: dict | None = None, sub: dict | None = None, **inputs) -> St:
    return St(opcode, inputs=inputs, fields=fields or {}, substacks=sub or {})


def _flat(body) -> list[St]:
    out: list[St] = []
    for part in body:
        if isinstance(part, list):
            out.extend(_flat(part))
        else:
            out.append(part)
    return out


def IF(cond, *body) -> St:
    return ST("control_if", CONDITION=cond, sub={"SUBSTACK": _flat(body)})


def IF_ELSE(cond, then, other) -> St:
    return ST(
        "control_if_else",
        CONDITION=cond,
        sub={"SUBSTACK": _flat(then), "SUBSTACK2": _flat(other)},
    )


def FOREVER(*body) -> St:
    return ST("control_forever", sub={"SUBSTACK": _flat(body)})


def REPEAT(times, *body) -> St:
    return ST("control_repeat", TIMES=times, sub={"SUBSTACK": _flat(body)})


def set_var(name: str, value) -> St:
    return ST("data_setvariableto", fields={"VARIABLE": V(name)}, VALUE=value)


def change_var(name: str, value) -> St:
    return ST("data_changevariableby", fields={"VARIABLE": V(name)}, VALUE=value)


def set_x(value) -> St:
    return ST("motion_setx", X=value)


def set_y(value) -> St:
    return ST("motion_sety", Y=value)


def set_size(value) -> St:
    return ST("looks_setsizeto", SIZE=value)


def say(message) -> St:
    return ST("looks_say", MESSAGE=message)


def wait(seconds: float) -> St:
    return ST("control_wait", DURATION=seconds)


def play(sound: str) -> St:
    return ST("sound_play", SOUND_MENU=MENU("SOUND_MENU", sound))


def switch_costume(value) -> St:
    return ST("looks_switchcostumeto", COSTUME=value)


def create_clone(who: str = "_myself_") -> St:
    return ST("control_create_clone_of", CLONE_OPTION=MENU("CLONE_OPTION", who))


def item_of(list_name: str, index) -> Rep:
    return REP("data_itemoflist", fields={"LIST": L(list_name)}, INDEX=index)


def rnd(low, high) -> Rep:
    return REP("operator_random", FROM=low, TO=high)


def add(a, b) -> Rep:
    return REP("operator_add", NUM1=a, NUM2=b)


def sub(a, b) -> Rep:
    return REP("operator_subtract", NUM1=a, NUM2=b)


def mul(a, b) -> Rep:
    return REP("operator_multiply", NUM1=a, NUM2=b)


def eq(a, b) -> Rep:
    return REP("operator_equals", OPERAND1=a, OPERAND2=b)


def lt(a, b) -> Rep:
    return REP("operator_lt", OPERAND1=a, OPERAND2=b)


def gt(a, b) -> Rep:
    return REP("operator_gt", OPERAND1=a, OPERAND2=b)


def ge(a, b) -> Rep:
    return REP("operator_not", BOOLEAN=lt(a, b))


def join(a, b) -> Rep:
    return REP("operator_join", STRING1=a, STRING2=b)


def mathop(op: str, number) -> Rep:
    return REP("operator_mathop", fields={"OPERATOR": op}, NUM=number)


def slot_label():
    names = item_of("planetNames", V("myItem"))
    costs = item_of("planetCosts", V("myItem"))
    return join(join(names, " $"), costs)


def build_project() -> Project:
    project = Project("Star Game")
    project.broadcast_id("supernova")

    stage = project.add_stage()
    for name, value in (
        ("starDust", 0),
        ("perSecond", 0),
        ("clickPower", 1),
        ("planetsBought", 0),
        ("shopIndex", 0),
        ("upgraded", 0),
        ("spawnIdx", 0),
    ):
        stage.add_var(name, value)
    stage.add_list("planetCosts", PLANET_COSTS)
    stage.add_list("planetIncome", PLANET_INCOME)
    stage.add_list("planetNames", PLANET_NAMES)
    stage.add_list("planetCostumes", PLANET_COSTUMES)
    stage.add_costume("nebula", backdrop_png(), 240, 180)
    project.add_monitor("starDust", 310, 5)
    project.add_monitor("perSecond", 310, 35)
    project.add_monitor("clickPower", 310, 65)
    project.add_monitor("planetsBought", 310, 95)

    bgstar = project.add_sprite(
        "BgStar", layer_order=1, visible=False, rotation_style="all around"
    )
    bgstar.add_var("myX", 0)
    bgstar.add_var("myY", 0)
    bgstar.add_var("mySize", 40)
    bgstar.add_costume("bgstar", bgstar_png(), 20, 20)
    bgstar.add_costume("bgstar-nova", bgstar_nova_png(), 32, 32)
    nova_data, nova_frames = nova_wav()
    bgstar.add_sound("nova", nova_data, RATE, nova_frames)
    bgstar.add_script(
        Script(
            "event_whenflagclicked",
            [
                ST("looks_hide"),
                REPEAT(
                    28,
                    set_var("myX", rnd(-230, 230)),
                    set_var("myY", rnd(-165, 165)),
                    set_var("mySize", rnd(20, 60)),
                    create_clone(),
                ),
            ],
            x=30,
            y=30,
        )
    )
    bgstar.add_script(
        Script(
            "control_start_as_clone",
            [
                switch_costume(MENU("COSTUME", "bgstar")),
                ST("looks_show"),
                set_x(V("myX")),
                set_y(V("myY")),
                set_size(V("mySize")),
                FOREVER(
                    change_var("mySize", 0.3),
                    set_size(V("mySize")),
                    IF(
                        gt(V("mySize"), 140),
                        switch_costume(MENU("COSTUME", "bgstar-nova")),
                        play("nova"),
                        ST("event_broadcast", BROADCAST_INPUT=BC("supernova")),
                        set_var("mySize", rnd(20, 60)),
                        set_var("myX", rnd(-230, 230)),
                        set_var("myY", rnd(-165, 165)),
                        create_clone(),
                        wait(0.15),
                        ST("control_delete_this_clone"),
                    ),
                ),
            ],
            x=30,
            y=330,
        )
    )

    planet = project.add_sprite("Planet", layer_order=2, visible=False)
    planet.add_var("myAngle", 0)
    planet.add_var("myRadius", 120)
    planet.add_var("mySpeed", 2)
    for index, costume_name in enumerate(PLANET_COSTUMES):
        planet.add_costume(costume_name, planet_png(index), 36, 36)
    planet.add_script(
        Script(
            "event_whenflagclicked",
            [
                ST("looks_hide"),
                FOREVER(wait(1), change_var("starDust", V("perSecond"))),
            ],
            x=30,
            y=30,
        )
    )
    planet.add_script(
        Script(
            "control_start_as_clone",
            [
                switch_costume(item_of("planetCostumes", V("spawnIdx"))),
                set_var("myAngle", rnd(0, 360)),
                set_var("myRadius", rnd(95, 150)),
                set_var("mySpeed", rnd(1, 4)),
                ST("looks_show"),
                FOREVER(
                    change_var("myAngle", V("mySpeed")),
                    set_x(mul(V("myRadius"), mathop("cos", V("myAngle")))),
                    set_y(mul(V("myRadius"), mathop("sin", V("myAngle")))),
                    wait(0.03),
                ),
            ],
            x=30,
            y=300,
        )
    )

    star = project.add_sprite(
        "Star", layer_order=3, visible=True, x=0, y=0, rotation_style="all around"
    )
    star.add_costume("star", star_png(), 50, 50)
    star.add_costume("star-nova", star_nova_png(), 55, 55)
    click_data, click_frames = click_wav()
    star.add_sound("click", click_data, RATE, click_frames)
    star.add_script(
        Script(
            "event_whenflagclicked",
            [
                set_size(50),
                FOREVER(ST("motion_turnright", DEGREES=1)),
            ],
            x=30,
            y=30,
        )
    )
    star.add_script(
        Script(
            "event_whenthisspriteclicked",
            [
                change_var("starDust", V("clickPower")),
                play("click"),
                set_size(62),
                wait(0.05),
                set_size(50),
            ],
            x=30,
            y=260,
        )
    )
    star.add_script(
        Script(
            "event_whenbroadcastreceived",
            [
                change_var("starDust", mul(10, V("clickPower"))),
                set_size(85),
                wait(0.15),
                set_size(50),
            ],
            fields={"BROADCAST_OPTION": BC("supernova")},
            x=30,
            y=420,
        )
    )

    shop = project.add_sprite(
        "Shop",
        layer_order=4,
        visible=False,
        x=-150,
        y=0,
        rotation_style="don't rotate",
    )
    shop.add_var("slotIdx", 0)
    shop.add_var("myItem", 0)
    for index in range(3):
        shop.add_costume(f"row{index + 1}", shop_row_png(index), 90, 50)
    buy_data, buy_frames = buy_wav()
    shop.add_sound("buy", buy_data, RATE, buy_frames)
    shop.add_script(
        Script(
            "event_whenflagclicked",
            [
                ST("looks_hide"),
                set_var("slotIdx", 0),
                create_clone(),
                set_var("slotIdx", 1),
                create_clone(),
                set_var("slotIdx", 2),
                create_clone(),
            ],
            x=30,
            y=30,
        )
    )
    shop.add_script(
        Script(
            "control_start_as_clone",
            [
                IF_ELSE(
                    eq(V("slotIdx"), 0),
                    [set_y(100), switch_costume(MENU("COSTUME", "row1"))],
                    [
                        IF_ELSE(
                            eq(V("slotIdx"), 1),
                            [set_y(0), switch_costume(MENU("COSTUME", "row2"))],
                            [set_y(-100), switch_costume(MENU("COSTUME", "row3"))],
                        )
                    ],
                ),
                set_x(-150),
                ST("looks_show"),
                FOREVER(
                    set_var("myItem", add(V("shopIndex"), add(V("slotIdx"), 1))),
                    IF_ELSE(
                        gt(V("myItem"), 6),
                        [say("--")],
                        [
                            IF_ELSE(
                                eq(V("myItem"), 6),
                                [
                                    IF_ELSE(
                                        eq(V("upgraded"), 1),
                                        [say("UPGRADE MAXED")],
                                        [say(join("UPGRADE X2 ", item_of("planetCosts", 6)))],
                                    )
                                ],
                                [say(slot_label())],
                            )
                        ],
                    ),
                    wait(0.25),
                ),
            ],
            x=30,
            y=330,
        )
    )
    shop.add_script(
        Script(
            "event_whenthisspriteclicked",
            [
                set_var("myItem", add(V("shopIndex"), add(V("slotIdx"), 1))),
                IF(
                    eq(V("slotIdx"), 0),
                    IF_ELSE(
                        gt(V("myItem"), 5),
                        [
                            IF(
                                eq(V("upgraded"), 0),
                                IF(
                                    ge(V("starDust"), item_of("planetCosts", 6)),
                                    change_var("starDust", sub(0, item_of("planetCosts", 6))),
                                    set_var("upgraded", 1),
                                    change_var("clickPower", V("clickPower")),
                                    change_var("perSecond", V("perSecond")),
                                    play("buy"),
                                ),
                            )
                        ],
                        [
                            IF(
                                ge(V("starDust"), item_of("planetCosts", V("myItem"))),
                                change_var(
                                    "starDust", sub(0, item_of("planetCosts", V("myItem")))
                                ),
                                set_var("spawnIdx", V("myItem")),
                                create_clone("Planet"),
                                change_var("planetsBought", 1),
                                change_var("shopIndex", 1),
                                IF_ELSE(
                                    eq(V("upgraded"), 1),
                                    [
                                        change_var(
                                            "perSecond",
                                            mul(item_of("planetIncome", V("myItem")), 2),
                                        )
                                    ],
                                    [change_var("perSecond", item_of("planetIncome", V("myItem")))],
                                ),
                                play("buy"),
                            )
                        ],
                    ),
                ),
            ],
            x=30,
            y=660,
        )
    )

    return project


def main() -> int:
    out = Path(__file__).with_name("star-game.sb3")
    path = build_project().write(out)
    print(f"wrote {path} ({path.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
