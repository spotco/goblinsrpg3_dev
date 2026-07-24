# Goblins RPG 3 browser port

This repository contains a static browser port of the original PowerPoint 97-2003 `.pps` game source.

The current playable build lives in `docs/`, which is suitable for GitHub Pages configured to publish from the `docs` folder on the `master` branch. The build uses reconstructed unwatermarked slide PNGs plus transparent HTML hotspots generated from the PowerPoint hyperlink/action records.

## Git workflow

Codex should commit completed, validated work locally, but should not push to GitHub unless explicitly asked.
When explicitly asked to publish, use plain `git` rather than `gh`, ask for approval immediately before the push tool call, and honor the requested destination branch.
If Git access to `.git` is denied, stop and request permission rather than retrying `.git\index` operations.

## Local preview

Run a static server from the repository root:

```powershell
python tools/serve_docs.py --port 8765 --directory docs
```

Then open:

```text
http://127.0.0.1:8765/
```

### Debug mode (recommended for agents and fidelity work)

```text
http://127.0.0.1:8765/?debug=1&slide=2
```

- `debug=1` enables console logging, hotspot outlines, and an on-page Debug HUD
- `slide=N` deep-links to a screen and suppresses boot auto-advance away from it
- Browser API: `goblinsRpg3Debug.dumpScreen()`, `goto(n)`, `listProblems()`, `snapshot()`

Offline helpers:

```powershell
python tools/debug_slide.py 2
python tools/audit_visual_risks.py
python tools/probe_mechanic.py all --slide 2
python tools/debug_bundle.py 2
python tools/render_reconstructed.py --slides 2
python tools/build_game_manifest.py --slides 2
```

Full playbook: [`docs/DEBUGGING.md`](docs/DEBUGGING.md).

Opening-ten feature gap report (for planning fidelity work):

```powershell
python tools/analyze_opening_slides.py
# → generated/slide_1_10_feature_gaps.json
```

See `PLAN.md` section **Next steps: slides 1–10 missing PowerPoint features**.

Defaults in `docs/app.js` (`RUNTIME_CONFIG`) still work; URL query overrides are preferred so you do not need to edit source. Log entries use the `[GoblinsRPG3]` prefix.

The local server sends `no-store`/`no-cache` headers for every page and asset. The page also adds a per-load cache-busting query to scripts, styles, manifests, images, and audio, so refreshes always fetch current files.

## Rebuild generated data

The extraction tools use Python packages listed in `tools/requirements.txt`.

```powershell
python tools/extract_ppt.py "goblins3 v.1.0 LAUNCH.pps"
python tools/audit_timing_tree.py "goblins3 v.1.0 LAUNCH.pps"
python tools/extract_animation_manifest.py "goblins3 v.1.0 LAUNCH.pps"
python tools/extract_layers.py
python tools/extract_embedded_audio.py "goblins3 v.1.0 LAUNCH.pps"
python tools/convert_audio.py
python tools/render_reconstructed.py
python tools/verify_render_manifest.py
python tools/build_game_manifest.py
python tools/extract_source_semantics.py
python tools/generate_visual_review.py
python tools/generate_gameplay_behavior_review.py
python tools/verify_extractor_contract.py
python tools/verify_inventory.py generated/inventory.json
python tools/verify_timing_tree.py
python tools/verify_animation_manifest.py
python tools/verify_animation_player_contract.py
python tools/verify_layers.py
python tools/verify_animated_layer_coverage.py
python tools/verify_embedded_audio.py
python tools/verify_audio_cues.py
python tools/verify_gameplay_behavior.py
python tools/verify_site.py
python tools/verify_runtime_traversal.py
python tools/build_advancement_model.py
python tools/verify_advancement.py
python tools/analyze_start_graph.py
python tools/verify_start_graph.py
python tools/scan_advancement_coverage.py
python tools/build_offline_playability.py
python tools/build_combat_option_matrix.py
python tools/build_media_death_report.py
python tools/build_chapter_walks.py
python tools/build_fidelity_reports.py
python tools/verify_fidelity.py
python tools/verify_runtime_traversal.py
python tools/verify_offline_playability.py
```

`generated/poi_audit.tsv` is produced by `tools/poi/PoiAudit.java` using the portable JDK and Apache POI copies in `_port_analysis_tmp/`. See `POI_EVALUATION.md` for the exact toolchain notes.

## Current limitations

- The selected publishable non-watermarked render path is the repo-local custom layer reconstruction documented in `RENDERING.md`; it is verified by `generated/reconstructed/render_manifest.json` and `tools/verify_render_manifest.py`.
- The screen PNGs are not yet verified pixel-perfect against Microsoft PowerPoint reference screenshots.
- The manifest now includes separately addressable image/text/shape layers and a decoded PP10 animation timing tree. The browser runtime has contract-covered first-pass support for linear property interpolation, acceleration/deceleration modifiers, auto-reverse, hold/restart behavior, OnNext/OnPrev queueing, chained start/end triggers, motion paths, scale behavior, visibility/set effects, observed slide transition effects, and mapped audio commands.
- `generated/source_semantics.json` consolidates stable slide IDs, title/name/master/layout flags, z-order coverage, text/style metadata, transition coverage, animation counts, and audio cue resolution status.
- `generated/animated_layer_coverage.json` verifies all 567 animated PowerPoint shape targets have separate browser layers, so animation-critical objects are not only present in the fallback screen raster.
- `generated/runtime_traversal.json` validates every declared hotspot edge and reports graph reachability/cycles. The current hotspot-only graph starts at `slide-001`, which has no hotspot, so opening-slide animation/click behavior still needs manual/runtime QA.
- `Ffvictory.mid` is rendered by `tools/render_midi.py` with the deterministic repo-local `goblins-python-additive-v1` synth, then converted to MP3 and Opus by `tools/convert_audio.py`.
- `docs/game-manifest.json` includes `audioCues` and `mediaBindings[].cueBehavior` records for trigger/start/loop/stop/replace behavior that is exposed by the extracted PowerPoint atoms.
- Three legacy embedded-audio cue references remain explicitly unresolved in `mediaBindings`; their cue IDs are not present in the embedded sound collection or recoverable linked-source inventory, so they need final PowerPoint-reference QA before mapping.
- `generated/visual_review_checklist.json` contains the 201-screen manual visual-review scaffold; manual playthrough and visual review are still required before calling this final.
- `generated/gameplay_behavior_review.json` classifies all 217 extracted action records: 194 navigation actions, 7 clickable mapped media actions, 1 mapped media action with zero click area, 3 unresolved media actions, and 12 explicit no-op actions.
