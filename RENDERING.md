# Rendering path

The selected publishable non-watermarked render path is the repo-local custom reconstruction:

```powershell
python tools/render_reconstructed.py
python tools/verify_render_manifest.py
python tools/build_game_manifest.py
```

This path composites `generated/layers.json` into 720×540 4:3 PNG screens under `generated/reconstructed/`, then copies those screens into `docs/screens/` via `tools/build_game_manifest.py`.

The render index is `generated/reconstructed/render_manifest.json`. It records:

- renderer id: `goblins-layer-reconstruction-v2`
- source layer manifest
- output size and scale
- per-slide output path
- byte count and SHA-256
- image/text/transformed rendered-layer counts

This keeps the browser build publishable on GitHub Pages without Office, Aspose, LibreOffice, or a backend. Runtime hotspots and animated objects remain data-driven from `docs/game-manifest.json` rather than being baked into a screenshot-only port.

## Current fidelity boundary

This renderer is the selected publishable path, not yet a claim of pixel-perfect PowerPoint fidelity. The remaining fidelity blocker is comparison against Microsoft PowerPoint reference screenshots. That requires a trusted PowerPoint export or screenshots captured from the original `.pps`.

Generated review scaffold:

```powershell
python tools/generate_visual_review.py
```

The output `generated/visual_review_checklist.json` lists all 201 screens, their render path, hotspot counts, animated/transformed layer counts, graph-reachability flags, and a pending manual review status.
