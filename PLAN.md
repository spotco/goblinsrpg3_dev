# Goblins RPG 3 browser port plan

## Goal and acceptance criteria

Ship a **static** browser port of `goblins3 v.1.0 LAUNCH.pps` on GitHub Pages (`docs/`), with **no changes to the PowerPoint file**.

**Must work from the extracted data as-is.** The port must reproduce **all PowerPoint slide-advancement methods** used by the game so the full graph is playable without editing the `.pps`.

| Advancement method | Meaning in PPT | Port requirement |
| --- | --- | --- |
| **Hyperlink / action on shape or text** | Click control → go to a specific slide (or media/no-op) | Extract true targets; runtime navigates only on those hits |
| **OnNext / OnPrev animation clicks** | Stage click advances the animation queue | Already partially implemented; keep as first consumer of stage clicks |
| **Click-to-advance slide** | After builds (or with no builds), stage click goes to **next sequential slide** when the slide/show allows it (`manualAdvance` / default click advance) | **Decode + implement**; do **not** use a blanket “blank stage never advances” rule |
| **Auto-advance** | Timer after slide time / when animations finish | Keep; schedule `max(slideTimeMs, animation timeline)` accurately |
| **Media / other actions** | Sound, no-op, etc. | Keep mapped vs unresolved explicit |

**Hard constraint:** Do not require PowerPoint authoring fixes. If the binary truly contains a self-hyperlink, reproduce that atom’s behavior **and** still allow progress via any other PPT-legal advancement method that the show provides (e.g. click-to-next). Prefer fixing **mis-parsed** targets over inventing remaps.

**Deliverables:** extracted assets, `docs/game-manifest.json` + animation manifest, browser runtime, tools, automated checks. Manual playthrough/visual QA is last, not a blocker for the advancement milestone.

---

## Source inventory (stable)

| Item | Finding |
| --- | --- |
| Presentation | `goblins3 v.1.0 LAUNCH.pps` (PPT 97–2003/OLE), SHA-256 `5EF9EF5169B09119FD3E9CD7015FC8F25FF78BF104041CBC1EBBCA13BE45FA93` |
| Screens | 201 slides, 4:3 (5760×4320 source coords → 720×540 stage) |
| Actions | 217 interactive-action records; 194 hyperlinks (graph, not only linear) |
| Hyperlink graph (current extract) | ~118 forward, ~55 back, **21 self** (`target_slide == source`); most continues **work**; selfs cluster on some start/continue/image controls — see `generated/hyperlink_pattern_analysis.json` |
| Visuals | Embedded pictures + per-slide layers; reconstructed rasters under `docs/screens/` |
| Audio | Embedded WAVs + linked WMA/MIDI converted to MP3/Opus |

**Toolchain:** Python `olefile`/MS-PPT extractors + Apache POI audit (shapes/text/pictures/transitions; not full PP10 anim tree). No Aspose, no `python-pptx` for this binary.

**Animation data:** PP10 timing trees required (not optional). Evidence in `ANIMATION_EVALUATION.md`, `generated/timing_tree_audit.json`, `docs/animation-manifest.json`.

---

## Completed work (condensed)

### Extraction and assets
- [x] Inventory, semantics, layers, pictures, text, transitions, embedded/linked audio, MIDI render path.
- [x] PP10 animation manifest decode (nodes, triggers, sequences, modifiers, behaviors, motion/scale/set/effect/command).
- [x] WordArt geotext recovery (Escher `geotext.unicode` / font); slide solid backgrounds; opening title entrance path improved.
- [x] Non-watermarked reconstruct path (`tools/render_reconstructed.py` → `docs/screens/`); `RENDERING.md`.

### Browser runtime (`docs/`)
- [x] Static stage, layers, hotspots, restart/mute, cache-busting, first-gesture audio unlock.
- [x] Animation scheduler: OnNext queue, delays, set visibility, fade/dissolve, ppt_* animate, scale, motion endpoint, start/end triggers, transitions hooks, media `playFrom`.
- [x] Debug tooling: `?debug=1&slide=N`, HUD/API, `tools/debug_slide.py`, `audit_visual_risks.py`, `probe_mechanic.py`, `debug_bundle.py`, `analyze_opening_slides.py`, `docs/DEBUGGING.md`.

