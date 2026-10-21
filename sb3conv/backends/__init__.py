"""Backend package: importing this registers every built-in language."""

from __future__ import annotations

from sb3conv.backends.base import (
    DEFAULT_LANGUAGE,
    BackendSpec,
    EmitResult,
    OutputFile,
    available_languages,
    get_backend,
    register,
)

__all__ = [
    "DEFAULT_LANGUAGE",
    "BackendSpec",
    "EmitResult",
    "OutputFile",
    "available_languages",
    "get_backend",
    "register",
]


def _load_builtin_backends() -> None:
    from sb3conv.backends import c, javascript, lua, python, typescript  # noqa: F401

    register(c.SPEC)
    register(javascript.SPEC)
    register(lua.SPEC)
    register(python.SPEC)
    register(typescript.SPEC)


_load_builtin_backends()
