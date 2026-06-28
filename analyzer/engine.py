"""
Analysis engine — coordinates metric computation for a single episode.

Stages (reported via progress_cb):
  0.00–0.05  duration probe
  0.05–0.55  cut detection (PySceneDetect, most expensive)
  0.55–0.88  frame sampling (color / motion / flashing)
  0.88–0.96  audio extraction & loudness (FFmpeg)
  0.96–1.00  sensory-load composite + return
"""

from __future__ import annotations
import threading
import time
from pathlib import Path
from typing import Any, Callable

import cv2

from .config_loader import load_config
from .metrics_audio import compute_audio_metrics
from .metrics_cuts import compute_cut_metrics
from .metrics_frames import compute_frame_metrics
from .metrics_sensory import compute_sensory_load
from .schema import EpisodeMetrics, EpisodeResult


def _get_duration(video_path: Path) -> float:
    cap = cv2.VideoCapture(str(video_path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 1.0
    frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
    cap.release()
    return frame_count / fps


def analyze_episode(
    video_path: Path | str,
    config: dict[str, Any] | None = None,
    progress_cb: Callable[[float], None] | None = None,
    frame_cb: Callable | None = None,
) -> EpisodeResult:
    """
    Analyze a single episode and return an EpisodeResult.

    Args:
        video_path: Path to the MP4 file.
        config: Config dict (loaded from config.json if None).
        progress_cb: Optional callback(fraction: float) called during analysis.
        frame_cb: Optional callback(frame, sat, motion, luminance, is_flash) for
                  each sampled frame — used by the live analysis viewer.

    Returns:
        EpisodeResult with all real metric values.
    """
    video_path = Path(video_path)
    cfg = config or load_config()

    if not video_path.exists():
        return EpisodeResult(
            file=video_path.name,
            status="failed",
            error=f"File not found: {video_path}",
            config=cfg,
        )

    try:
        # Stage 1: duration probe
        if progress_cb:
            progress_cb(0.02)
        duration_sec = _get_duration(video_path)

        # Stage 2: cut detection (PySceneDetect has no progress callback, so we
        # trickle the bar forward on a side thread so the UI doesn't appear frozen)
        if progress_cb:
            progress_cb(0.05)

        _cut_done = threading.Event()
        if progress_cb:
            _t0 = time.time()
            # Conservative estimate keeps the bar well below 55% so it never
            # overshoots before detection finishes — the snap to 0.55 will be small.
            _est_sec = max(5.0, duration_sec / 10.0)

            def _trickle() -> None:
                while not _cut_done.wait(timeout=0.35):
                    frac = min(0.90, (time.time() - _t0) / _est_sec)
                    progress_cb(0.05 + frac * 0.48)

            threading.Thread(target=_trickle, daemon=True).start()

        shot_metrics, pacing_metrics = compute_cut_metrics(
            video_path,
            threshold=cfg["cut_detection_threshold"],
            duration_sec=duration_sec,
        )
        _cut_done.set()

        # Stage 3: frame sampling (color / motion / flashing)
        if progress_cb:
            progress_cb(0.55)

        def _frame_progress(frac: float) -> None:
            if progress_cb:
                progress_cb(0.55 + frac * 0.33)

        color_metrics, motion_metrics, flashing_metrics = compute_frame_metrics(
            video_path,
            sample_fps=cfg["sample_fps"],
            flashing_threshold=cfg["flashing_luminance_threshold"],
            duration_sec=duration_sec,
            progress_cb=_frame_progress,
            frame_cb=frame_cb,
        )

        # Stage 4: audio
        if progress_cb:
            progress_cb(0.88)
        audio_metrics = compute_audio_metrics(video_path)

        # Stage 5: composite
        if progress_cb:
            progress_cb(0.96)
        sensory_metrics = compute_sensory_load(
            pacing_metrics, color_metrics, motion_metrics,
            flashing_metrics, audio_metrics, cfg,
        )

    except Exception as exc:
        return EpisodeResult(
            file=video_path.name,
            status="failed",
            error=str(exc),
            config=cfg,
        )

    if progress_cb:
        progress_cb(1.0)

    return EpisodeResult(
        file=video_path.name,
        duration_sec=round(duration_sec, 2),
        metrics=EpisodeMetrics(
            shot_length=shot_metrics,
            scene_pacing=pacing_metrics,
            color_saturation=color_metrics,
            motion=motion_metrics,
            flashing=flashing_metrics,
            audio=audio_metrics,
            sensory_load=sensory_metrics,
        ),
        config=cfg,
    )
