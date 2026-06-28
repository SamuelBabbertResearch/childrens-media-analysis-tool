"""Loads and validates config.json. Returns a plain dict — no GUI dependencies."""

from __future__ import annotations
import json
import sys
from pathlib import Path
from typing import Any


def _base_dir() -> Path:
    # When frozen by PyInstaller, _MEIPASS is the unpacked bundle directory.
    # At runtime we prefer a config.json next to the .exe so users can edit weights.
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).parent
        if (exe_dir / "config.json").exists():
            return exe_dir
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).parent.parent


def load_config(path: Path | str | None = None) -> dict[str, Any]:
    """Load config from *path*, falling back to the project-root config.json."""
    resolved = Path(path) if path else _base_dir() / "config.json"
    with resolved.open() as fh:
        return json.load(fh)
