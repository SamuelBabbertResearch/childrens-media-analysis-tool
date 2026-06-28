"""
Resolves ffmpeg/ffprobe executables — bundled copy first, PATH fallback.

Search order:
  1. Next to the exe (PyInstaller frozen build, _internal/)
  2. Project root (running from source with local copies)
  3. System PATH (user has FFmpeg installed globally)
"""
from __future__ import annotations
import sys
from pathlib import Path


def _find(name: str) -> str:
    candidates: list[Path] = []

    if getattr(sys, "frozen", False):
        # PyInstaller --onedir: binaries land in _internal/ (sys._MEIPASS)
        candidates.append(Path(sys._MEIPASS) / name)          # type: ignore[attr-defined]
        # Also check next to the exe for manually placed copies
        candidates.append(Path(sys.executable).parent / name)
    else:
        # Running from source: check project root
        candidates.append(Path(__file__).parent.parent / name)

    for c in candidates:
        if c.exists():
            return str(c)

    return name  # fall back to PATH


def ffmpeg_exe() -> str:
    return _find("ffmpeg.exe")
