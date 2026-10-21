"""TypeScript backend: the JavaScript emit as ``.ts`` sources plus a tsconfig.

Output layout::

    <out>/index.html         page with the stage canvas; loads runtime.js + main.js
    <out>/runtime.ts         the JS runtime, prefixed with @ts-nocheck
    <out>/main.ts            generated scripts, inlined MANIFEST, SCRIPTS registration
    <out>/tsconfig.json      loose settings (strict: false); tsc emits runtime.js + main.js
    <out>/sb3_manifest.json  stage/sprite/monitor description (also inlined in main.ts)
    <out>/assets/*           costumes and sounds extracted from the .sb3

The generated code is the JavaScript backend's output verbatim: valid
TypeScript with implicit-any parameters, so ``tsc`` type-checks the glue
while ``@ts-nocheck`` keeps the 1600-line runtime out of the way. The build
step (``sb3conv.build_app.build_typescript_app``) runs ``tsc`` and then the
normal single-file javascript packaging.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from sb3conv.backends.base import BackendSpec, EmitResult, OutputFile
from sb3conv.backends.javascript import RUNTIME_SOURCE, _index_source, _main_source
from sb3conv.backends.javascript.stmts import StatementEmitter
from sb3conv.backends.python import _manifest, _plan_assets, _route_fields, _script_language
from sb3conv.errors import BackendError
from sb3conv.sb3.model import Project
from sb3conv.sb3.procedures import find_procedures, procedure_by_script, procedure_map

# implicit-any friendly: the generated scripts pass untyped ctx/rt around on purpose
TSCONFIG = """\
{
  "compilerOptions": {
    "target": "ES2020",
    "module": "ES2020",
    "lib": ["DOM", "ES2020"],
    "strict": false,
    "noImplicitAny": false,
    "skipLibCheck": true
  },
  "files": ["runtime.ts", "main.ts"]
}
"""

# scripts tagged javascript/js convert under the typescript backend too
_ACCEPTED = ("typescript", "javascript", "js")


def _check_ts(sources: dict[str, str]) -> None:
    """Type-check generated TypeScript with ``tsc`` when it is on PATH."""
    tsc = shutil.which("tsc")
    if not tsc:
        return
    with tempfile.TemporaryDirectory(prefix="sb3conv-ts-") as tmp:
        root = Path(tmp)
        for name, source in sources.items():
            (root / name).write_text(source, encoding="utf-8")
        (root / "tsconfig.json").write_text(TSCONFIG, encoding="utf-8")
        proc = subprocess.run(
            [tsc, "-p", str(root)], capture_output=True, text=True, check=False
        )
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout).strip()
            raise BackendError(f"generated TypeScript does not compile:\n{detail}")


def emit_typescript(project: Project, options: dict) -> EmitResult:
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
        language = _script_language(script, overrides, default="typescript")
        script_languages[script.script_id] = language
        if not is_definition and language not in _ACCEPTED:
            warn(
                f"script at {script.target.name}:{round(script.hat.y)} is tagged "
                f"{language!r}; the typescript backend skipped it"
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
    runtime_source = "// @ts-nocheck\n" + RUNTIME_SOURCE.read_text(encoding="utf-8")
    index_source = _index_source(str(manifest_obj["name"]))
    _check_ts({"runtime.ts": runtime_source, "main.ts": main_source})

    files = [
        OutputFile(path="index.html", content=index_source),
        OutputFile(path="main.ts", content=main_source),
        OutputFile(path="runtime.ts", content=runtime_source),
        OutputFile(path="tsconfig.json", content=TSCONFIG),
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
    name="typescript",
    label="TypeScript (browser)",
    file_extension=".ts",
    emitter=emit_typescript,
)
