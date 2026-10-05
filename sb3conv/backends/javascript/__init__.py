"""JavaScript (browser) backend: emit a self-contained web app.

Output layout::

    <out>/index.html         page with the stage canvas; loads runtime.js + main.js
    <out>/runtime.js         copy of runtime_src.js (canvas + Web Audio only)
    <out>/main.js            generated scripts, inlined MANIFEST, SCRIPTS registration
    <out>/sb3_manifest.json  stage/sprite/monitor description (also inlined in main.js)
    <out>/assets/*           costumes and sounds extracted from the .sb3
"""

from __future__ import annotations

import html
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from sb3conv.backends.base import BackendSpec, EmitResult, OutputFile
from sb3conv.backends.javascript.exprs import js_str
from sb3conv.backends.javascript.stmts import StatementEmitter
from sb3conv.backends.python import _manifest, _plan_assets, _route_fields, _script_language
from sb3conv.errors import BackendError
from sb3conv.sb3.model import Project
from sb3conv.sb3.procedures import find_procedures, procedure_by_script, procedure_map

RUNTIME_SOURCE = Path(__file__).with_name("runtime_src.js")


def _main_source(functions: list[str], regs: list[tuple[str, str, dict, str]], manifest_json: str) -> str:
    lines = [
        "// Converted from Scratch by sb3conv. Open index.html in a browser.",
        "",
        f"const MANIFEST = {manifest_json};",
        "",
    ]
    for source in functions:
        lines.append(source)
        lines.append("")
    lines.append("const SCRIPTS = [")
    for sprite, hat, fields, fn_name in regs:
        fields_json = json.dumps(fields, ensure_ascii=False)
        lines.append(
            f"  new ScriptReg({js_str(sprite)}, {js_str(hat)}, {fields_json}, {fn_name}),"
        )
    lines.append("];")
    lines.append("")
    lines.append("run(SCRIPTS, MANIFEST);")
    lines.append("")
    return "\n".join(lines)


def _index_source(name: str) -> str:
    title = html.escape(name)
    return (
        "<!doctype html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{title}</title>\n"
        "<style>\n"
        "  html, body { margin: 0; height: 100%; background: #000; }\n"
        "  body { display: flex; align-items: center; justify-content: center; }\n"
        "</style>\n"
        "</head>\n"
        "<body>\n"
        '<canvas id="stage"></canvas>\n'
        '<script src="runtime.js"></script>\n'
        '<script src="main.js"></script>\n'
        "</body>\n"
        "</html>\n"
    )


def _check_js(sources: dict[str, str]) -> None:
    """Syntax-check generated JavaScript with ``node --check`` when node exists."""
    node = shutil.which("node")
    if not node:
        return
    with tempfile.TemporaryDirectory(prefix="sb3conv-js-") as tmp:
        for name, source in sources.items():
            path = Path(tmp) / name
            path.write_text(source, encoding="utf-8")
            proc = subprocess.run(
                [node, "--check", str(path)],
                capture_output=True,
                text=True,
                check=False,
            )
            if proc.returncode != 0:
                detail = (proc.stderr or proc.stdout).strip()
                raise BackendError(f"generated {name} is not valid JavaScript:\n{detail}")


def emit_javascript(project: Project, options: dict) -> EmitResult:
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
        language = _script_language(script, overrides, default="javascript")
        script_languages[script.script_id] = language
        if not is_definition and language != "javascript":
            warn(
                f"script at {script.target.name}:{round(script.hat.y)} is tagged "
                f"{language!r}; the javascript backend skipped it"
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

    plan = _plan_assets(project, assets, warn, svg_policy="passthrough")
    manifest_obj = _manifest(project, options, plan)
    manifest_json = json.dumps(manifest_obj, indent=2, ensure_ascii=False)
    main_source = _main_source(functions, regs, manifest_json)
    runtime_source = RUNTIME_SOURCE.read_text(encoding="utf-8")
    index_source = _index_source(str(manifest_obj["name"]))
    _check_js({"runtime.js": runtime_source, "main.js": main_source})

    files = [
        OutputFile(path="index.html", content=index_source),
        OutputFile(path="main.js", content=main_source),
        OutputFile(path="runtime.js", content=runtime_source),
        OutputFile(path="sb3_manifest.json", content=manifest_json),
        *plan.files,
    ]
    return EmitResult(
        files=files,
        warnings=warnings,
        entrypoint="index.html",
        script_languages=script_languages,
    )


SPEC = BackendSpec(
    name="javascript",
    label="JavaScript (browser)",
    file_extension=".js",
    emitter=emit_javascript,
)
