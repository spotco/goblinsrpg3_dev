# Agent testing notes — Goblins RPG 3 browser port

Last audited: 2026-09-03 (agent setup pass).

## What this is
Static browser port of `goblins3 v.1.0 LAUNCH.pps` into `docs/` for GitHub Pages.
The browser never loads the `.pps`; it loads prebuilt manifests and assets.

## Checkouts / git policy
- Agent computer (default): `/workspace/goblinsrpg3_dev`
- User PC only when explicitly asked: `F:\dev\goblinsrpg3_dev`
- Branch: **`grokbot-dev`** — push here; never merge to `master`/`main` unless user explicitly asks
- After each chunk: report what changed + what to test/verify (see `NOTES.md`)

## Goal snapshot (from PLAN.md)
- Tier A (early loop): title to intro to first combats to death/loop — offline nearly locked (~29 slides from start)
- Tier B: full deck navigable — not met (islands / zero-inbound roots)
- Tier C: PPT-faithful feel — partial; visual/anim QA still open

## Setup (agent computer)
```bash
cd /workspace/goblinsrpg3_dev
python3 -m venv .venv
.venv/bin/pip install -r tools/requirements.txt
.venv/bin/python tools/serve_docs.py --port 8765 --directory docs
# open http://127.0.0.1:8765/?debug=1&slide=2
```

## Setup (user PC)
```powershell
cd F:\dev\goblinsrpg3_dev
python tools/serve_docs.py --port 8765 --directory docs
```

## Prove without babysitting the browser first
```bash
.venv/bin/python tools/verify_offline_playability.py
.venv/bin/python tools/verify_site.py
.venv/bin/python tools/verify_runtime_traversal.py
.venv/bin/python tools/verify_animation_manifest.py
```

Note: `verify_animated_layer_coverage.py` currently expects the obsolete snippet
`screenImage.hidden = renderedLayers;` — runtime uses hybrid underlay
`screenImage.hidden = renderedLayers && !pngUnderlay;` (treat verifier fail as contract drift, not missing layers).

## Browser QA protocol (required for Tier C claims)
1. Serve `docs/` with `tools/serve_docs.py` (cache-busting headers).
2. Always use `?debug=1&slide=N` for fidelity work.
3. Console API: `goblinsRpg3Debug.dumpScreen()`, `goto(n)`, `listProblems()`, `snapshot()`.
4. For each suspect slide: wait ~2s for auto/timeline, then stage-click for OnNext, then hit hotspots.
5. Compare extract to manifest to runtime decision, not pixels alone (`docs/DEBUGGING.md`).

### Priority slides from user memory / TODO_NOTES.md
| Slide | Claim / focus |
| --- | --- |
| 1 | Wrong background |
| 2 | Opening anim / advance |
| 14 | Goblin vs dog attack image anims |
| 21 / 42 | First combat loop (042 to 021) logic |
| 29 | Combat slide transitions |
| 32 | Attack anims + missing images |

## Claim evaluation template
- Asset extraction: confirm `docs/screens` (201), `docs/assets/slide-assets`, `docs/game-manifest.json`, `docs/animation-manifest.json`; rebuild from README only if the `.pps` changed.
- Web animations/rendering: dumpScreen on slides above; check lastRenderDecision (layers vs hybrid vs png), animated layer count, motion after OnNext.
- Slide progression: advancement HUD + offline playability; distinguish graph-OK vs runtime-broken.
- First combat logic: walk seed 1 offline then browser slide 21 / 42 hotspots; do not invent story bridges.

## Known durable facts (2026-09-03 setup)
- Offline playability: passed (TierA=29, death=True, loop042 to 021=True).
- Site + runtime traversal + animation manifest: passed.
- Local untracked on user PC: `TODO_NOTES.md` (not on GitHub root listing).
- `_port_analysis_tmp/` is disposable analysis workspace (gitignored).

## Browser QA results (2026-09-03)

Served at `http://127.0.0.1:8765/?debug=1&slide=N`. No uncaught JS errors on slides 1 or 32.

| Slide | Observed |
| --- | --- |
| 1 | White bg + logo; sparse; no anim; HUD low-contrast warning |
| 2 | Title/start text overlapping; hotspot advances to slide 3; no anim motion |
| 14 | Landscape renders; goblin/dog/attack imagery absent; media click no visual change |
| 21 | Combat UI + two goblins; Attack/Flee drawn but not clickable; goblin hotspots go to 19 and 17 |
| 29 | Sparse hills + gray sword figure; empty text outline; hotspot → slide 30 death |
| 32 | Similar sparse scene; attack imagery/anims absent |

Claim verdicts: extraction OK; web anim/render broken; progression partial (hotspots yes, anim-driven no); first combat controls broken at runtime.