### Automated verification
- [x] Extractor/site/animation-contract/traversal/gameplay-behavior/audio/layer coverage verifiers (see `tools/verify_*.py` and README rebuild list).

### Packaging
- [x] Playable `docs/` tree; README for local serve and rebuild.

---

## NEXT MILESTONE (do this next): full PPT advancement support

**Objective:** Analyze and implement every slide-advancement path so the **entire game** is traversable with **unchanged** `.pps` data.

**Exit criteria:**
- Automated graph + advancement-policy tests pass for all slides.
- No reliance on editing the PowerPoint.
- Stage-click policy is **data-driven** from PPT (not a global “never advance” or “always next”).
- Hyperlink targets match the best available binary/POI (and PPT UI oracle where used for validation only).
- Agent can complete a scripted path from slide 1 through early story and sample combat hubs without manual PPT fixes.

### Phase A — Analyze advancement model (read PPT accurately)

Produce a single machine-readable report (suggested: `generated/advancement_model.json`) covering **all 201 slides**:

1. **Per-slide advancement profile**
   - Transition flags: `autoAdvance`, `manualAdvance`, slide time, effect type/direction.
   - Hyperlink/actions: targets, self vs non-self, text vs image hit, media/no-op.
   - Animation: OnNext/OnPrev queue depth, whether progress depends on stage clicks for builds.
   - **Classified mode(s)** e.g. `hyperlink_only` | `click_advance_after_anims` | `click_advance_always` | `auto_advance` | `mixed`.

2. **Hyperlink ground truth (especially the 21 self-links)**
   - Compare OLE `ExHyperlink` + `InteractiveInfoAtom` vs POI text/shape links.
   - Attempt deeper target resolution (persist IDs / place-in-document) if labels alone are insufficient.
   - Optional **read-only** PPT UI check on a sample (start, a few continues, a hub image link)—document findings; do not modify the file.
   - Output: for each self-link, `status = confirmed_self | misparsed | needs_deeper_atom | unknown`.

3. **Working patterns as fixtures**
   - Text continues that already resolve correctly (e.g. 17→22, 18→24).
   - Image multi-hotspot hubs (e.g. ~67, 69, 72, 102).
   - Choice text (Attack/flee) with non-self targets.
   - Use these as regression oracles for “do not break good edges.”

4. **Stuck-graph detection**
   - Slides with **no** non-self hyperlink **and** no autoAdvance **and** no click-to-advance classification → must be explained or fixed via correct flag/hyperlink decode.
   - Reuse/extend `generated/hyperlink_pattern_analysis.json` and `generated/slide_1_10_feature_gaps.json`.

### Phase B — Implement advancement in extractor + runtime

1. **Manifest schema**
   - [ ] Publish per-screen `advancement` (or equivalent) from extract/build: allowed stage-click effects, auto-advance delay, next sequential id when applicable.
   - [ ] Keep hotspots as today; ensure `targetSlide` reflects best resolution.

2. **Runtime stage-click continuum**
   - [ ] On stage click (non-hotspot):  
     1) unlock audio;  
     2) if animation queue non-empty → `advanceAnimation()`;  
     3) else if slide allows **click-to-advance** → `navigateTo(nextSequential)`;  
     4) else no-op.
   - [ ] Hotspot clicks always take precedence (`stopPropagation`).
   - [ ] Auto-advance: keep `max(slideTimeMs, animationTimeline.durationMs)`; fix timeline underestimates if advances fire early/late.
   - [ ] Debug deep-link `?slide=N` may still suppress auto-advance for inspection; document it.

