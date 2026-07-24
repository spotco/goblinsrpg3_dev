# Debugging the Goblins RPG 3 port

The browser **never loads the `.pps`**. It loads prebuilt dumps:

- `docs/game-manifest.json` — screens, layers, hotspots, media, transitions
- `docs/animation-manifest.json` — timing tree
- `docs/screens/*.png` — reconstructed composites (fallback / review)
- `docs/assets/**` — layer images + audio

When something “looks wrong,” compare **source extract → published manifest → runtime decision**, not just pixels.

## Quick start (browser)

Serve the site:

```powershell
python tools/serve_docs.py --port 8765 --directory docs
```

Open a slide with full debug mode:

```text
http://127.0.0.1:8765/?debug=1&slide=2
```

| Query | Effect |
|---|---|
| `debug=1` | Logging + hotspot outlines + on-page Debug HUD |
| `slide=N` | Jump straight to slide N (skips boot auto-advance away from it) |
| `log=1` | Logging only |
| `hotspots=1` | Hotspot outline CSS only |
| `hud=1` | HUD only |

### Browser console API

`window.goblinsRpg3Debug`:

| Method | Purpose |
|---|---|
| `goto(2)` / `goto("slide-002")` | Navigate and return a dump |
| `dumpScreen()` / `dumpScreen(2)` | Full runtime dump (layers, hotspots, render decision, problems) |
| `listProblems()` | Heuristic problems for the current screen |
| `snapshot()` | Animation queue / timers / last interaction |
| `setDebugMode({ logging, css, hud })` | Toggle features live |
| `toggle()` / `setEnabled(true)` | Console logging only |

HUD buttons call `dumpScreen()` / `listProblems()` and also log to the console.

Click a layer while debug/HUD is on to select it (cyan outline + HUD detail).

## Slide advancement (runtime)

Stage click policy is data-driven from each screen’s `advancement` block in `game-manifest.json`:

1. Unlock audio  
2. If OnNext animation queue non-empty → play next animation node  
3. Else if `advancement.stageClickAdvancesSlide` (PPT `manualAdvance` bit) → go to `nextSequentialId`  
4. Else no-op (hyperlink/media hotspots only)

Rebuild policy:

```powershell
python tools/build_game_manifest.py
python tools/build_advancement_model.py
python tools/verify_advancement.py
```

Debug HUD shows `advancement` modes and leave paths. `?slide=N` still suppresses **auto**-advance for that slide only.

## Offline tools

All commands assume the repo root as the working directory.

### Prove Tier A without browser playtest

Offline playability suite (PLAN Phase 1) walks the **post-resolve** graph and freezes fixtures:

```powershell
python tools/build_offline_playability.py
python tools/verify_offline_playability.py
```

| Output | Purpose |
| --- | --- |
| `generated/path_walk_report.json` | BFS from seeds; Tier A summary (29 slides, death s030, loop s042→s021) |
| `generated/chapter_entry_map.json` | Zero-inbound roots + sealed islands + `?debug=1&slide=N` hints |
| `generated/promote_audit.json` | All port promotes + residual self hyperlinks |
| `generated/clickable_contract.json` | Clickable hotspots must navigate, play media, or be documented residual self |
| `generated/media_death_residuals.json` | Unresolved/zero-area media residuals + death/end terminal notes |

Also useful: `python tools/analyze_start_graph.py` / `verify_start_graph.py` for the closed early-loop baseline.

Chapter jumps (Tier B without title bridges):

- URL: `?debug=1&slide=43` (Ubergoblin island), `?debug=1&slide=55` (midgame), `?debug=1&slide=52` (island hub orphan).
- HUD: with `?debug=1`, use **Chapters** dropdown + **Go** (`docs/chapter-entries.json`, rebuilt by `tools/build_chapter_walks.py`).
- Offline: `generated/chapter_walks.json` (all seeds leave-able), `generated/chapter_entry_map.json`.

### Fidelity offline contracts (Phase 5.1 / 5.3 / 5.5)

```powershell
python tools/build_fidelity_reports.py
python tools/verify_fidelity.py
python tools/verify_runtime_traversal.py
```

