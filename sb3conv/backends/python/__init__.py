"""Python (pygame) backend: emit a self-contained runnable project.

Output layout::

    <out>/main.py            generated scripts + SCRIPTS registration
    <out>/runtime.py         copy of runtime_src.py (stdlib + pygame only)
    <out>/sb3_manifest.json  stage/sprite/monitor description for the runtime
    <out>/assets/*           costumes and sounds extracted from the .sb3
"""

from __future__ import annotations

import ast
import json
from dataclasses import dataclass, field
from pathlib import Path

from sb3conv.backends.base import BackendSpec, EmitResult, OutputFile
from sb3conv.backends.python.stmts import StatementEmitter
from sb3conv.errors import BackendError
from sb3conv.sb3.model import Costume, Literal, Project, Script, Target
from sb3conv.sb3.procedures import find_procedures, procedure_by_script, procedure_map
from sb3conv.svg import RASTER_ZOOM, has_zero_extent, is_complex, rasterize

RUNTIME_SOURCE = Path(__file__).with_name("runtime_src.py")

LANG_ALIASES = {
    "py": "python",
    "python": "python",
    "js": "javascript",
    "javascript": "javascript",
}


def _normalize_lang(value: str | None) -> str:
    if not value:
        return "python"
    key = value.strip().lower()
    return LANG_ALIASES.get(key, key)


def _runtime_helper_names() -> list[str]:
    """Public top-level functions of runtime_src (imported by generated main.py)."""
    tree = ast.parse(RUNTIME_SOURCE.read_text(encoding="utf-8"))
    names = {
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and not node.name.startswith("_")
    }
    names.discard("run_cli")
    return sorted(names)


def _script_language(script: Script, overrides: dict[str, str], default: str = "python") -> str:
    # explicit CLI conversion options win over the hat comment
    override = overrides.get(script.target.name)
    if override:
        return _normalize_lang(override)
    declared = script.declared_language()
    if declared:
        return _normalize_lang(declared)
    return default


def _route_fields(project: Project, script: Script) -> dict[str, str]:
    """The hat-block fields the runtime needs to route this script to an event."""
    hat = script.hat
    fields: dict[str, str] = {}
    opcode = hat.opcode
    if opcode == "event_whenkeypressed":
        fields["KEY_OPTION"] = hat.field("KEY_OPTION", "space")
    elif opcode == "event_whenbroadcastreceived":
        raw = hat.field("BROADCAST_OPTION", "")
        fields["BROADCAST_OPTION"] = project.broadcast_name(raw)
    elif opcode == "event_whenbackdroptoggles":
        raw = hat.field("BACKDROP", "")
        costume = project.stage.costume_by_ref(raw)
        fields["BACKDROP"] = costume.name if costume else raw
    elif opcode == "event_whengreaterthan":
        fields["WHENGREATERTHANOPERATOR"] = hat.field("WHENGREATERTHANOPERATOR", "loudness")
        value = hat.inputs.get("WHENGREATERTHANVALUE")
        if isinstance(value, Literal):
            fields["WHENGREATERTHANVALUE"] = value.as_text()
        else:
            fields["WHENGREATERTHANVALUE"] = hat.field("WHENGREATERTHANVALUE", "100")
    return fields


@dataclass(frozen=True)
class CostumeAsset:
    """Where a costume's bytes land plus the geometry the runtime should use.

    Anchors are in surface-pixel space with a matching resolution, so every
    runtime computes the same stage-unit center and display size; rasterized
    SVGs scale both together.
    """

    filename: str
    cx: float
    cy: float
    resolution: float


@dataclass
class AssetPlan:
    """The assets a conversion emits and how each costume maps onto them."""

    files: list[OutputFile] = field(default_factory=list)
    costumes: dict[tuple[str, str], CostumeAsset] = field(default_factory=dict)

    def costume(self, target: Target, costume: Costume) -> CostumeAsset:
        entry = self.costumes.get((target.name, costume.name))
        if entry is None:
            return CostumeAsset(
                filename=costume.asset.filename,
                cx=costume.rotation_center_x,
                cy=costume.rotation_center_y,
                resolution=costume.bitmap_resolution,
            )
        return entry


def _plan_assets(
    project: Project,
    assets: dict[str, bytes],
    warn,
    *,
    svg_policy: str = "passthrough",
) -> AssetPlan:
    """Collect output files and per-costume mappings, applying the SVG policy.

    - ``passthrough``: keep .svg files untouched (the browser renders them).
    - ``rasterize``: every SVG becomes a PNG (bitmap runtimes need pixels).
    - ``rasterize_complex``: only SVGs using features the C runtime cannot
      draw become PNGs; simple ones stay vector.

    Rasterized costumes get their geometry multiplied by ``RASTER_ZOOM`` so
    display sizes and anchors match the original vector.
    """
    plan = AssetPlan()
    emitted: dict[str, str] = {}
    out_bytes: dict[str, bytes] = {}
    zoomed: set[str] = set()

    for target in project.targets:
        for costume in target.costumes:
            original = costume.asset.filename
            if original in emitted:
                continue
            emitted[original] = original
            data = assets.get(original)
            if data is None:
                warn(f"asset {original} for costume {costume.name!r} is missing from the archive")
                continue
            out_bytes[original] = data
            if costume.asset.data_format != "svg" or svg_policy == "passthrough":
                continue
            if (
                svg_policy == "rasterize_complex"
                and not is_complex(data)
                and not has_zero_extent(data)
            ):
                continue
            png = rasterize(data)
            if png is None:
                runtime_name = "pygame" if svg_policy == "rasterize" else "SDL"
                warn(
                    f"costume {costume.name!r}: SVG could not be rasterized; kept as .svg "
                    f"(the {runtime_name} runtime cannot draw it)"
                )
                continue
            emitted[original] = f"{costume.asset.asset_id}.png"
            out_bytes[original] = png
            zoomed.add(original)

    for original, filename in emitted.items():
        data = out_bytes.get(original)
        if data is not None:
            plan.files.append(OutputFile(path=f"assets/{filename}", content=data, mode="wb"))

    for target in project.targets:
        for costume in target.costumes:
            original = costume.asset.filename
            cx = costume.rotation_center_x
            cy = costume.rotation_center_y
            resolution = costume.bitmap_resolution
            if original in zoomed:
                cx *= RASTER_ZOOM
                cy *= RASTER_ZOOM
                resolution *= RASTER_ZOOM
            plan.costumes[(target.name, costume.name)] = CostumeAsset(
                filename=emitted[original], cx=cx, cy=cy, resolution=resolution
            )

    seen: set[str] = set()
    for target in project.targets:
        for sound in target.sounds:
            filename = sound.asset.filename
            if filename in seen:
                continue
            seen.add(filename)
            data = assets.get(filename)
            if data is None:
                warn(f"asset {filename} for sound {sound.name!r} is missing from the archive")
                continue
            plan.files.append(OutputFile(path=f"assets/{filename}", content=data, mode="wb"))
    return plan


