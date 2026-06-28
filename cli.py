"""
Command-line interface for the Children's TV Sensory-Load Analyzer.

Usage:
    python cli.py analyze <file.mp4>            # analyze one episode
    python cli.py analyze <show_folder/>        # batch analyze all episodes + aggregate
    python cli.py shows <root_folder/>          # list all shows under root
    python cli.py db episodes <root_folder/>    # print episode index table
    python cli.py db shows <root_folder/>       # print show index table
"""

from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

from analyzer.aggregate import compute_show_aggregate, save_show_results
from analyzer.batch import analyze_show_batch
from analyzer.cache import load_cached, save_cache
from analyzer.config_loader import load_config
from analyzer.db import get_db, query_episodes, query_shows
from analyzer.engine import analyze_episode
from analyzer.show_index import list_episodes, list_shows


def cmd_analyze(args: argparse.Namespace) -> None:
    target = Path(args.path)
    cfg = load_config()

    if target.is_file() and target.suffix.lower() == ".mp4":
        _analyze_single(target, cfg, force=args.force)
    elif target.is_dir():
        _analyze_batch(target, cfg, force=args.force)
    else:
        print(f"Error: {target} is not an MP4 file or a directory.", file=sys.stderr)
        sys.exit(1)


# ---------------------------------------------------------------------------
# Single episode
# ---------------------------------------------------------------------------

def _analyze_single(episode: Path, cfg: dict, force: bool = False) -> None:
    show_dir = episode.parent
    root = show_dir.parent

    cached = None if force else load_cached(root, show_dir.name, episode.stem)
    if cached:
        print(f"[cache] {episode.name}")
        print(json.dumps(cached, indent=2))
        return

    def _progress(frac: float) -> None:
        filled = int(frac * 30)
        bar = "#" * filled + "-" * (30 - filled)
        print(f"\r  [{bar}] {int(frac * 100):3d}%", end="", flush=True)

    print(f"Analyzing {episode.name} ...")
    result = analyze_episode(episode, config=cfg, progress_cb=_progress)
    print()

    save_cache(root, show_dir.name, episode.stem, result.to_dict())

    if result.status == "failed":
        print(f"Error: {result.error}", file=sys.stderr)
        sys.exit(1)

    print(result.to_json())


# ---------------------------------------------------------------------------
# Batch (show folder)
# ---------------------------------------------------------------------------

def _analyze_batch(show_dir: Path, cfg: dict, force: bool = False) -> None:
    root = show_dir.parent
    episodes = list_episodes(show_dir)

    if not episodes:
        print(f"No MP4 files found in {show_dir}")
        return

    print(f"Show: {show_dir.name}  ({len(episodes)} episode(s))\n")

    current_ep: list[str] = [""]

    def _progress(ep_name: str, ep_frac: float, overall_frac: float) -> None:
        if ep_name != current_ep[0]:
            if current_ep[0]:
                print()  # newline after previous episode's bar
            current_ep[0] = ep_name
            print(f"  {ep_name}")
        filled = int(ep_frac * 30)
        bar = "#" * filled + "-" * (30 - filled)
        print(f"\r    [{bar}] {int(ep_frac * 100):3d}%  (overall {int(overall_frac * 100):3d}%)",
              end="", flush=True)

    results = analyze_show_batch(
        show_dir, root=root, config=cfg, force=force, progress_cb=_progress
    )
    print("\n")

    # Summary table
    ok = [r for r in results if r.status == "ok"]
    failed = [r for r in results if r.status == "failed"]

    print(f"{'Episode':<30} {'Duration':>10} {'Cuts/min':>10} {'Saturation':>12} "
          f"{'Motion':>8} {'Flash/min':>10} {'Load':>6}")
    print("-" * 92)
    for r in results:
        if r.status == "failed":
            print(f"  {r.file:<28} {'FAILED':>10}  {r.error[:40]}")
        else:
            m = r.metrics
            print(
                f"  {r.file:<28} {r.duration_sec:>9.0f}s "
                f"{m.scene_pacing.cuts_per_min:>10.1f} "
                f"{m.color_saturation.mean:>12.3f} "
                f"{m.motion.mean:>8.3f} "
                f"{m.flashing.luminance_delta_events_per_min:>10.1f} "
                f"{m.sensory_load.score:>6.3f}"
            )

    print()

    if not ok:
        print("All episodes failed — no aggregate computed.", file=sys.stderr)
        sys.exit(1)

    if failed:
        print(f"Warning: {len(failed)} episode(s) failed and were excluded from aggregate.\n")

    aggregate = compute_show_aggregate(show_dir.name, results)
    json_path, csv_path = save_show_results(root, show_dir.name, results, aggregate)

    print("Show aggregate:")
    print(aggregate.to_json())
    print(f"\nSaved: {json_path.relative_to(root)}")
    print(f"       {csv_path.relative_to(root)}")


# ---------------------------------------------------------------------------
# Shows listing
# ---------------------------------------------------------------------------

def cmd_shows(args: argparse.Namespace) -> None:
    root = Path(args.root)
    if not root.is_dir():
        print(f"Error: {root} is not a directory.", file=sys.stderr)
        sys.exit(1)

    shows = list_shows(root)
    if not shows:
        print("No show folders found (folders containing .mp4 files).")
        return

    print(f"Root: {root}")
    for show in shows:
        eps = list_episodes(show)
        print(f"  {show.name}/  — {len(eps)} episode(s)")
        for ep in eps:
            print(f"    {ep.name}")


# ---------------------------------------------------------------------------
# DB index queries
# ---------------------------------------------------------------------------

