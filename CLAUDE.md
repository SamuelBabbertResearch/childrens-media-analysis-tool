# Children's TV Sensory-Load Analyzer — Claude Code Project Brief

This file is meant to be dropped into the project root as `CLAUDE.md` (or pasted as your
opening message to Claude Code). It sets the shared context. The numbered **phase prompts**
at the bottom are what you paste in one at a time, verifying the acceptance criteria for each
before moving on. Commit after each phase.

---

## Part 1 — Project Brief (use as CLAUDE.md)

### Goal

A desktop Windows application that analyzes MP4 episodes of children's TV shows and produces a
**sensory-load profile** for each episode and a **cumulative profile** for a whole show. The tool
measures formal/structural features of the video (pacing, color, motion). It does **not** issue a
verdict on "appropriateness" — it presents transparent, labeled metrics that a person interprets.
Every composite score must show its component parts.

### Stack (use these; do not substitute without asking)

- Language: **Python 3.11+**
- Cut / scene detection: **PySceneDetect** (use its current API for the installed version)
- Frame analysis: **OpenCV** (`opencv-python`) + **NumPy**
- Decoding backend / optional audio: **FFmpeg** (assume on PATH; document this)
- Aggregation / export: **pandas**
- GUI: **Tkinter** (standard library) — keep it plain and classic; no Qt, no web frameworks
- Charts (Phase 4 only): **matplotlib** embedded in Tk

### Architecture (non-negotiable separation)

1. A **pure analysis engine** (`analyzer/` package) with no GUI imports. Each metric is an
   isolated, independently testable function: input = video path (and config), output = numbers.
2. A **CLI** (`cli.py`) that runs the engine on one file or one folder and writes JSON/CSV.
   The GUI is a thin layer over this same engine — never duplicate analysis logic in the UI.
3. The GUI must run analysis on a **worker thread** with a progress callback so it never freezes.

### Folder / data convention

```
<root>/
  <Show Name>/
    episode01.mp4
    episode02.mp4
  <Another Show>/
    ...
```

A "show" is a folder; episodes are the MP4 files inside it. Results are **cached** to disk
(e.g. `<root>/.analysis/<show>/<episode>.json`) so reopening a show doesn't re-run analysis.

### Output schema (define in Phase 0, keep stable)

Per-episode JSON, roughly:

```json
{
  "file": "episode01.mp4",
  "duration_sec": 1320.0,
  "metrics": {
    "shot_length": {"mean_sec": 3.1, "median_sec": 2.4, "shots_per_min": 19.3, "count": 425},
    "scene_pacing": {"cuts_per_min": 19.3, "shot_length_cv": 0.82, "timeline_cuts_per_30s": [..]},
    "color_saturation": {"mean": 0.61, "temporal_var": 0.04},
    "motion": {"mean": 0.27, "peak": 0.91},
    "flashing": {"luminance_delta_events_per_min": 4.0},
    "sensory_load": {"score": 0.68, "components": {"pacing": .., "saturation": .., "motion": .., "flashing": ..}}
  },
  "config": { "...": "the config used, for reproducibility" }
}
```

Show-level aggregate: per-metric mean/median across episodes, episode-to-episode variability,
and the distribution, written to JSON + CSV.

### Metric definitions (operationalize exactly this way)

- **Shot length** — Use PySceneDetect content detection to get cut timestamps. Shot durations =
  gaps between cuts. Report mean, median, shots-per-minute, count. Shorter = faster.
- **Scene pacing** — Derived from the same cut series: cut rate (cuts/min), variability of shot
  length (coefficient of variation = std/mean), and a rolling "cuts per 30s" timeline array.
  This captures *rhythm*, distinct from raw shot length. State this distinction in code comments.
- **Color saturation** — Sample frames at 1–2 fps, convert to HSV, take the S channel mean per
  frame. Report mean and temporal variance across the episode.
- **Motion** — Default: normalized mean absolute frame difference between consecutive sampled
  frames (fast, good as a relative proxy). Make the method pluggable so dense optical flow
  (Farneback) can be swapped in later. Report mean and peak.
