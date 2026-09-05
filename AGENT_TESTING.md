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

## WordArt TEXT_CURVE_UP (2026-09-05)

### References (OOXML / Office)
- Microsoft Learn `TextShapeValues.TextCurveUp` → serialized `textCurveUp`: https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.drawing.textshapevalues
- Microsoft Learn `PresetTextWrap` (`a:prstTxWarp`) dual-path warp algorithm (top+bottom guides): https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.drawing.presettextwrap
- OOXML `prstTxWarp` / `ST_TextShapeType` including `textCurveUp` / `textCurveDown`: https://c-rex.net/samples/ooxml/e1/part4/OOXML_P4_DOCX_prstTxWarp_topic_ID0EBMJNB.html — https://c-rex.net/samples/ooxml/e1/Part4/OOXML_P4_DOCX_ST_TextShapeType_topic_ID0EQTSOB.html
- VBA `msoTextEffectShapeCurveUp` (=17): Office WordArt Transform “Curve Up”
- Practical SVG path defaults (CurveUp quadratic): [pptx-svg renderer_warp](https://github.com/t-ujiie-g/pptx-svg) `textCurveUp`: `M 0,cy+adj Q cx,cy-adj w,cy+adj` (adj≈h·0.46)

**Visual intent:** letters follow an **upward-arching path / warp between top&bottom curves** (middle higher, ends lower). **Not** a flat CSS rotate.

### Runtime
- `docs/app.js`: `mountWordArtPathWarp` + SVG `textPath` for `TEXT_CURVE_UP` / `TEXT_CURVE_DOWN` (and Arch siblings). Keeps fill/stroke/bounds from `32c503a`.
- Fixture: slide 14 shape **15382** “Yip!” — verify `?debug=1&slide=14` after stage-click + ~1.5s (delay+dissolve).
- Screenshots: `/workspace/goblins-yip-curve-*.png` (crop/stage/reconstructed).

### Residual
- Font: Arial Black may substitute; glyph outlines are textPath-along-tangent, not full OOXML dual-path mesh warp.
- `TEXT_DEFLATE` (s002 title) still CSS scale approx.

## Gap catalog — slides 1–3, 5, 7, 11–14 (+ title/start, captions, explosions, pre-battle)

Categorized **unimplemented or approximate** viewer gaps still relevant on these slides:

### A. WordArt / DrawingML text warp (`prstTxWarp`)
| Status | Item |
| --- | --- |
| **Done (path)** | `TEXT_CURVE_UP` (s014 Yip!) via SVG textPath; `CURVE_DOWN` / `ARCH_*` wired same helper |
| **Approx** | `TEXT_DEFLATE` (s002 GOBLINSRPG3) — CSS scaleY squeeze only |
| **Unused in deck / not implemented** | Other ST_TextShapeType presets (wave, inflate, chevron, fade, cascade, can, ring, stop, …) |
| **Residual** | True dual-path outline warp; WordArt 3D/bevel/extrusion (none authored on focus slides) |

### B. Builds / text animation
| Status | Item |
| --- | --- |
| **OK-ish** | ParaBuild `asAWhole` (many on s001/s003/s005/s007/s012/s014) — whole-shape entrances work without special splitter |
| **Partial** | `TimeIterateData` byWord/byLetter (s001 “Presents”) — unit stagger exists; multi-paragraph level builds unused |
| **Gap** | Dedicated ParaBuild scheduling UI/semantics beyond whole-shape (no `paraBuild` branch in `app.js`) |

### C. Entrance / emphasis effects
| Status | Item |
| --- | --- |
| **Implemented** | dissolve (dominant on focus slides), fade, visibility set, basic scale, line motion paths (s014 knock-off / fly) |
| **Approx / limited** | Slide transition `effectType=3` on s003 (wipe-class) — CSS transition subset only |
| **Not seen authored** | Complex presets (wheel, zoom, color pulse, spiral, …) on these slides |
| **Gap** | Richer effect filter graph / subEffect fidelity beyond fade+dissolve pairing |

### D. Geometry / media / composite
| Status | Item |
| --- | --- |
| **Implemented** | IRREGULAR_SEAL_1 clip-path “explosions” (s007); geometric AutoShapes; hybrid PNG underlay for sparse slides |
| **Gap** | Shadow / glow / soft-edge / reflection (no extract fields on focus layers today) |
| **Gap** | OLE / embedded object reactivation (source is legacy `.pps`; media via extracted assets + `playFrom` commands) |
| **Residual** | Caption/dialogue typography (apostrophes/ellipses), low-contrast text warnings, PNG vs live-layer double-draw policy on hybrid slides |
| **Pre-battle s014** | Motion + dissolve mostly wired; timing/click continuum still easy to desync vs PPT |

### E. Audio / commands
| Status | Item |
| --- | --- |
| **Partial** | `command` / `playFrom(0.0)` present (title/start media) — depends on extracted audio binding |
| **Gap** | Full PPT sound timeline / overlapping cue fidelity |

Use `?debug=1&slide=N` + `goblinsRpg3Debug.dumpScreen()` when claiming fixes.
