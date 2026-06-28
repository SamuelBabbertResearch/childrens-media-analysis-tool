"""Discovers shows (folders) and episodes (MP4 files) under a root directory."""

from __future__ import annotations
from pathlib import Path


def list_shows(root: Path) -> list[Path]:
    """Return subdirectories of *root* that contain at least one MP4 file."""
    return sorted(
        d for d in root.iterdir()
        if d.is_dir() and not d.name.startswith(".") and any(d.glob("*.mp4"))
    )


def list_episodes(show_dir: Path) -> list[Path]:
    """Return MP4 files inside *show_dir*, sorted by name."""
    return sorted(show_dir.glob("*.mp4"))