- **Flashing (bonus, cheap, high value)** — Count events where luminance changes between sampled
  frames exceed a threshold; report events per minute. Relevant to photosensitivity/overstimulation.
- **Sensory load** — A **transparent weighted composite** of the normalized sub-metrics
  (pacing, saturation, motion, flashing). Use **fixed, documented reference ranges** for
  normalization (min-max against documented bounds), NOT per-corpus normalization, so scores
  are comparable across separate runs. Weights live in the config file and are user-editable.
  Always output both the composite and its normalized components.

### Performance & robustness constraints

- Episodes are 11–24 min. Do NOT process every frame for color/motion — sample at a configurable
  fps (default 2). Cut detection runs on the decoded stream via PySceneDetect.
- Handle corrupt/unreadable files gracefully (log, skip, mark failed — never crash a batch).
- Show progress for batch runs (per-episode callback).
- Everything runs **fully offline / local**. No cloud, no network calls.

### Config

A single `config.json` (or `config.py` dataclass) holding: sample_fps, cut-detection threshold,
flashing threshold, sensory-load weights, and the fixed normalization reference ranges.

### Coding standards

Type hints, docstrings on each metric function, a `tests/` directory with at least one short
sample clip and unit tests asserting each metric returns plausible bounded numbers. Keep the
engine importable and GUI-free.

---

## Part 2 — Phase prompts (paste one at a time)

### Phase 0 — Scaffold & data contract
> Set up the project structure and the data contract only. Create the repo layout
> (`analyzer/`, `cli.py`, `config.json`, `tests/`), install/declare dependencies in
> `requirements.txt`, and define the per-episode and per-show output schemas as documented in
> CLAUDE.md (use dataclasses or pydantic). Implement `cli.py analyze <file.mp4>` that produces
> schema-valid JSON with **stub** metric values for now. Implement the folder model (show folder
> -> episode list) and result caching paths.
> **Acceptance:** `python cli.py analyze sample.mp4` runs and emits schema-valid JSON; running
> on a folder lists shows and episodes correctly.

### Phase 1 — Analysis engine (the hard part — validate before any GUI)
> Implement each metric in `analyzer/` as an isolated function per the operationalizations in
> CLAUDE.md: shot_length, scene_pacing, color_saturation, motion, flashing, and the sensory_load
> composite. Respect the sampling-fps constraint. Wire real values into `cli.py`. Add unit tests
> in `tests/` against a short sample clip asserting each metric returns bounded, plausible numbers.
> **Acceptance:** real JSON for one real episode; each metric independently sane (sanity-check
> against eyeballing the clip); `pytest` passes.

### Phase 2 — Batch processing & show-level aggregation
> Add a batch runner: given a show folder, analyze every episode (skipping/logging failures),
> write per-episode cached JSON, and compute a show-level aggregate (per-metric mean/median,
> episode-to-episode variability, distributions) to JSON + CSV. Use the cache so already-analyzed
> episodes aren't recomputed unless forced. Provide a progress callback hook.
> **Acceptance:** point the CLI at a show folder -> per-episode results + one cumulative
> aggregate; re-running uses cache; a deliberately corrupt file is skipped, not fatal.

### Phase 3 — Tkinter GUI (thin layer over the engine)
> Build a plain classic Tkinter window. Left pane: a tree of shows -> episodes, populated from a
> user-chosen root folder (folder picker). Buttons: "Analyze Episode" and "Analyze Show (batch)".
> Right pane: a results panel showing the metric table for the selected episode (composite score
> + its components clearly broken out), and the cumulative profile when a show is selected. Run
> all analysis on a **worker thread** with a progress bar; the UI must never freeze. Read from
> cache when present.
> **Acceptance:** full click-through on Windows — pick root, browse shows/episodes, run single,
> run batch with a live progress bar, view per-episode and cumulative results, no UI freeze.

