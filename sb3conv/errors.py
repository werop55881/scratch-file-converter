"""Errors raised by sb3conv."""

from __future__ import annotations


class Sb3Error(Exception):
    """Base class for all converter errors."""


class ArchiveError(Sb3Error):
    """The .sb3 file could not be read as a zip archive."""


class ProjectFormatError(Sb3Error):
    """project.json is missing, malformed, or not a Scratch 3 project."""


class UnsupportedOpcodeError(Sb3Error):
    """A block opcode has no mapping in the selected backend."""

    def __init__(self, opcode: str, backend: str) -> None:
        super().__init__(f"opcode {opcode!r} is not supported by the {backend} backend")
        self.opcode = opcode
        self.backend = backend


class BackendError(Sb3Error):
    """A backend is missing or failed while emitting."""
