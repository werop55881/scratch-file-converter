"""Custom block (procedure) discovery shared by every backend.

A ``procedures_definition`` hat points at a ``procedures_prototype`` block that
carries the proccode, argument ids and argument names in its mutation. Calls
(``procedures_call``) reference the same proccode, so each backend can resolve
a call to the emitted function through :func:`procedure_map`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from sb3conv.sb3.model import BlockRef, Project, Script, Target


def _json_list(text: str) -> list[str]:
    try:
        value = json.loads(text or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


@dataclass
class Procedure:
    """One custom block definition."""

    script: Script
    target: Target
    proccode: str
    argumentids: list[str]
    params: dict[str, str] = field(default_factory=dict)  # argument name -> identifier
    fn_name: str = ""

    @property
    def param_list(self) -> list[str]:
        """Parameter identifiers in argument order (for the function signature)."""
        return [f"_a{index}" for index in range(len(self.argumentids))]


def find_procedures(project: Project) -> list[Procedure]:
    """Every well-formed definition in the project, in script order."""
    procedures: list[Procedure] = []
    for script in project.all_scripts():
        if script.hat.opcode != "procedures_definition":
            continue
        ref = script.hat.inputs.get("custom_block")
        prototype = script.target.blocks.get(ref.block_id) if isinstance(ref, BlockRef) else None
        if prototype is None or prototype.opcode != "procedures_prototype":
            continue  # emit_function warns about definitions without a prototype
        argumentids = _json_list(prototype.mutation.get("argumentids", ""))
        argumentnames = _json_list(prototype.mutation.get("argumentnames", ""))
        names = (argumentnames + [""] * len(argumentids))[: len(argumentids)]
        params = {name: f"_a{index}" for index, name in enumerate(names)}
        procedures.append(
            Procedure(
                script=script,
                target=script.target,
                proccode=prototype.mutation.get("proccode", ""),
                argumentids=argumentids,
                params=params,
                fn_name=f"proc_{len(procedures)}",
            )
        )
    return procedures


def procedure_map(procedures: list[Procedure]) -> dict[tuple[str, str], Procedure]:
    """(target name, proccode) -> definition, for resolving call sites."""
    mapping: dict[tuple[str, str], Procedure] = {}
    for procedure in procedures:
        mapping.setdefault((procedure.target.name, procedure.proccode), procedure)
    return mapping


def procedure_by_script(procedures: list[Procedure]) -> dict[str, Procedure]:
    """script id -> definition, so emit loops can find a script's own procedure."""
    return {procedure.script.script_id: procedure for procedure in procedures}