### Phase 4 — Polish & optional extensions
> Add: CSV/JSON export buttons; a simple matplotlib chart embedded in Tk (e.g. cuts-per-30s
> timeline, or a bar chart of the sensory-load components); editable sensory-load weights in the
> UI that re-score from cached raw metrics without re-analyzing video. OPTIONAL stretch: audio
> metrics via FFmpeg (RMS loudness, dynamic range) folded into sensory_load as an additional
> weighted component — this is the single highest-value addition for children's content.
> **Acceptance:** export works; changing weights re-scores instantly from cache; (if attempted)
> audio loudness appears as a labeled component.

### Phase 5 — Persistent index database & sortable browser
> Build a persistent SQLite index (`index.db` in the root) that stores analyzed results for every
> episode and show across sessions, so the app accumulates a growing library over time regardless
> of which root folder is currently open.
>
> **Database layer** (`analyzer/db.py`, no GUI imports):
> - Use Python's built-in `sqlite3` — no ORM, no new dependencies.
> - Schema: two tables. `episodes` — one row per analyzed episode with columns for every scalar
>   metric (file path, show name, duration, shots_per_min, cuts_per_min, shot_length_cv,
>   color_saturation_mean, motion_mean, motion_peak, flashing_events_per_min, audio_rms_mean,
>   audio_dynamic_range_db, sensory_load_score, analyzed_at timestamp). `shows` — one row per
>   show with the aggregate stats (mean/median sensory load, episode count, etc.) derived from
>   its episodes table rows. Both tables use the canonical file path as primary key so
>   re-analyzing an episode upserts rather than duplicates.
> - Expose functions: `upsert_episode(result: EpisodeResult, show_name: str)`,
>   `upsert_show(aggregate: ShowAggregate, show_name: str)`,
>   `query_episodes(sort_by, ascending, filter_show) -> list[dict]`,
>   `query_shows(sort_by, ascending) -> list[dict]`,
>   `get_db(root: Path) -> sqlite3.Connection`. Wire `upsert_episode` into `engine.analyze_episode`
>   (via a post-analysis hook, not inside the engine itself) and `upsert_show` into
>   `batch.analyze_show_batch`, so every successful analysis auto-indexes.
>
> **Index Browser tab** in the GUI:
> - Add a second top-level tab (use `ttk.Notebook`) alongside the existing folder tree: "Index".
> - Inside: two sub-tabs — "All Episodes" and "All Shows".
> - Each sub-tab is a `ttk.Treeview` with sortable columns. Clicking a column header re-sorts
>   (toggle ascending/descending). Columns for episodes: Show, File, Duration, Cuts/min,
>   Saturation, Motion, Audio RMS, Sensory Load, Analyzed At. Columns for shows: Show, Episodes,
>   Avg Load, Avg Cuts/min, Avg Motion, Avg Saturation.
> - A search/filter bar at the top filters by show name substring (live, no button needed).
> - Selecting a row in the episode table and clicking "View Details" (or double-clicking) jumps
>   to that episode's cached result in the main results panel.
> - A "Refresh Index" button re-queries the DB without re-analyzing anything.
> - The browser loads on app start; it does not block the UI (run the initial DB query on a
>   worker thread if the index is large).
>
> **CLI support**: `python cli.py db episodes [--show SHOW] [--sort sensory_load_score] [--desc]`
> prints a formatted table from the index. `python cli.py db shows [--sort avg_load]` similarly.
>
> **Acceptance:** after analyzing two or more shows, the Index tab lists all episodes and shows
> across both, sortable by every column; filtering by show name narrows the list; double-clicking
> an episode row shows its cached metrics; re-analyzing an episode updates its row in place
> (upsert); the CLI `db` subcommand prints the same data; the DB persists across app restarts.

---

## Part 3 — Research grounding (metric labels + academic defensibility)

