"""Disk cache for per-episode results under <root>/.analysis/<show>/<episode>.json"""

from __future__ import annotations
import json
from pathlib import Path
from typing import Any


def cache_path(root: Path, show_name: str, episode_stem: str) -> Path:
    return root / ".analysis" / show_name / f"{episode_stem}.json"


def load_cached(root: Path, show_name: str, episode_stem: str) -> dict[str, Any] | None:
    p = cache_path(root, show_name, episode_stem)
    if p.exists():
        with p.open() as fh:
            return json.load(fh)
    return None


def save_cache(root: Path, show_name: str, episode_stem: str, data: dict[str, Any]) -> None:
    p = cache_path(root, show_name, episode_stem)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w") as fh:
        json.dump(data, fh, indent=2)
