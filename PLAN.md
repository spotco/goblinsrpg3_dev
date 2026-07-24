# Goblins RPG 3 browser port plan

## Goal and acceptance criteria

Ship a **static** browser port of `goblins3 v.1.0 LAUNCH.pps` on GitHub Pages (`docs/`), with **no changes to the PowerPoint file**.

**Must work from the extracted data as-is.** The port must reproduce **PowerPoint slide-advancement methods** used by the game so content is navigable without editing the `.pps`.

### Product tiers (choose / track explicitly)

| Tier | Meaning | Status (2026-07) |
| --- | --- | --- |
| **A — Early loop shippable** | Title → intro → first combats → death **or** closed combat loop; offline-proven | **Near-ready** (~29 directed slides from start) |
| **B — Full deck navigable** | From title **or** a documented chapter/entry map, all major story/combat content is reachable | **Not met** (~29/201 from title; islands + zero-inbound roots) |
| **C — PPT-faithful feel** | Navigation + visuals + timing match original slideshow | **Partial** (nav policy v3; anim/visual fidelity open) |

**Near-term goal (while manual playtest may be unavailable):** lock **Tier A offline**, make **Tier B via chapter entries** (not invented title bridges), then fidelity (Tier C pieces).

**Do not treat** `stuckSlideCount == 0` alone as “fully playable.” Leave-path coverage is necessary; **start-directed reachability + honest controls** are also required.

### Advancement methods (port requirements)

| Advancement method | Meaning in PPT | Port requirement |
| --- | --- | --- |
| **Hyperlink / action on shape or text** | Click control → specific slide (or media/no-op) | Extract true targets; runtime navigates only on those hits |
| **OnNext / OnPrev animation clicks** | Stage click advances the animation queue | First consumer of stage clicks |
| **Click-to-advance slide** | After builds, stage click → next sequential when `manualAdvance` / policy allows | Data-driven; not “blank stage never advances” forever |
| **Auto-advance** | Timer after slide time / when animations finish | `max(slideTimeMs, animation timeline)` |
| **Media / other actions** | Sound, no-op, etc. | Mapped vs unresolved explicit |

**Hard constraint:** Do not require PowerPoint authoring fixes. Prefer fixing **mis-parsed** targets over inventing remaps. Where ExHyperlink is confirmed self-only (`Slide N`, no target atom), apply **documented** playability promotes (continue/start, sole-image, all-self combat) with provenance — not a silent inventory rewrite. **Do not invent story bridges** (e.g. s042 → midgame) without PPT UI oracle or misparse proof.

**Deliverables:** extracted assets, `docs/game-manifest.json` + animation manifest, browser runtime, tools, automated checks. Manual playthrough/visual QA is last, not a blocker for offline navigation milestones.

---

## Source inventory (stable)

| Item | Finding |
| --- | --- |
| Presentation | `goblins3 v.1.0 LAUNCH.pps` (PPT 97–2003/OLE), SHA-256 `5EF9EF5169B09119FD3E9CD7015FC8F25FF78BF104041CBC1EBBCA13BE45FA93` |
| Screens | 201 slides, 4:3 (5760×4320 source coords → 720×540 stage) |
| Actions | 217 interactive-action records; 194 hyperlinks (graph, not only linear) |
| Hyperlink graph (binary) | ~118 forward, ~55 back, **21 self** by ExHyperlink label; inventory label-faithful; port promotes in manifest |
| Start-directed graph | **29** slides reachable from slide 1; early combat **loops s042 → s021**; no binary exit to mid/late game |
| Sealed islands | **s043–s054** (Ubergoblin + mini hub); **s020–s025** pair |
| Zero-inbound roots | 18 slides including **s043**, **s055** midgame (debug/`?slide=` only under current graph) |
| Visuals | Embedded pictures + per-slide layers; reconstructed rasters under `docs/screens/` |
| Audio | Embedded WAVs + linked WMA/MIDI → MP3/Opus |

