"""PyInstaller entry point for the sb3conv desktop app."""

from __future__ import annotations

from sb3conv.gui import main

if __name__ == "__main__":
    raise SystemExit(main())
