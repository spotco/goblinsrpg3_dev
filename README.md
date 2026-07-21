# Goblins RPG 3 browser port

This repository contains a static browser port of the original PowerPoint 97-2003 `.pps` game source.

The current playable build lives in `docs/`, which is suitable for GitHub Pages configured to publish from the `docs` folder on the `master` branch. The build uses reconstructed unwatermarked slide PNGs plus transparent HTML hotspots generated from the PowerPoint hyperlink/action records.

## Git workflow

Codex should commit completed, validated work locally, but should not push to GitHub unless explicitly asked.

## Local preview

Run a static server from the repository root:

```powershell
python -m http.server 8765 --directory docs
```

Then open:

```text
http://127.0.0.1:8765/
```

Add `?debug=1` to show hotspot rectangles.

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
python tools/build_game_manifest.py
python tools/extract_source_semantics.py
python tools/verify_extractor_contract.py
python tools/verify_inventory.py generated/inventory.json
python tools/verify_timing_tree.py
python tools/verify_animation_manifest.py
python tools/verify_animation_player_contract.py
python tools/verify_layers.py
python tools/verify_animated_layer_coverage.py
python tools/verify_embedded_audio.py
python tools/verify_audio_cues.py
python tools/verify_site.py
python tools/verify_runtime_traversal.py
```

`generated/poi_audit.tsv` is produced by `tools/poi/PoiAudit.java` using the portable JDK and Apache POI copies in `_port_analysis_tmp/`. See `POI_EVALUATION.md` for the exact toolchain notes.

## Current limitations

- The screen PNGs are a first-pass reconstruction, not a verified pixel-perfect PowerPoint export.
- The manifest now includes separately addressable image/text/shape layers and a decoded PP10 animation timing tree, but the JavaScript animation player is not fully implemented yet.
- `generated/source_semantics.json` consolidates stable slide IDs, title/name/master/layout flags, z-order coverage, text/style metadata, transition coverage, animation counts, and audio cue resolution status.
- `generated/animated_layer_coverage.json` verifies all 567 animated PowerPoint shape targets have separate browser layers, so animation-critical objects are not only present in the fallback screen raster.
- `generated/runtime_traversal.json` validates every declared hotspot edge and reports graph reachability/cycles. The current hotspot-only graph starts at `slide-001`, which has no hotspot, so opening-slide animation/click behavior still needs manual/runtime QA.
- `Ffvictory.mid` is rendered by `tools/render_midi.py` with the deterministic repo-local `goblins-python-additive-v1` synth, then converted to MP3 and Opus by `tools/convert_audio.py`.
- `docs/game-manifest.json` includes `audioCues` and `mediaBindings[].cueBehavior` records for trigger/start/loop/stop/replace behavior that is exposed by the extracted PowerPoint atoms.
- Three legacy embedded-audio cue references remain explicitly unresolved in `mediaBindings`; their cue IDs are not present in the embedded sound collection or recoverable linked-source inventory, so they need final PowerPoint-reference QA before mapping.
- Manual playthrough and visual review are still required before calling this final.