**Toolchain:** Python `olefile`/MS-PPT extractors + Apache POI audit. No Aspose, no `python-pptx` for this binary.

**Animation data:** PP10 timing trees required. See `ANIMATION_EVALUATION.md`, `generated/timing_tree_audit.json`, `docs/animation-manifest.json`.

---

## Completed work (condensed)

### Extraction and assets
- [x] Inventory, semantics, layers, pictures, text, transitions, embedded/linked audio, MIDI render path.
- [x] PP10 animation manifest decode (nodes, triggers, sequences, modifiers, behaviors, motion/scale/set/effect/command).
- [x] WordArt geotext recovery; slide solid backgrounds; opening title entrance path improved.
- [x] Non-watermarked reconstruct path (`tools/render_reconstructed.py` → `docs/screens/`); `RENDERING.md`.

### Browser runtime (`docs/`)
- [x] Static stage, layers, hotspots, restart/mute, cache-busting, first-gesture audio unlock.
- [x] Animation scheduler: OnNext queue, delays, set visibility, fade/dissolve, ppt_* animate, scale, motion endpoint, start/end triggers, transitions hooks, media `playFrom`.
- [x] Debug tooling: `?debug=1&slide=N`, HUD/API, offline autopsy tools, `docs/DEBUGGING.md`.

### Advancement / graph (leave-path milestone)
- [x] Advancement policy continuum + `advancement` blocks on all screens (`advancementPolicy` **v4**).
- [x] Self-link playability promotes + s046 combat all-self → 47; leave-path **stuck = 0**.
- [x] Start-graph analysis + baseline verify (29 slides); sealed islands documented; no invented bridges.
- [x] Coverage scan, stuck-hyperlink audit, advancement model + verifiers.

### Automated verification / packaging
- [x] Extractor/site/animation/traversal/gameplay/audio/layer verifiers; playable `docs/` tree; README rebuild list.

---

## Advancement policy (implemented)

| PPT signal | Port behavior |
| --- | --- |
| `manualAdvance` | Stage click → next sequential after OnNext queue empty |
| `autoAdvance` + `slideTimeMs` | Timer; delay = `max(slideTimeMs, animation timeline)` |
| Neither bit | Blank stage does not change slides (unless documented fallback) |
| Hotspots | Always first (`stopPropagation`) |
| Self continue/start + sole image | Promote to next + provenance |
| Combat all options self | Promote to next outcome (`combat_all_self_to_next_outcome`) — see s046 |
| Combat partial self | Keep self; leave via other options |
| Death / Press esc | `deathTerminal` + `restart_only` |
| Continue text / empty interstitial, no leave | Stage-click-to-next fallback |
| Binary `action=none` + continue/combat label | **Promote**: mirror sibling hyperlink by text, or continue→next if sole leave (`noop_mirror_sibling_hyperlink` / `noop_continue_to_next`) |
| Residual binary self (partial combat / hub image) | Keep target=source; **`accepted_source_self` non-clickable** when slide has other leave paths |

**Counts:** 201 slides · **14** stage-click-advance (9 manualAdvance + 5 interstitial fallbacks; continue-text fallbacks reduced after noop promote) · 59 auto-advance · **0** stuck leave paths. Hyperlinks in manifest: **202** (194 binary + 8 noop promotes).

#### s046 Ubergoblin (documented promote)

Binary labels all options `"Slide 46"`; s047 is authored death cutscene (15 dmg); no win/flee branches; promote all options **46 → 47** with provenance. Partial combat selfs elsewhere **not** bulk-promoted.

#### Source graph limitation (documented, not a missing atom)

- All **217** InteractiveInfoAtoms inventoried; **jump always 0**; ExHyperlink = single friendly name only.
- Title path is a **closed early loop** (re-entry **s042 → s021**).
- Mid/late content is leave-able once entered but **not title-reachable** without chapter jumps or a future proven edge.
- Artifacts: `generated/start_graph_analysis.json`, `generated/advancement_coverage_scan.json`.