def _costume_manifest(target: Target, costume: Costume, plan: AssetPlan) -> dict:
    entry = plan.costume(target, costume)
    return {
        "name": costume.name,
        "id": costume.costume_id,
        "file": entry.filename,
        "cx": entry.cx,
        "cy": entry.cy,
        "resolution": entry.resolution,
    }


def _target_manifest(target: Target, plan: AssetPlan) -> dict:
    data: dict = {
        "name": target.name,
        "variables": dict(target.variables.values()),
        "lists": dict(target.lists.values()),
        "currentCostume": target.current_costume,
        "volume": target.volume,
        "layerOrder": target.layer_order,
        "costumes": [_costume_manifest(target, costume, plan) for costume in target.costumes],
        "sounds": [
            {"name": sound.name, "file": sound.asset.filename} for sound in target.sounds
        ],
    }
    if not target.is_stage:
        data.update(
            x=target.x,
            y=target.y,
            direction=target.direction,
            size=target.size,
            visible=target.visible,
            rotationStyle=target.rotation_style,
        )
    return data


def _manifest(project: Project, options: dict, plan: AssetPlan) -> dict:
    return {
        "name": str(options.get("name") or "Scratch project"),
        "assetDir": "assets",
        "scale": int(options.get("scale", 2)),
        "fps": int(options.get("fps", 30)),
        "stage": _target_manifest(project.stage, plan),
        "sprites": [_target_manifest(target, plan) for target in project.sprites],
        "monitors": [
            {
                "id": monitor.monitor_id,
                "label": monitor.label,
                "target": monitor.target_name,
                "isList": monitor.is_list,
                "x": monitor.x,
                "y": monitor.y,
                "mode": monitor.mode,
                "visible": monitor.visible,
                "value": monitor.value,
            }
            for monitor in project.monitors
        ],
    }


def _main_source(functions: list[str], regs: list[tuple[str, str, dict, str]]) -> str:
    helpers = ",\n    ".join(_runtime_helper_names())
    lines = [
        '"""Converted from Scratch by sb3conv. Run with: python main.py"""',
        "# ruff: noqa",
        "",
        "from runtime import (",
        "    ScriptReg,",
        "    run_cli,",
        f"    {helpers},",
        ")",
        "",
    ]
    for source in functions:
        lines.append(source)
        lines.append("")
        lines.append("")
    lines.append("SCRIPTS = [")
    for sprite, hat, fields, fn_name in regs:
        fields_json = json.dumps(fields, ensure_ascii=False)
        lines.append(f"    ScriptReg({sprite!r}, {hat!r}, {fields_json}, {fn_name}),")
    lines.append("]")
    lines.append("")
    lines.append('if __name__ == "__main__":')
    lines.append("    raise SystemExit(run_cli(SCRIPTS))")
    lines.append("")
    return "\n".join(lines)


def _check(source: str, label: str) -> None:
    try:
        compile(source, label, "exec")
    except SyntaxError as exc:
        raise BackendError(f"generated {label} is not valid Python: {exc}") from exc


def emit_python(project: Project, options: dict) -> EmitResult:
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

    for index, script in enumerate(project.all_scripts()):
        procedure = proc_script.get(script.script_id)
        is_definition = script.hat.opcode == "procedures_definition"
        language = _script_language(script, overrides)
        script_languages[script.script_id] = language
        if not is_definition and language != "python":
            warn(
                f"script at {script.target.name}:{round(script.hat.y)} is tagged "
                f"{language!r}; the python backend skipped it"
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

    main_source = _main_source(functions, regs)
    runtime_source = RUNTIME_SOURCE.read_text(encoding="utf-8")
    plan = _plan_assets(project, assets, warn, svg_policy="rasterize")
    manifest_source = json.dumps(_manifest(project, options, plan), indent=2, ensure_ascii=False)
    _check(main_source, "main.py")
    _check(runtime_source, "runtime.py")

    files = [
        OutputFile(path="main.py", content=main_source),
        OutputFile(path="runtime.py", content=runtime_source),
        OutputFile(path="sb3_manifest.json", content=manifest_source),
        *plan.files,
    ]
    return EmitResult(
        files=files,
        warnings=warnings,
        entrypoint="main.py",
        script_languages=script_languages,
    )


SPEC = BackendSpec(
    name="python",
    label="Python (pygame)",
    file_extension=".py",
    emitter=emit_python,
)