3. **Hyperlink accuracy**
   - [ ] Fix extractor if Phase A finds mis-parsed targets.
   - [ ] If targets are confirmed self in the binary, **do not** invent remaps in the `.pps`; ensure the player can still leave the slide via any other decoded method (click-to-advance, other controls).
   - [ ] Never implement “global always next on blank click” without flags.

4. **Related animation support needed for full-game progress**
   - [ ] Multi-step set hidden/visible + dissolve OnNext trains (story slides).
   - [ ] Decode/apply `RT_TimeSubEffectContainer` if it changes reveal behavior.
   - [ ] ParaBuild/iterate: implement or document whole-shape approximation with a fixture (e.g. slide 7).
   - [ ] Keep media bindings and unresolved cues explicit.

5. **Automated tests for this milestone**
   - [ ] Advancement-policy unit tests from `advancement_model.json` (every slide has a legal leave rule or is a true terminal).
   - [ ] Traversal: hyperlink edges still valid; sequential click-advance edges where classified.
   - [ ] Regression: working continue/image hub samples still resolve to same targets.
   - [ ] Contract snippets for new runtime hooks only.
   - [ ] Wire into verify scripts as appropriate (`verify_site`, new `verify_advancement.py`, etc.).

### Phase C — After advancement works (secondary fidelity)

Defer until the game is fully traversable:

- WordArt geometry polish; empty text layer cleanup.
- Motion path sampling beyond endpoint; rotation/color/filter if needed later.
- Pixel-perfect vs PowerPoint screenshots.
- Optional a11y labels on hotspots; audio loop/stop/replace edge cases.
- GitHub Pages enablement if not already on.

---

## Later: manual testing and release QA (end of plan)

Do **not** block the advancement milestone on these. Run after automated advancement support is in place.

- [ ] Manual playthrough checklist for major branches/endings (use debug tools + risk queues).
- [ ] Visual review of all screens against PowerPoint reference screenshots (`generated/visual_review_checklist.json`); annotate special behavior.
- [ ] Browser QA: Chromium + Firefox; desktop and mobile viewports; text wrap, hitboxes, z-order, audio.
- [ ] Spot-check start → story → combat hub paths against the original `.pps` in PowerPoint slideshow.
- [ ] Confirm GitHub Pages deployment from `docs/` after push.

---

## Technical decisions (current)

| Topic | Decision |
| --- | --- |
| Source of truth | Unmodified `.pps`; port fixes extraction/runtime only |
| Rendering | Hybrid: addressable layers + reconstructed raster fallback + transparent hotspots |
| Audio | MP3 + Opus in `docs/assets/audio/`; no WMA at runtime |
| Stage click | **Data-driven**: animations first, then click-to-advance **if PPT says so**; not hyperlink-only forever, not always-next |
| Hyperlinks | Prefer accurate decode; majority of edges already work; investigate self-links before heuristics |
| Debug | `docs/DEBUGGING.md`; `?debug=1&slide=N`; offline autopsy/risk tools |

---

## Reference artifacts for future agents

| Artifact | Use |
| --- | --- |
| `docs/DEBUGGING.md` | How to debug runtime + offline tools |
| `generated/slide_1_10_feature_gaps.json` | Opening-ten gap snapshot (`tools/analyze_opening_slides.py`) |
| `generated/hyperlink_pattern_analysis.json` | Continue/image/self-link patterns |
| `generated/visual_risks.json` | Deck-wide risk queue |
| `generated/runtime_traversal.json` | Current hotspot-edge graph |
| `POI_EVALUATION.md` / `ANIMATION_EVALUATION.md` / `RENDERING.md` | Domain notes |

`_port_analysis_tmp/` remains disposable local research (JDK/POI/venv); not part of the published site.

---

## Immediate next actions for the next implementation run

1. **Analyze** full-deck advancement + hyperlink ground truth → write `generated/advancement_model.json` (and docs summary if useful).  
2. **Implement** manifest fields + runtime stage-click continuum + any extractor hyperlink fixes.  
3. **Automate** advancement/traversal regressions.  
4. Only then polish visuals / manual QA (later sections).