---

## Milestone: playable product (offline-first)

**Objective:** A working game that future agents can verify **without browser playtest**, then expand to full-deck navigation and fidelity.

**Definition of done without browser playtest:**

- Tier A path walk automated and green  
- Graph/orphan report green or explicitly accepted in PLAN  
- P1 transition defects fixed or listed with slide IDs  
- Chapter entry map for non-title content  
- Promote audit table regenerable from manifest  

When playtest returns: visual/feel QA only — **not** rediscovering the graph.

---

### Phase 0 — Align goal (do first on any long run)

- [x] Confirm near-term ship target in this PLAN (default until overridden):
  - [ ] **A only** — early 29-slide loop as the product
  - [x] **A + chapter select** — **current default** for “full content” without inventing bridges
  - [ ] **B from title** — requires PPT oracle evidence **or** explicit policy exception to invent bridges
- [x] Recorded under Technical decisions (`Near-term ship default`).

---

### Phase 1 — Offline “is it a game?” proof

Highest value without playtest. Tools write reports under `generated/`; verify is self-contained.

- [x] **1.1 Path walker** — `tools/build_offline_playability.py` + `tools/playability_graph.py` → `generated/path_walk_report.json` (seeds include 1, 43, 55, …).
- [x] **1.2 Tier A fixtures** — `tools/verify_offline_playability.py`: story/village/combat, death **s030**, loop **s042→s021**, baseline **29** slides.
- [x] **1.3 Chapter / entry catalog** — `generated/chapter_entry_map.json` (zero-inbound roots, sealed islands, `?debug=1&slide=N` hints).
- [x] **1.4 Promote audit table** — `generated/promote_audit.json` (promotes + residual selfs).
- [x] **1.5 Clickable contract** — `generated/clickable_contract.json`; residual selfs allowed as documented; violations fail verify.
- [x] **1.6 Wire verifies** — `verify_offline_playability.py` + README rebuild list.
- [x] **1.7 Agent handoff note** — `docs/DEBUGGING.md` section “Prove Tier A without browser playtest”.

**Exit criteria:** met — offline suite green; reports under `generated/`.

**Phase 1 residual follow-up:** completed in Phase 2 (noop continues + residual self policy).

---

### Phase 2 — Transition defects (offline-provable)

Fix labeled controls that don’t navigate. Prefer hotspot-level resolve with provenance (same family as continue promote).

#### P1 — labeled control broken

- [x] **2.1 Noop continues** — `noop_continue_to_next` for sole continue labels (**s155, s158, s163**); `noop_mirror_sibling_hyperlink` when continue text matches a sibling nav control (**s051** → same target as sibling). Policy v4. Residual empty-text noops: **s010, s012, s014, s036** (decorative; real continue is another hotspot).
- [x] **2.2 Combat/menu noops** — mirror sibling by label: **s150** `-limit`→167, **s156/s159/s164** `-attack`→ working sibling targets (`noop_mirror_sibling_hyperlink`). Combat matrix `noopOptions=0`.
- [x] **2.3 Combat option matrix** — `tools/build_combat_option_matrix.py` → `generated/combat_option_matrix.json` (also via offline playability build).
- [x] **2.4 Partial combat selfs** — **s015 flee**, **s027 flee**, **s039 attack**: kept binary self (`confirmed_self_combat`); **`residualStatus=accepted_source_self`**, **non-clickable**, `behaviorStatus=documented_residual_self`, rationale on hotspot. Leave via other option / auto. **No invent remap** without oracle.
- [x] **2.5 Residual image selfs** — **s050, s052**: same residual policy (`hub_image_self`); multi-exit hubs keep other hotspots clickable.
- [x] **2.6 Re-run** offline suite after residual policy; clickable contract: residual selfs non-clickable; residualSelfCount=5.

#### P2 — media / secondary nav noise

