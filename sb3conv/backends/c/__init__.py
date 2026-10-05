"""C (SDL2) backend: emit a self-contained native project.

Output layout::

    <out>/main.c            generated scripts + manifest data + SCRIPTS registration
    <out>/runtime.h         copy of runtime_src.h
    <out>/runtime.c         copy of runtime_src.c (SDL2/SDL2_image/SDL2_ttf/SDL2_mixer)
    <out>/Makefile          canonical zig cc link line (SDL2_HOME guarded)
    <out>/sb3_manifest.json stage/sprite/monitor description (reference copy)
    <out>/assets/*          costumes and sounds extracted from the .sb3
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from sb3conv.backends.base import BackendSpec, EmitResult, OutputFile
from sb3conv.backends.c.exprs import c_str, format_number
from sb3conv.backends.c.stmts import StatementEmitter, value_params
from sb3conv.backends.python import (
    AssetPlan,
    _manifest,
    _plan_assets,
    _route_fields,
    _script_language,
)
from sb3conv.errors import BackendError
from sb3conv.sb3.model import Monitor, Project, Target
from sb3conv.sb3.procedures import find_procedures, procedure_by_script, procedure_map

RUNTIME_HEADER = Path(__file__).with_name("runtime_src.h")
RUNTIME_SOURCE = Path(__file__).with_name("runtime_src.c")
VENDOR_DIR = Path(__file__).parent / "vendor" / "nanosvg"

# The link line that works with zig cc (mingw) + the SDL2 devel packages:
# SDL2main first because SDL.h renames main; libmsvcrt.a provides _setjmp.
LINK_LIBS = [
    "-lmingw32",
    "-lmingwex",
    "-lSDL2main",
    "-lSDL2",
    "-lSDL2_image",
    "-lSDL2_ttf",
    "-lSDL2_mixer",
    "-lmsvcrt",
    "-lgdi32",
    "-lwinmm",
    "-limm32",
    "-lole32",
    "-loleaut32",
    "-lsetupapi",
    "-lversion",
    "-lcfgmgr32",
    "-lusp10",
    "-lrpcrt4",
    "-luuid",
]


def find_zig() -> str | None:
    """Locate the zig compiler: $ZIG, PATH, then the portable ~/zigsdk install."""
    env = os.environ.get("ZIG")
    if env and Path(env).exists():
        return env
    found = shutil.which("zig")
    if found:
        return found
    fallback = Path.home() / "zigsdk" / "zig.exe"
    if fallback.exists():
        return str(fallback)
    return None


def find_sdl2_home() -> Path | None:
    """Locate SDL2 development files: $SDL2_HOME, then the portable ~/sdl2-mingw."""
    env = os.environ.get("SDL2_HOME")
    if env and (Path(env) / "include").is_dir():
        return Path(env)
    fallback = Path.home() / "sdl2-mingw"
    if (fallback / "include").is_dir():
        return fallback
    return None


def build_executable(out_dir: Path | str, *, exe_name: str = "game.exe") -> Path:
    """Compile main.c + runtime.c in ``out_dir`` into a runnable executable."""
    out_dir = Path(out_dir).resolve()
    zig = find_zig()
    sdl = find_sdl2_home()
    if zig is None:
        raise BackendError(
            "zig not found; install zig (https://ziglang.org) or set ZIG to its path"
        )
    if sdl is None:
        raise BackendError(
            "SDL2 development files not found; set SDL2_HOME to a directory "
            "with include/ and lib/ (SDL2, SDL2_image, SDL2_ttf, SDL2_mixer)"
        )
    exe = out_dir / exe_name
    command = [
        zig,
        "cc",
        "main.c",
        "runtime.c",
        "-std=c11",
        "-Wall",
        f"-I{sdl / 'include'}",
        f"-L{sdl / 'lib'}",
        *LINK_LIBS,
        "-o",
        str(exe),
    ]
    proc = subprocess.run(
        command, cwd=out_dir, capture_output=True, text=True, check=False
    )
    if proc.returncode != 0:
        raise BackendError(f"C build failed:\n{proc.stderr or proc.stdout}")
    return exe


def runtime_env(smoke: bool = False) -> dict[str, str]:
    """Environment for running the executable: SDL DLLs on PATH, dummy drivers."""
    env = dict(os.environ)
    sdl = find_sdl2_home()
    if sdl is not None:
        env["PATH"] = str(sdl / "bin") + os.pathsep + env.get("PATH", "")
    if smoke:
        env["SDL_VIDEODRIVER"] = "dummy"
        env["SDL_AUDIODRIVER"] = "dummy"
    return env


# ----------------------------------------------------------------------
# manifest -> static C data
# ----------------------------------------------------------------------
def _c_double(value: float) -> str:
    return format_number(float(value))


def _value_init(value: object) -> str:
    """Static initializer for one Value (plain braces, no compound literals)."""
    if isinstance(value, bool):
        return f"{{VAL_NUM, {1 if value else 0}, {{0}}}}"
    if isinstance(value, (int, float)):
        return f"{{VAL_NUM, {_c_double(value)}, {{0}}}}"
    return f"{{VAL_STR, 0.0, {c_str(str(value))}}}"


def _float_or_zero(text: object) -> float:
    try:
        return float(text)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


def _target_data(index: int, target: Target, plan: AssetPlan) -> tuple[list[str], str]:
    """Static arrays for one target plus the body of its TargetDef initializer."""
    lines: list[str] = []
    nvars = len(target.variables)
    if nvars:
        lines.append(f"static VarSlot vars_{index}[] = {{")
        for name, value in target.variables.values():
            lines.append(f"  {{{c_str(name)}, {_value_init(value)}}},")
        lines.append("};")
    vars_field = f".vars = vars_{index}, .nvars = {nvars}" if nvars else ".vars = NULL, .nvars = 0"

    nlists = len(target.lists)
    if nlists:
        for slot, (_name, items) in enumerate(target.lists.values()):
            if items:
                lines.append(f"static Value list_{index}_{slot}_items[] = {{")
                for item in items:
                    lines.append(f"  {_value_init(item)},")
                lines.append("};")
        lines.append(f"static ListSlot lists_{index}[] = {{")
        for slot, (name, items) in enumerate(target.lists.values()):
            if items:
                count = len(items)
                lines.append(f"  {{{c_str(name)}, list_{index}_{slot}_items, {count}, {count}}},")
            else:
                lines.append(f"  {{{c_str(name)}, NULL, 0, 0}},")
        lines.append("};")
    lists_field = f".lists = lists_{index}, .nlists = {nlists}" if nlists else ".lists = NULL, .nlists = 0"

    ncostumes = len(target.costumes)
    if ncostumes:
        lines.append(f"static CostumeDef costumes_{index}[] = {{")
        for costume in target.costumes:
            entry = plan.costume(target, costume)
            cx = repr(float(entry.cx))
            cy = repr(float(entry.cy))
            resolution = int(entry.resolution) or 1
            lines.append(
                f"  {{.name = {c_str(costume.name)}, .id = {c_str(costume.costume_id)}, "
                f".file = {c_str(entry.filename)}, .cx = {cx}, .cy = {cy}, "
                f".resolution = {resolution}}},"
            )
        lines.append("};")
    costumes_field = (
        f".costumes = costumes_{index}, .ncostumes = {ncostumes}"
        if ncostumes
        else ".costumes = NULL, .ncostumes = 0"
    )

    nsounds = len(target.sounds)
    if nsounds:
        lines.append(f"static SoundDef sounds_{index}[] = {{")
        for sound in target.sounds:
            lines.append(f"  {{.name = {c_str(sound.name)}, .file = {c_str(sound.asset.filename)}}},")
        lines.append("};")
    sounds_field = f".sounds = sounds_{index}, .nsounds = {nsounds}" if nsounds else ".sounds = NULL, .nsounds = 0"

    body = [
        f"{{.name = {c_str(target.name)}, .is_stage = {1 if target.is_stage else 0}, ",
        f"{vars_field}, {lists_field}, {costumes_field}, {sounds_field}, ",
        f".current_costume = {target.current_costume}, .volume = {target.volume}, ",
        f".layer_order = {target.layer_order}",
    ]
    if target.is_stage:
        body.append(', .direction = 90, .size = 100, .visible = 1, .rotation_style = "all around"')
    else:
        body.append(
            f", .x = {_c_double(target.x)}, .y = {_c_double(target.y)}, "
            f".direction = {_c_double(target.direction)}, .size = {_c_double(target.size)}, "
            f".visible = {1 if target.visible else 0}, "
            f".rotation_style = {c_str(target.rotation_style)}"
        )
    body.append("},")
    return lines, "".join(body)


def _monitors_data(monitors: list[Monitor]) -> tuple[list[str], str]:
    if not monitors:
        return [], "NULL"
    lines = ["static MonitorDef MONITORS[] = {"]
    for monitor in monitors:
        target_field = c_str(monitor.target_name) if monitor.target_name else "NULL"
        lines.append(
            f"  {{.id = {c_str(monitor.monitor_id)}, .label = {c_str(monitor.label)}, "
            f".target = {target_field}, .is_list = {1 if monitor.is_list else 0}, "
            f".x = {_c_double(monitor.x)}, .y = {_c_double(monitor.y)}, "
            f".mode = {c_str(monitor.mode)}, .visible = {1 if monitor.visible else 0}, "
            f".initial = {_value_init(monitor.value)}}},"
        )
    lines.append("};")
    return lines, "MONITORS"


def _data_source(project: Project, options: dict, plan: AssetPlan) -> list[str]:
    """Every static the runtime reads: vars, lists, costumes, targets, monitors."""
    targets = [project.stage, *project.sprites]
    lines: list[str] = []
    target_bodies: list[str] = []
    for index, target in enumerate(targets):
        data_lines, body = _target_data(index, target, plan)
        lines.extend(data_lines)
        target_bodies.append("  " + body)
    lines.append("static TargetDef TARGETS[] = {")
    lines.extend(target_bodies)
    lines.append("};")
    lines.append("")

    monitor_lines, monitors_field = _monitors_data(project.monitors)
    lines.extend(monitor_lines)
    if monitor_lines:
        lines.append("")

    lines.append("static SbProject PROJECT = {")
    lines.append(f"  .name = {c_str(str(options.get('name') or 'Scratch project'))},")
    lines.append('  .asset_dir = "assets",')
    lines.append(f"  .scale = {int(options.get('scale', 2))},")
    lines.append(f"  .fps = {int(options.get('fps', 30))},")
    lines.append("  .targets = TARGETS,")
    lines.append(f"  .ntargets = {len(targets)},")
    lines.append(f"  .monitors = {monitors_field},")
    lines.append(f"  .nmonitors = {len(project.monitors)},")
    lines.append("};")
    lines.append("")
    return lines


def _scripts_source(regs: list[tuple[str, str, dict, str]]) -> list[str]:
    if not regs:
        return ["static const ScriptReg *const SCRIPTS = NULL;", "#define SB_SCRIPT_COUNT 0", ""]
    lines = ["static const ScriptReg SCRIPTS[] = {"]
    for sprite, hat, fields, fn_name in regs:
        parts = [f".sprite = {c_str(sprite)}", f".hat = {c_str(hat)}"]
        if "KEY_OPTION" in fields:
            parts.append(f".key_option = {c_str(fields['KEY_OPTION'])}")
        if "BROADCAST_OPTION" in fields:
            parts.append(f".broadcast_option = {c_str(fields['BROADCAST_OPTION'])}")
        if "BACKDROP" in fields:
            parts.append(f".backdrop = {c_str(fields['BACKDROP'])}")
        if "WHENGREATERTHANOPERATOR" in fields:
            parts.append(f".greater_op = {c_str(fields['WHENGREATERTHANOPERATOR'])}")
        if "WHENGREATERTHANVALUE" in fields:
            value = _c_double(_float_or_zero(fields["WHENGREATERTHANVALUE"]))
            parts.append(f".greater_value = {value}")
        parts.append(f".fn = {fn_name}")
        lines.append("  {" + ", ".join(parts) + "},")
    lines.append("};")
    lines.append(f"#define SB_SCRIPT_COUNT {len(regs)}")
    lines.append("")
    return lines


def _main_source(
    name: str,
    functions: list[str],
    data_lines: list[str],
    regs: list[tuple[str, str, dict, str]],
    forward_decls: list[str] | None = None,
) -> str:
    lines = [
        "/* Converted from Scratch by sb3conv - do not edit by hand.",
        " *",
        f" * Project: {name}",
        " * Build:   make SDL2_HOME=/path/to/sdl2   (see Makefile)",
        " * Run:     game.exe [--smoke N] [--dump] [--scale N] [--fps N]",
        " */",
        '#include "runtime.h"',
        "",
    ]
    if forward_decls:
        lines.extend(forward_decls)
        lines.append("")
    for source in functions:
        lines.append(source)
        lines.append("")
    lines.extend(data_lines)
    lines.extend(_scripts_source(regs))
    lines.append("int main(int argc, char **argv) {")
    lines.append("  return sb_run(&PROJECT, argc, argv, SCRIPTS, SB_SCRIPT_COUNT);")
    lines.append("}")
    lines.append("")
    return "\n".join(lines)


def _makefile_source() -> str:
    return (
        "# Generated by sb3conv - build the converted project.\n"
        "#\n"
        "# Needs a C compiler plus SDL2 development files (headers, import\n"
        "# libraries, DLLs). The canonical Windows setup is zig cc and the\n"
        "# SDL2/SDL2_image/SDL2_ttf/SDL2_mixer devel packages:\n"
        "#\n"
        "#     make SDL2_HOME=C:/path/to/sdl2-mingw\n"
        "#\n"
        "# Override the compiler with: make CC=gcc SDL2_HOME=...\n"
        "\n"
        "SDL2_HOME ?=\n"
        "ifeq ($(strip $(SDL2_HOME)),)\n"
        "$(error SDL2_HOME is not set - point it at a directory with include/ and lib/)\n"
        "endif\n"
        "\n"
        "ZIG ?= zig\n"
        "CC = $(ZIG) cc\n"
        "OUT ?= game.exe\n"
        "CFLAGS = -std=c11 -Wall -I$(SDL2_HOME)/include\n"
        "LDFLAGS = -L$(SDL2_HOME)/lib"
        " -lmingw32 -lmingwex -lSDL2main -lSDL2 -lSDL2_image -lSDL2_ttf -lSDL2_mixer"
        " -lmsvcrt -lgdi32 -lwinmm -limm32 -lole32 -loleaut32 -lsetupapi -lversion"
        " -lcfgmgr32 -lusp10 -lrpcrt4 -luuid\n"
        "\n"
        "all: $(OUT)\n"
        "\n"
        "$(OUT): main.c runtime.c runtime.h\n"
        "\t$(CC) main.c runtime.c $(CFLAGS) $(LDFLAGS) -o $(OUT)\n"
        "\n"
        "run: $(OUT)\n"
        "\t$(OUT)\n"
        "\n"
        "clean:\n"
        "\trm -f $(OUT)\n"
        "\n"
        ".PHONY: all run clean\n"
    )


def _check_c(main_source: str, runtime_header: str) -> None:
    """Syntax-check the generated main.c when a compiler is available."""
    zig = find_zig()
    if zig is None:
        return
    with tempfile.TemporaryDirectory(prefix="sb3conv-c-") as tmp:
        directory = Path(tmp)
        (directory / "main.c").write_text(main_source, encoding="utf-8")
        (directory / "runtime.h").write_text(runtime_header, encoding="utf-8")
        proc = subprocess.run(
            [zig, "cc", "-c", "-std=c11", "-Wall", "main.c", "-o", "main.o"],
            cwd=directory,
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout).strip()
            raise BackendError(f"generated main.c does not compile:\n{detail}")


def emit_c(project: Project, options: dict) -> EmitResult:
    warnings: list[str] = []

    def warn(message: str) -> None:
        warnings.append(message)

    overrides = dict(options.get("script_lang") or {})
    assets: dict[str, bytes] = dict(options.get("assets") or {})

    functions: list[str] = []
    regs: list[tuple[str, str, dict, str]] = []
    script_languages: dict[str, str] = {}

    procedures = find_procedures(project)
    proc_map = procedure_map(procedures)
    proc_script = procedure_by_script(procedures)
    # Procedures may be called before they appear in the file, and may call
    # each other, so every definition gets a forward declaration up front.
    forward_decls = [
        "static void "
        f"{procedure.fn_name}(Actor *ctx, Rt *rt"
        + "".join(f", {param}" for param in value_params(procedure))
        + ");"
        for procedure in procedures
    ]

    for index, script in enumerate(project.all_scripts()):
        procedure = proc_script.get(script.script_id)
        is_definition = script.hat.opcode == "procedures_definition"
        language = _script_language(script, overrides, default="c")
        script_languages[script.script_id] = language
        if not is_definition and language != "c":
            warn(
                f"script at {script.target.name}:{round(script.hat.y)} is tagged "
                f"{language!r}; the c backend skipped it"
            )
            continue
        function_name = procedure.fn_name if procedure else f"script_{index}"
        source = StatementEmitter(
            project, script, warn, procedures=proc_map, procedure=procedure
        ).emit_function(function_name)
        if source is None:
            continue
        functions.append(source)
        if is_definition:
            continue  # custom blocks are called, not registered as hat routes
        regs.append(
            (script.target.name, script.hat.opcode, _route_fields(project, script), function_name)
        )

    runtime_header = RUNTIME_HEADER.read_text(encoding="utf-8")
    runtime_source = RUNTIME_SOURCE.read_text(encoding="utf-8")
    plan = _plan_assets(project, assets, warn, svg_policy="rasterize_complex")
    main_source = _main_source(
        str(options.get("name") or "Scratch project"),
        functions,
        _data_source(project, options, plan),
        regs,
        forward_decls,
    )
    _check_c(main_source, runtime_header)

    manifest_source = json.dumps(_manifest(project, options, plan), indent=2, ensure_ascii=False)
    files = [
        OutputFile(path="main.c", content=main_source),
        OutputFile(path="runtime.h", content=runtime_header),
        OutputFile(path="runtime.c", content=runtime_source),
        OutputFile(path="nanosvg.h", content=(VENDOR_DIR / "nanosvg.h").read_text(encoding="utf-8")),
        OutputFile(
            path="nanosvgrast.h",
            content=(VENDOR_DIR / "nanosvgrast.h").read_text(encoding="utf-8"),
        ),
        OutputFile(
            path="nanosvg-LICENSE.txt",
            content=(VENDOR_DIR / "LICENSE.txt").read_text(encoding="utf-8"),
        ),
        OutputFile(path="Makefile", content=_makefile_source()),
        OutputFile(path="sb3_manifest.json", content=manifest_source),
        *plan.files,
    ]
    return EmitResult(
        files=files,
        warnings=warnings,
        entrypoint="main.c",
        script_languages=script_languages,
    )


SPEC = BackendSpec(
    name="c",
    label="C (SDL2)",
    file_extension=".c",
    emitter=emit_c,
)