def _db_backfill(root: Path) -> None:
    """Seed the index DB from all cached episode JSONs — mirrors what the GUI does on folder open."""
    from analyzer.aggregate import compute_show_aggregate
    from analyzer.cache import load_cached
    from analyzer.db import get_db, upsert_episode, upsert_show
    from analyzer.schema import EpisodeResult

    conn = get_db(root)
    for show_dir in list_shows(root):
        show_results = []
        for ep in list_episodes(show_dir):
            c = load_cached(root, show_dir.name, ep.stem)
            if c:
                try:
                    result = EpisodeResult.from_dict(c)
                    if result.status == "ok":
                        upsert_episode(conn, result, show_dir.name, str(ep))
                        show_results.append(result)
                except Exception:
                    pass
        if show_results:
            try:
                agg = compute_show_aggregate(show_dir.name, show_results)
                upsert_show(conn, agg, show_dir.name)
            except Exception:
                pass
    conn.close()


def cmd_db(args: argparse.Namespace) -> None:
    root = Path(args.root)
    if not root.is_dir():
        print(f"Error: {root} is not a directory.", file=sys.stderr)
        sys.exit(1)

    # Reconfigure stdout to UTF-8 so filenames with emoji/non-ASCII print safely
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

    _db_backfill(root)   # ensure index is up to date before querying
    conn = get_db(root)
    sort_by = args.sort or ("analyzed_at" if args.table == "episodes" else "avg_load")
    ascending = not args.desc

    if args.table == "episodes":
        rows = query_episodes(conn, sort_by=sort_by, ascending=ascending,
                              filter_show=args.show or "")
        if not rows:
            print("No episodes in index.  Run 'analyze' first, or choose the root folder in the GUI.")
            return
        hdr = f"{'Show':<22} {'File':<28} {'C/min':>6} {'Sat':>5} {'Mot':>5} {'RMS':>7} {'Load':>6}  {'Date'}"
        print(hdr)
        print("-" * len(hdr))
        for r in rows:
            cpm  = f"{r['cuts_per_min']:.1f}"          if r["cuts_per_min"]           is not None else "—"
            sat  = f"{r['color_saturation_mean']:.3f}" if r["color_saturation_mean"]  is not None else "—"
            mot  = f"{r['motion_mean']:.3f}"            if r["motion_mean"]            is not None else "—"
            rms  = f"{r['audio_rms_mean']:.4f}"         if r["audio_rms_mean"]         is not None else "n/a"
            load = f"{r['sensory_load_score']:.3f}"     if r["sensory_load_score"]     is not None else "—"
            date = (r["analyzed_at"] or "")[:16]
            print(f"  {r['show_name']:<20} {r['file_name']:<28} "
                  f"{cpm:>6} {sat:>5} {mot:>5} {rms:>7} {load:>6}  {date}")

    elif args.table == "shows":
        rows = query_shows(conn, sort_by=sort_by, ascending=ascending)
        if not rows:
            print("No shows in index.  Run 'analyze' on a show folder first.")
            return
        hdr = f"{'Show':<30} {'Eps':>4} {'Avg Load':>9} {'Avg C/min':>10} {'Avg Mot':>8} {'Avg Sat':>8}"
        print(hdr)
        print("-" * len(hdr))
        for r in rows:
            load = f"{r['avg_load']:.3f}"         if r["avg_load"]         is not None else "—"
            cpm  = f"{r['avg_cuts_per_min']:.1f}" if r["avg_cuts_per_min"] is not None else "—"
            mot  = f"{r['avg_motion']:.3f}"        if r["avg_motion"]       is not None else "—"
            sat  = f"{r['avg_saturation']:.3f}"    if r["avg_saturation"]   is not None else "—"
            print(f"  {r['show_name']:<28} {r['episode_count']:>4} "
                  f"{load:>9} {cpm:>10} {mot:>8} {sat:>8}")


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Children's TV Sensory-Load Analyzer",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_analyze = sub.add_parser(
        "analyze", help="Analyze an episode (MP4) or all episodes in a show folder"
    )
    p_analyze.add_argument("path", help="Path to an MP4 file or a show folder")
    p_analyze.add_argument("--force", action="store_true", help="Re-analyze even if cached")
    p_analyze.set_defaults(func=cmd_analyze)

    p_shows = sub.add_parser("shows", help="List all shows under a root folder")
    p_shows.add_argument("root", help="Root folder containing show sub-folders")
    p_shows.set_defaults(func=cmd_shows)

    p_db = sub.add_parser("db", help="Query the persistent index database")
    db_sub = p_db.add_subparsers(dest="table", required=True)

    p_db_ep = db_sub.add_parser("episodes", help="List all indexed episodes")
    p_db_ep.add_argument("root", help="Root folder (where .analysis/index.db lives)")
    p_db_ep.add_argument("--show",  default="", help="Filter by show name substring")
    p_db_ep.add_argument("--sort",  default="", help="Sort column (e.g. sensory_load_score)")
    p_db_ep.add_argument("--desc",  action="store_true", help="Sort descending")
    p_db_ep.set_defaults(func=cmd_db)

    p_db_sh = db_sub.add_parser("shows", help="List all indexed shows")
    p_db_sh.add_argument("root", help="Root folder (where .analysis/index.db lives)")
    p_db_sh.add_argument("--sort",  default="", help="Sort column (e.g. avg_load)")
    p_db_sh.add_argument("--desc",  action="store_true", help="Sort descending")
    p_db_sh.set_defaults(func=cmd_db)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