- [x] **2.7 Unresolved media** — **s054, s096, s193** (legacy cue ids **3/4** missing from embedded audio): `documented_unresolved_media`, non-clickable, rationale; **no invented sounds**. Report: `generated/media_death_residuals.json`.
- [x] **2.8 Zero-area media** — **s104** mapped cue 2 but zero-area bounds: `documented_zero_area_media`, non-clickable; auto playFrom may still run from timing tree.
- [x] **2.9 Death terminals** — **s030/s197** `terminalKind=death`, `leavePaths=restart_only`, `terminalNotes`; **s200** `terminalKind=end_card` + hyperlink leave to 201 + notes. Verified in `verify_advancement` / offline suite.

**Exit criteria (Phase 2 complete):** 2.1–2.9 done. Transition/media residuals are documented or promoted; full Phase 2 offline suite green. Next: Phase 3 chapters.

---

### Phase 3 — Midgame as chapters (Tier B without title bridges)

Make non-title content a working game via **documented entry**, not invented s042 exits.

- [x] **3.1 Subgraph walks** — `tools/build_chapter_walks.py` → `generated/chapter_walks.json`; primary seeds 1/20/43/52/55/66/70/119/148/166 + zero-inbound; **allOk**, no stuck.
- [x] **3.2 Publish entry map** — enriched `generated/chapter_entry_map.json` (`tierB.mode=chapter_select`, outcomes, orphan entries); slim `docs/chapter-entries.json` for runtime.
- [x] **3.3 Debug chapter menu** — under `?debug=1` HUD: Chapters select + Go loads `chapter-entries.json` and jumps via `goblinsRpg3Debug.goto`.
- [x] **3.4 Island integrity** — islands s043–054 / s020–25 leave-able from primary entries; **s052** not directed-reachable from 43 (orphan entry documented + menu/walk seed).
- [x] **3.5 Verify** — `verify_offline_playability` asserts walks allOk, islands ok, menu contains 1/43/55.

**Exit criteria:** met — **Tier B via chapter select** (title still closed 29-slide loop; no invented bridges). Residual: human may still want more menu labels / QA of midgame content feel (Phase 5/6).

**Note for agents:** From s043 primary walk, hub nodes **52/53** need `?slide=52` (island orphan). s055 walk reaches **118** slides including death/end terminals.

---

### Phase 4 — Title → midgame only with evidence

- [ ] **4.1 Human PPT UI oracle** — can original leave early combat loop? Reach s043 / s055 from title?
- [ ] **4.2 If UI matches binary (closed loop)** — accept Tier A + chapters; **or** explicit policy exception to invent bridges (list each edge + rationale in PLAN).
- [ ] **4.3 If UI disagrees with binary** — find misparse/atom; fix extractor; re-promote only with proof; update start-reachability baseline.
- [ ] **4.4 No silent bridges** — any new forward edge must have provenance + verify fixture.

**Exit criteria:** Decision recorded; either baseline still 29 with chapters, or new reachability count + tests.

---

### Phase 5 — Fidelity (Tier C pieces; after nav is honest)

Do **not** block Phases 1–3 on these.

#### Animation / timing

- [x] **5.1** Opening train **inventory + contract** — `generated/opening_animation_trains.json` for **s003–s008, s012–s014** (OnNext counts, set/effect presence, timeline ms). Runtime first-pass OnNext/set/effect confirmed. **Residual:** pixel-true multi-step dissolve sequencing still approximate (see 5.2).
- [ ] **5.2** `RT_TimeSubEffectContainer` / ParaBuild-iterate: implement beyond whole-shape approximation (documented in opening trains `runtimeSupport`).
- [x] **5.3** Auto-advance timing — runtime `max(slideTimeMs, animationTimeline)`; offline `generated/auto_advance_timing.json` + `verify_fidelity.py` (59 autos; effective ≥ slideTime; 4 extended by anim estimate).
- [ ] **5.4** Motion path sampling beyond endpoint; rotation/color/filter if needed.
- [x] **5.5** Sequential advance edges — `generated/sequential_advance_edges.json` + `verify_runtime_traversal.py` v2: **9** manualAdvance, **5** fallback stage-click, **59** auto edges; opening 3–8/12–13 fixtures.

