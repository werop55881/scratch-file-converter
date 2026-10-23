"""Backend contract: shared types plus the registry every language plugs into."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from sb3conv.errors import BackendError

if TYPE_CHECKING:
    from sb3conv.sb3.model import Project


# every emitter phrases untranslated blocks the same two ways
_UNSUPPORTED_RE = re.compile(
    r"^unsupported (?:reporter|block) '(\w+)' in script at (.+?)(?: - replaced with a no-op)?$"
)


class WarningSink:
    """Collects conversion warnings and tallies unsupported Scratch blocks.

    Emitters report untranslated blocks through the shared ``warn`` callable;
    the sink keeps those lines verbatim for the user and also records the
    structured ``(opcode, location)`` pairs so convert() can write an
    ``unsupported.txt`` report next to the generated project.
    """

    def __init__(self) -> None:
        self.warnings: list[str] = []
        self.unsupported: list[tuple[str, str]] = []

    def __call__(self, message: str) -> None:
        self.warnings.append(message)
        match = _UNSUPPORTED_RE.match(message)
        if match is not None:
            self.unsupported.append((match.group(1), match.group(2).strip()))


@dataclass
class OutputFile:
    """One file a backend wants written to the output directory."""

    path: str
    content: str | bytes
    mode: str = "w"
    encoding: str = "utf-8"


@dataclass
class EmitResult:
    """Everything a backend produced for a project."""

    files: list[OutputFile] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    # (opcode, "Sprite (script at y)") for every block that became a no-op
    unsupported: list[tuple[str, str]] = field(default_factory=list)
    entrypoint: str = "main.py"
    # language tags assigned per script (used by the mixed-language feature)
    script_languages: dict[str, str] = field(default_factory=dict)


Emitter = Callable[["Project", dict], EmitResult]


@dataclass(frozen=True)
class BackendSpec:
    """Metadata describing one target language."""

    name: str
    label: str
    file_extension: str
    emitter: Emitter

    def emit(self, project: Project, options: dict | None = None) -> EmitResult:
        return self.emitter(project, options or {})


_REGISTRY: dict[str, BackendSpec] = {}
_ALIASES = {
    "py": "python",
    "js": "javascript",
    "cc": "c",
    "ts": "typescript",
    "love": "lua",
    "gd": "godot",
    "gdscript": "godot",
}
DEFAULT_LANGUAGE = "python"


def register(spec: BackendSpec) -> BackendSpec:
    _REGISTRY[spec.name] = spec
    return spec


def get_backend(name: str | None) -> BackendSpec:
    key = (name or DEFAULT_LANGUAGE).lower()
    key = _ALIASES.get(key, key)
    if key not in _REGISTRY:
        known = ", ".join(sorted(_REGISTRY)) or "<none registered>"
        raise BackendError(f"unknown language {name!r}; available: {known}")
    return _REGISTRY[key]


def available_languages() -> list[str]:
    return sorted(_REGISTRY)