> **Framing note (read first).** Everything below is a *scaffold*. The conceptual mapping
> (metric → literature → why it matters) is sound, but pull the primary sources and confirm
> exact findings before any formal citation. Every claim here is **correlational and
> interpretive**: these are formal/structural *proxies* the literature associates with arousal
> and attentional demand, not measures of "appropriateness." The link to developmental impact
> depends on the child's age, individual sensory-processing differences, and dose. Use
> correlational language throughout; never state that a feature *causes* an outcome.

### The mechanism (one paragraph, the spine of the whole tool)

Media researchers distinguish *content* from **formal features** — the perceptually salient,
content-independent structural attributes of video: cuts, edits, pace, motion, zooms, sound
effects (the framework traces to Huston & Wright). These features capture and direct attention
largely through the **orienting response**: an automatic, reflexive reallocation of attention
toward novel or changing stimuli. Rapid cutting and high motion trigger orienting responses
*repeatedly*, which is both arousing and attentionally demanding. Lang's **Limited Capacity
Model of Motivated Mediated Message Processing (LC4MP)** gives the resource account: each edit
or scene change consumes a slice of finite processing capacity. This is why "fast and busy"
isn't a vague impression — it is a measurable rate of demands on a limited system. That rate is
exactly what this tool quantifies.

### Per-metric grounding (also usable as GUI tooltip copy)

- **Shot length / scene pacing** — Faster cutting means more frequent orienting responses and
  higher processing load. Lillard & Peterson (2011, *Pediatrics*) found that 4-year-olds who
  watched a fast-paced fantastical cartoon showed immediate executive-function decrements
  relative to slower or non-screen conditions. Important nuance to preserve: later work
  (Lillard et al., 2015) suggests *fantastical/unexpected events* may drive the effect as much
  as raw pace — so present pacing as one associated factor, not the cause. Pacing *variability*
  (steady vs. bursty rhythm) is worth surfacing on its own.
- **Motion** — High on-screen motion is a bottom-up, pre-attentive attention magnet (visual
  saliency work, e.g. Itti & Koch) and a recurring orienting trigger. More motion = more
  involuntary attentional pull and arousal.
- **Color saturation** — High saturation and contrast are salient, stimulating features that
  draw attention bottom-up. Treat as an arousal/stimulation proxy, not a quality judgment.
- **Flashing / luminance change** — Rapid luminance shifts are a recognized overstimulation and
  photosensitivity concern (photosensitive-epilepsy guidance; the well-known 1997 broadcast
  incident is the canonical case). This is the metric with the clearest safety, not just
  arousal, rationale.
- **Sensory load (composite)** — Synthesizes the above into a single arousal/attentional-demand
  profile. Christakis et al. (2004, *Pediatrics*) reported a correlational association between
  early heavy TV exposure and later attention problems, and proposed an overstimulation
  hypothesis (developing minds conditioned to expect high stimulation). State plainly that this
  is correlational and contested; the composite describes the *stimulus*, not the child's outcome.

### Reference scaffold (verify before formal citation)

- Huston & Wright — formal features framework
- Lang — Limited Capacity Model (LC4MP) of media processing
- Lillard & Peterson (2011), *Pediatrics* — pacing/fantastical content and immediate EF
- Lillard et al. (2015) — disentangling pace vs. fantastical content
- Christakis et al. (2004), *Pediatrics* — early exposure and later attention (correlational)
- Itti & Koch — bottom-up visual saliency
- Anderson & Pempek; Goodrich, Pempek & Calvert — formal features and young children's attention

### Honest limitations (put a version of this in the app's About panel)

The tool measures the stimulus, not the viewer. It cannot account for the child's age, temperament,
sensory-processing profile, or how much they watch. The evidence base is largely correlational and
in places actively debated. Output is a transparent profile to inform a caregiver's judgment, not a
rating, score-card, or verdict on a show.

---

## How to drive this

1. Drop this file in as `CLAUDE.md`.
2. Paste Phase 0. Verify acceptance. `git commit`.
3. Repeat through Phase 5, one phase per prompt, committing between each.
4. Don't let it run ahead — if it starts building the GUI during Phase 1, redirect it.