#### Visual / text / audio

- [ ] **5.6** WordArt geometry polish; empty text layer cleanup.
- [ ] **5.7** Mojibake / encoding cleanup on layer text (e.g. `Æ`, `à` artifacts) where extractible.
- [ ] **5.8** Visual risk queue: missing anim target layers (e.g. s007), sparse coverage; **refresh offline self_hyperlink risks** to use post-resolve targets (stale highs vs promoted runtime).
- [ ] **5.9** Low-contrast text mitigation or document as source art.
- [ ] **5.10** Audio loop/stop/replace edge cases; unresolved media cleanup (overlaps 2.7).
- [ ] **5.11** Pixel-perfect vs PowerPoint screenshots (optional late).

#### Runtime / packaging extras (known gaps)

- [ ] **5.12** Optional a11y: focusable hotspots, keyboard activate, labels from shapeText.
- [ ] **5.13** Touch / small-viewport hit targets (mobile QA later).
- [ ] **5.14** CI (or documented one-shot script) running full verify suite on push.
- [ ] **5.15** GitHub Pages enablement + cache-bust smoke after deploy.
- [ ] **5.16** Optional: mute persistence, reduced-motion respect for anims.

---

### Phase 6 — Manual testing and release QA

Run after Phases 1–3 (and 4 if pursuing title wiring). **Do not** block offline milestones.

- [ ] **6.1** Manual playthrough: Tier A happy path (title → combat loop / death).
- [ ] **6.2** Chapter jumps: `?slide=43` Ubergoblin; `?slide=55` midgame; 1–2 deep combat hubs from catalog.
- [ ] **6.3** Spot-check promotes (s002 start, s009 village, s046 options → 47).
- [ ] **6.4** Visual review vs `generated/visual_review_checklist.json` / PPT screenshots.
- [ ] **6.5** Browser QA: Chromium + Firefox; desktop + mobile viewports; text wrap, hitboxes, z-order, audio.
- [ ] **6.6** Spot-check same paths in original `.pps` slideshow (oracle notes).
- [ ] **6.7** Confirm GitHub Pages from `docs/` after push.

---

## Transition defect backlog (snapshot for agents)

Update when fixed. Severity: **P0** full-game from title · **P1** broken labels · **P2** polish.

| ID | Sev | Slides / scope | Issue | Phase |
| --- | --- | --- | --- | --- |
| G1 | P0 | Start set 29; s042→s021 | Closed early loop; no title→midgame edge in binary | 3–4 |
| G2 | P0 | 43–54, 20–25 | Sealed undirected islands | 3 |
| G3 | P0 | 18 zero-inbound roots | Orphan story/combat trains | 3 |
| T1 | P1 | ~~051, 155, 158, 163~~ | Continue noop → **fixed** (mirror/next) | 2.1 done |
| T2 | P1 | ~~150, 156, 159, 164~~ | Combat option noop → **fixed** (mirror sibling) | 2.2 done |
| T5 | P2 | 010, 012, 014, 036 | Empty-text decorative explicit_noop (sibling continue works) | accept |
| T3 | P1 | ~~015, 027, 039~~ | Partial combat self → **documented non-clickable residual** | 2.4 done |
| T4 | P1 | ~~050, 052~~ | Hub image self → **documented non-clickable residual** | 2.5 done |
| M1 | P2 | ~~054, 096, 193~~ | Unresolved media → **documented non-clickable** (cue 3/4 missing) | 2.7 done |
| M2 | P2 | ~~104~~ | Zero-area media → **documented non-clickable** | 2.8 done |
| D1 | P2 | 030, 197, 200 | Death/end terminals documented (`terminalKind`/`terminalNotes`) | 2.9 done |
| A1 | P2 | Opening trains | Inventory+contract done; pixel dissolve residual | 5.1 partial |
| A3 | P2 | Auto-advance timing | max(slide, anim) offline+runtime | 5.3 done |
| A4 | P2 | Sequential edges | traversal v2 + fixtures | 5.5 done |
| A2 | P2 | Builds | ParaBuild / sub-effects | 5.2 |
| V1 | P2 | Deck-wide | Visual risks / contrast / stale self_hl audit | 5.8–5.9 |