| Artifact | Purpose |
| --- | --- |
| `generated/sequential_advance_edges.json` | 9 manualAdvance + fallback stage-click + 59 auto edges |
| `generated/auto_advance_timing.json` | `effectiveDelayMs = max(slideTime, anim timeline)` |
| `generated/opening_animation_trains.json` | s003–s008 / s012–s014 OnNext + behavior inventory |
| `generated/runtime_traversal.json` | Hotspot + sequential combined graph |

### Single-slide autopsy

```powershell
python tools/debug_slide.py 2
python tools/debug_slide.py 2 --open
```

Writes `generated/debug/slide-002.json` with:

- POI shapes (text / geotext / pictures / style)
- Published layers + hotspots
- PNG stats
- Risk list + suggested follow-up commands

### Whole-deck risk queue

```powershell
python tools/audit_visual_risks.py
python tools/audit_visual_risks.py --slides 1-20
```

Writes `generated/visual_risks.json`:

- `queue` — slides sorted by severity (start here)
- `byCode` — grouped issue types
- `risks` — flat list

### Mechanic probes

Compare source mapping vs port for one concern:

```powershell
python tools/probe_mechanic.py wordart --slide 2
python tools/probe_mechanic.py hotspots --slide 2
python tools/probe_mechanic.py animation --slide 2
python tools/probe_mechanic.py media --slide 2
python tools/probe_mechanic.py background --slide 2
python tools/probe_mechanic.py pictures --slide 2
python tools/probe_mechanic.py all --slide 2 --json
```

### Debug bundle (shareable capture)

```powershell
python tools/debug_bundle.py 2
```

Creates `generated/debug/bundles/slide-002/` with `report.json`, PNG copies, sample layer images, and a local README.

## Faster rebuilds while iterating

Do **not** re-render all 201 slides unless you must.

Layer / text / hotspot / JS-only issues:

```powershell
python tools/extract_layers.py
python tools/build_game_manifest.py
# refresh browser
```

Composite PNG / reconstruction issues for a few slides:

```powershell
python tools/render_reconstructed.py --slides 2,14-16
python tools/build_game_manifest.py --slides 2,14-16
```

`--slides` on `build_game_manifest.py` only limits which screen PNGs are refreshed; the full game manifest is still rebuilt.

## Recommended agent workflow

When a screen or mechanic looks wrong:

1. Open `http://127.0.0.1:8765/?debug=1&slide=N` (or `goblinsRpg3Debug.goto(N)`).
2. Read the HUD + `dumpScreen()` / `listProblems()`.
3. Run `python tools/debug_slide.py N` and read `generated/debug/slide-NNN.json`.
4. If needed, run `python tools/probe_mechanic.py <mechanic> --slide N`.
5. Prefer pipeline fixes (`extract_layers` / POI audit / render / manifest) over one-off DOM hacks.
6. Rebuild only affected slides when possible; verify with dump + screenshot.

Whole-deck triage:

```powershell
python tools/audit_visual_risks.py
# work queue entries from generated/visual_risks.json
```

## What the risk codes mean (selected)

| Code | Meaning |
|---|---|
| `empty_text_wordart_unrecovered` | Escher geotext exists but layer text is empty |
| `self_hyperlink` | Hotspot targets its own slide |
| `unresolved_media` | Media action has no mapped audio |
| `sparse_visual_coverage` | No large image / very little drawn content |
| `low_contrast_text` | Light text on light slide background |
| `layers_mode_hides_png` | Runtime hides composite PNG because layers exist |
| `animation_target_missing_layer` | Timing tree targets a shape with no layer |
| `nearly_empty_png` | Reconstructed screen has almost no non-black samples |
| `missing_layer_image_file` | Layer `instancePath` file is missing on disk |

## Architecture reminder

```text
.pps  --offline extract/render-->  docs/*  --browser fetch-->  app.js runtime
```

Runtime decisions that commonly surprise people:

- If a screen has **any layers**, the full-screen PNG is **hidden** and only HTML layers draw.
- WordArt text often lives in **geotext.unicode**, not POI `getText()`.
- Slide backgrounds are often solid fills (e.g. white), not pictures.
- Stage clicks advance **queued animations**; only hotspot clicks navigate/play media.

## Related docs

- `README.md` — local preview + full rebuild pipeline
- `RENDERING.md` — reconstructed PNG path
- `POI_EVALUATION.md` — Apache POI limits vs Python OLE extractors