---

## How future agents should continue

1. Read **Product tiers** + **Phase 0** choice (if unset, default to **A + chapter select**).  
2. Open **Immediate next actions** (below) — Phases 1–3 + **5.1/5.3/5.5** fidelity contracts done; next deeper anim (5.2/5.4) or visual risks (5.8) or Phase 6 QA.  
3. Prefer **offline tools + `generated/*` reports** over assuming browser playtest (`verify_offline_playability.py`).  
4. Mark checklist items `[x]` when done; add residual rows to the defect backlog.  
5. Rebuild: see README verify list; always refresh advancement model + start graph + offline playability after manifest changes.  
6. Never invent title→midgame edges without Phase 4 evidence or explicit policy exception.

### Immediate next actions (current head of queue)

1. **Phase 5.2 / 5.4** — ParaBuild/sub-effects and/or motion path sampling (deeper anim fidelity).
2. **Phase 5.8** — refresh visual_risks self_hyperlink audit to post-resolve targets (stale highs).
3. **Phase 6** manual QA when playtest is available (chapter menu + Tier A path).
4. Phase 4 PPT oracle only if title-connected midgame is required.


## Technical decisions (current)

| Topic | Decision |
| --- | --- |
| Source of truth | Unmodified `.pps`; port fixes extraction/runtime only |
| Rendering | Hybrid: addressable layers + reconstructed raster + transparent hotspots |
| Audio | MP3 + Opus in `docs/assets/audio/`; no WMA at runtime |
| Stage click | Data-driven: anims first, then click-advance if PPT/policy says so |
| Hyperlinks | Inventory = binary labels; documented promotes only |
| Graph vs leave-path | Leave-path stuck = 0 ≠ full game; start set = 29; chapters for rest |
| Story bridges | Forbidden without oracle/misparse or explicit PLAN exception |
| Near-term ship default | **Tier A + chapter select** until Phase 0 overrides |
| Tier B acceptance | **Chapter select** (not title-connected full graph); walks allOk as of Phase 3 |
| Debug | `docs/DEBUGGING.md`; `?debug=1&slide=N`; offline tools |
| Playtest | Manual QA last; offline suite is the gate while unplaytested |

---

## Reference artifacts for future agents

| Artifact | Use |
| --- | --- |
| `docs/DEBUGGING.md` | Runtime debug + offline tools |
| `generated/start_graph_analysis.json` | Early loop, islands, zero-inbound, baseline 29 |
| `generated/advancement_model.json` | Per-slide leave paths |
| `generated/advancement_coverage_scan.json` | Leave-path OK, reachability, residual selfs |
| `generated/stuck_hyperlink_analysis.json` | ExHyperlink deep audit |
| `generated/hyperlink_pattern_analysis.json` | Continue/image/self patterns |
| `generated/visual_risks.json` | Deck-wide risk queue (refresh post-resolve) |
| `generated/runtime_traversal.json` | Hotspot-edge graph |
| `generated/gameplay_behavior_review.json` | Action behavior counts |
| `POI_EVALUATION.md` / `ANIMATION_EVALUATION.md` / `RENDERING.md` | Domain notes |
| `generated/path_walk_report.json` | Tier A / multi-seed path walks |
| `generated/chapter_entry_map.json` | Debug entry catalog / chapters |
| `generated/promote_audit.json` | All port promotes + residual selfs |
| `generated/clickable_contract.json` | Clickable hotspot contract |
| `generated/combat_option_matrix.json` | Per-fight option targets |

`_port_analysis_tmp/` remains disposable local research (JDK/POI/venv); not part of the published site.
