## 2026-09-13 s183 caption / s194 star flash / s201 credits crawl

**s183 top white box empty:** Shape 223238 is the white plate; 223239 is
`Step into the light… if th'art worthy…` with letter-iterate Appear. Units were
created at `opacity:0` for stagger, but set-visible only flipped `visibility`
when `opacity===""`, leaving letters invisible inside the box.

**Fix:** iterate set-visible → `opacity:1` (hidden → `0`).

**s194 white boxes over stars:** STAR_4 AutoShapes dissolve in then have
After-Animation Hide (`subEffect` OnEnd). Extract OnEnd `targetId` is the OOXML
cTn id, while `emitAnimationTrigger` keys on extract serial → hide never ran;
white stars stacked over the art. Also raced dissolve `finishIn` at the same ms.

**Fix:** bind mismatched OnEnd hides to parent entrance end +32ms and apply via
`applyHideOnNextClickAfterEffectNow` (cancel WAAPI + hard hide).

**s194 auto-advance?** No. Transition `slideTimeMs=6000` but `flags=0` (no
`autoAdvance` bit). Manifest `autoAdvance=false`. Do not invent.

**s201 multiple scrolling credits:** Hybrid PNG underlay kept baked credits under
the live ppt_y crawl (plus character layers). 

**Fix:** `screenNeedsPngUnderlay` returns false when a large animated text layer
(area≥0.35) exists — layers-only so one credits crawl.

**Verify:** `?debug=1&slide=183` (stage-click) — caption in white box;
`?debug=1&slide=194` (stage-click, ~12–14s) — stars flash then clear;
`?debug=1&slide=201` — single credits scroll, PNG hidden.

## 2026-09-13 World-map yellow boxes after arrow dissolve

**Symptom (slides 65 / also 84, 93):** yellow LEFT/DOWN_ARROW AutoShapes dissolve in looking correct for ~500ms, then become solid yellow rectangles.

**Cause:** `applyEffectBehavior` `finishIn` cleared `clipPath`/`webkitClipPath` after every entrance. Arrow geometry is CSS `clip-path` from `AUTOSHAPE_CLIP_PATHS` (`dataset.autoShapeClip`). Clearing it left the `#ffff00` fill as a box.

**Fix:** restore AutoShape clip-path in `finishIn` when `dataset.autoShapeClip` is set; `commitStyles`+`cancel` WAAPI so `fill: "forwards"` cannot keep a temporary box/inset clip.

**Slide 44 “You are here”:** PPT/pptx has `downArrow` + motion path (off-slide start) + red ellipse + “You are here” text dissolve. Arrow has **motion only** (no dissolve), so it was not hit by this bug. Slide **64** has map + red oval + caption only — **no** arrow shapes in .pps/pptx.

**Verify:** `?debug=1&slide=65` — after dissolve, LeftArrow/DownArrow stay arrow-shaped.

## 2026-09-13 Image exits + counter visibility + transition catalog

**Kill fade (s019 Felled and siblings):** PPS/pptx agree the goblin pic is
`presetClass=exit` / EffectType=2 `blinds(horizontal)` (not fade) + hide-after
~500ms. Runtime used to stub anything except fade/dissolve (`effect-skipped`).
`applyEffectBehavior` now plays blinds / box(in) / fade+dissolve **out** using
TimeEffectBehaviorAtom transition flag.

**Counter attack visibility (s023/s025/s032):** goblin pics are motion-only
paths starting at ~(0,0) — already on-slide. Pre-hiding every motion target
left them invisible until the path ran. Fly-ins (s014 hop, s019 slash) still
pre-hide because their path origin is far from 0.

**Slide transitions:** catalog of SSSlideInfoAtom vs pptx `p:transition` is
still only 3=checker, 11=zoom, 21=comb, 22=newsflash, 23=fade, 27=circle (+cut).
All already had CSS from 8d03732. `verify_transition_effects.py` now asserts
PPS↔pptx counts and image effect filters.

# Maintenance notes

## 2026-09-13 DocSummary slideId hyperlink resolve (overturns "irreducible" combat)

**Misread:** ExHyperlink CString `"Slide N"` is a *stale friendly name*. Real destinations
live in `\x05DocumentSummaryInformation` as UTF-16 `slideId,staleNum,Slide staleNum`,
paired 1:1 with ExHyperlink order, mapped through SlideListWithText `slideId` →
presentation order. 75/194 labels were stale.

**First combat (matches modern PPT on .pps + pptx debug lens):**
- Attack 15→**19** (Felled)→25 (x2 Attacks)→21 (×2 menu) — one fewer goblin
- Flee 15→**17** (CAN'T ESCAPE)→23 (x3 Attacks)→24 (×3 menu) — same count
- Boredom auto 15→16 still authored (asset-013 ×2); narrative "fled" ≠ Attack kill

**Also fixed by same resolve:** s002 start→3; s042→22 (not 21); s046→47 native (no
combat_all_self promote); start reachability 29→**193**; sealed islands → 0.

**Transitions:** CSS remapped SSSlideInfoAtom types to OOXML names used in deck:
3=checker, 11=zoom, 21=comb, 22=newsflash (s015), 23=fade, 27=circle. Prior CSS
wrongly mapped 22→wipe / 11→push.

**Policy:** still no target overrides / invent-bridges — this is extract fidelity.


## Agent / Grok Bot workflow (enforced)

- Default work happens on the agent cloud computer (`/workspace/goblinsrpg3_dev`), not the user's local PC, unless the user explicitly asks for local-machine work.
- Development branch is **`grokbot-dev`**. Push validated work to `grokbot-dev` only.
- **Never** merge to `master` / `main` unless the user explicitly asks.
- When a work chunk is done, always tell the user: (1) what changed, (2) what to test/verify (URLs, commands, slides).
- Use plain `git` for publish operations; do not use `gh` for push.
- If Git reports that `.git` access is denied, stop immediately and ask for permission; do not repeatedly retry or probe `.git\index`.

## Legacy publish notes

- Inspect the worktree and intended scope, then commit intentionally before push.
- Push destination for ongoing agent work: `grokbot-dev` (not `master`).

## 2026-09-05 WordArt curve-up

- Implemented SVG `textPath` warp for `TEXT_CURVE_UP` (see `AGENT_TESTING.md`).
- Push target remains `grokbot-dev` only.

## 2026-09-06 Start hotspot empty OnNext

- Slide 2 queued `s002-tn0002` (media `playFrom`) then empty media placeholder `s002-tn0007` (0 behaviors/children; Display/MediaVolume variants only — NOTES historically called these AfterEffect placeholders; they are OnNext-gated root siblings with variant instances 2/22, not TL_TPID_AfterEffect=13).
- Prior continuum needed 3 hotspot clicks: build → empty no-op → hyperlink. Not RDP double-fire (1 mousedown/up/click per physical press).
- Fix (61e35cc+): `advanceAnimation` drains empty interactive OnNext nodes via `isEmptyClickAdvanceNode` / `!nodeSubtreeHasBehaviors` and returns false when only empties drained so hyperlink/media can fire on the same click. Skip applies generally to any queued empty OnNext/OnPrev node, not slide-2-only.
- Expected: click1 starts media; click2 leaves to slide 3.
- Deck-wide scan of `docs/animation-manifest.json`: **11** empty OnNext nodes (waits triggerEvent 9/10, zero subtree behaviors), all root-time-node siblings:
  s002-tn0007, s013-tn0007, s014-tn0040, s030-tn0013, s054-tn0018, s074-tn0014, s081-tn0017, s096-tn0018, s104-tn0007, s193-tn0011, s197-tn0013.
- Playwright spot-check: s002 leaves in **2** hotspot clicks (empty drained on same click as hyperlink). s013: click1 advances media build, click2 drains empty `s013-tn0007` and falls through to media action (not stuck). s014 empty exists in manifest; slide autoAdvance may run sequences without parking it in the click queue — hotspot/stage clicks still not stuck on dead empties.

## 2026-09-06 First goblin×3 combat HUD / hotspot clicks

- Symptom: with `?debug=1`, Attack/Flee on combat menus (bottom-right OPTION) looked drawn but were not clickable; gold hotspot outlines sat under the Debug HUD. Blue debug outlines on goblin *layers* were easy to misread as the hit targets (s021 Attack→19 / flee→17 is the real wiring).
- Extract/manifest check (inventory + POI TEXTLINK + `combat_option_matrix` + start-graph): early combat targets are binary-faithful (including s015 Attack→18 CAN'T ESCAPE, s015 flee residual self non-clickable, loop s042→s021). No invent-bridge remaps.
- Runtime fix: `docs/styles.css` Debug HUD
  - `pointer-events: none` on the HUD shell; only `button`/`select` (and collapsed header) re-enable hits
  - Cap HUD `max-height: min(48vh, calc(100vh - 120px))` and shrink body so chapters/footer stay above OPTION
- Verify: Playwright across viewports — s015 Attack→18, s021 Attack→19 / flee→17 with `?debug=1`; continue/loop edges without debug. Screenshots `/workspace/goblins-combat-*.png`.


## 2026-09-06 Combat playthrough annotations + continue gate

- Debug HUD/overlay: per-slide role, hp/text hints, hotspot shapeText->target, anim behavior counts; stage overlay top-left (pointer-events:none); `goblinsRpg3Debug.combatAnnot()`.
- Fix: animated continue hotspots gated until reveal (late anim-manifest boot re-renderHotspots); Attack/Flee stay immediate.
- Playthrough (Playwright): Attack 15->18->24->31->29->30; boredom 15->16->32/17->22; 21 Attack/flee; 22->34/36->42->21 loop; s014 auto->15. Anims OK after full timeline waits; early missing text was delay.


## 2026-09-08 Title 1-click + combat empty phase + debug history

- **Debug history:** `?debug=1` HUD shows a playthrough ring buffer; `goblinsRpg3Debug.history()` / `clearHistory()`; persisted `sessionStorage` key `goblinsRpg3.debugHistory`.
- **Title 1-click:** Navigation hyperlinks bypass the OnNext continuum. Media-command-only OnNext (`playFrom`) is non-gating and sync-fired (or autoplayed on enter for continue-like slides including “Click here to start”), so BGM unlocks/plays on the same press that leaves to slide 3 — no separate media click.
- **Combat empty phase:** Attack/Flee hyperlinks were previously consumable by pending OnNext (e.g. s016 boredom title). Result slides (CAN'T ESCAPE / damage / felled) started entrance-hidden until a stage click — looked dead/empty after Attack. Fix: hyperlink bypass + autoplay OnNext on continue/media-only slides (not menu slides).
- Verify: Playwright title 1-click → s3 with `audio:play`; s015→18, s016→32, s021→19 settle with visible continue; flee 21→17→22. Screenshots `/workspace/goblins-fix2-*.png`.

## 2026-09-09 Attack→flee history + s003 dead first click

- **User history recovered** (`goblinsRpg3Debug.history()` / `sessionStorage`): s015 hotspot `-Attack` (shape 17419) → **slide 18** (not flee 17). Slide 18 is PPT `CAN'T ESCAPE!!` and combatAnnot role `flee-fail`, which is why Attack felt like a flee outcome. Binary/inventory confirms Attack→18 / flee residual self→15 (non-clickable). No remapping.
- **Why Playwright missed “wrong option” risks:** prior tests called `button.hotspot.click()` / aria substring `Attack`, which always hits the Attack DOM node. They never clicked the **visual OPTION text center**, and `/attack/i` can match “Goblin x3 attacked!”. Added `tools/verify_combat_visual_options.py` — mouse-clicks exact `^-?\s*attack$` / flee layer|button centers; fails if Attack navigates to a *distinct* flee target. Battle playthrough updated to use the same visual centers.
- **s003 post-title dead first click:** OnNext sequence `s003-tn0002` (`nextAction` click children) consumed click1 only to enqueue builds with no visible text. Fix: when a click opens that sequence, run the **first child on the same click** (`scheduleChildNodes(..., allowClickNode)`). Expected: click1 → “100 to 150 years ago…”, click2 peace, click3 Until…, click4 → s4. Builds are real (not empty); `fAutomatic:false` kept.

## 2026-09-11 First combat menu (s015) Attack/Flee + goblin flash

- **User report:** Attack/Flee stacked/broken; only Attack clickable; auto-advance and 3rd goblin disappears.
- **Extract/PPT:** Attack→18 (CAN'T ESCAPE); flee=self residual (`accepted_source_self`, non-clickable); `autoAdvance` 9000ms →16 boredom (2 goblins — authored). Bounds do **not** overlap (Attack y≈0.644, flee y≈0.711).
- **Flee “broken” UX:** PPT draws `-flee` underlined, but playability keeps it non-clickable (no invent flee bridge). Fix: `applyResidualCombatOptionStyle` mutes residual OPTION text (`.residual-combat-option`, no underline, opacity 0.45, title=rationale) so UI matches dead hit.
- **“3rd goblin disappears”:** (1) waiting out s015 auto→16 is the boredom leave (one goblin fled) — faithful. (2) Attack→18 standing goblin was invisible: parent effect-group `durationMs=0` emitted OnEnd at 1ms so AfterEffect Hide-After-Animation ran before the 500ms motion child — empty debug bounds. Fix: `nodeOnEndDelayMs` waits for **children** (not OnEnd-waiting subEffects) before emitting OnEnd. Goblin visible ~motion duration then hides.
- Verify: `tools/verify_combat_visual_options.py`; Playwright s015 Attack→18→24 continue; auto→16; screenshots `/workspace/goblins-menu15-*.png`.

## 2026-09-11 Click-gated result beats + s015 flee self-reload

- **User report:** 29→30→31 advancing automatically; Flee broken / wrong slides / goblins vanish.
- **29/30/31 auto-feel:** Not authored `autoAdvance` (flags clean). Runtime `screenShouldAutoplayAnimations` treated continue-only result beats as autoplay, so OnNext builds ran without clicks and felt like free slide advances. Fix: autoplay **only** when `advancement.autoAdvance` (PPT timer slides). Continue/result beats stay click-gated; stage click runs OnNext, then continue hyperlink leaves.
- **s015 -flee self:** Binary ExHyperlink target is Slide 15 (self) — intentional residual, not unimplemented. Prior mute/non-clickable UX diverged from PPT (self-hyperlink reloads the slide). Fix: `residual_self_reload` stays clickable → re-enter s015 (anims + 9s boredom timer reset). **No invent-bridge to 17.** Attack still →18; boredom auto →16.
- **Chapter jump:** Debug Chapters menu adds **First goblin x3 battle (pre-menu)** → s014 (`?debug=1&slide=14`).
- Verify: `tools/verify_click_advance_combat.py` (no auto-nav 29/30/31; click-gated continue; flee reload; Attack/boredom); offline/gameplay/advancement verifies.


## 2026-09-12 s015 Flee “does nothing” + Attack empty green boxes

- **Repro (f6186e0):** Flee hotspot fires `navigate-to-same-screen` and re-enters s015 (dissolve on “Goblin x3 attacked!” does replay) — feels like no-op because PPT binary target is self (not flee-fail 17). Attack→18 is binary-correct; slide 18 text is authored `CAN'T ESCAPE!!` (combatAnnot role flee-fail) **with** motion paths on 23555/23556.
- **Root cause of empty green boxes:** f6186e0 disabled continue-only OnNext autoplay. Attack landed on entrance-hidden layers; `?debug=1` outlined those hidden bounds on the grass. Stage click then played the attack motion — extra click felt broken.
- **Fix:** Restore continue-only `screenShouldAutoplayAnimations` (menu stays click-gated; result/continue autoplays in-slide entrances). Slide nav still requires continue hyperlink (29/30/31 must not auto-nav). Hide debug outlines on `visibility:hidden` layers. Tests: `verify_click_advance_combat.py` asserts Attack shows motion/text without stage click; flee re-enter; no invent→17.
- **Not overturned:** Attack→18 and flee self-reload remain PPT-faithful (no invent edges).
- **Green boxes nuance:** (1) `?debug=1` layer outlines on entrance-hidden shapes (fixed: no outline while `visibility:hidden`). (2) A few extracted pictures are ~100% Office palette green `(0,128,0)` placeholders (PPT chroma) — hidden via `.pure-green-placeholder`. Do **not** chroma-key mixed hill/sprite art (same green paints the grass).

### 2026-09-13 — exact two-goblin Flee regression

- **Extract evidence:** s016 (`Goblin fled of boredom…`) contains goblin picture shapes 20483/20485. Its binary hyperlinks are Attack shape 20488 →32 and Flee shape 20489 (`s016-a425115`) →17. s016 has no autoAdvance flag. s017 is authored `CAN'T ESCAPE!!!`, with Continue →22; s022 is the authored one-goblin menu.
- **Live exact repro:** start `?debug=1&slide=15`, allow authored 9s boredom auto→16, then click the visual Flee center once. History records `s016-a425115` →17 and slide enter 17. After the full 4.25s motion/text train the page remains on 17 with `CAN'T ESCAPE!!!` and `Click here to continue…`; it does not race/self-reload/auto-advance to s022.
- **Observed “run-away then 1 goblin” explanation:** s017 itself animates the player's failed escape before showing `CAN'T ESCAPE!!!`; the one-goblin state is s022, reachable only through s017's explicit Continue hyperlink. No extract supports remapping s016 Flee to an attack/damage slide, so no connection was invented.
- **Regression:** `tools/verify_combat_visual_options.py` now covers the full s015 boredom→s016 two-goblin state, visual-pointer hit target, Flee→17 history, visible failure caption, and a long settle proving one click cannot continue to s022.


## 2026-09-13 — remove target overrides; PPT binary is oracle

### Hard policy
**Never have overrides.** `USER_AUTHORIZED_TARGET_OVERRIDES` / Pass 4 remaps are removed.
Treat the `.pps` binary (ExHyperlink labels + InteractiveInfoAtom + POI TEXTLINK) as
oracle. If remembered play conflicts with binary edges, fix extract/runtime
interpretation — do not invent story remaps.

### Restored binary
- s017 Continue → **22** (1-goblin menu). Provenance: ExHyperlink id 77 label
  `Slide 22`, POI TEXTLINK on shape 18443, InteractiveInfoAtom action=4.

### Deep re-read of first-goblin combat (extract evidence)

| From | Action | Binary target | Visual goblins | Notes |
|------|--------|---------------|----------------|-------|
| s015 (×3) | Attack | s018 | — | POI+inventory agree shape 17419→18. s018 caption says CAN'T ESCAPE but carries Attack motion paths; Continue→s024 still ×3. **Not a kill ladder.** |
| s015 (×3) | Flee | s015 self | ×3 | Residual self-reload (PPT self-hyperlink). No invent→17. |
| s015 (×3) | autoAdvance 9s | s016 | **×3→×2** | SSSlideInfoAtom autoAdvance bit confirmed by POI. s016 text “Goblin fled of boredom…”, asset-013 ×2. |
| s016 (×2) | Attack | s032 | ×2 counter | Goblin x2 Attacks → Fury death chain |
| s016 (×2) | Flee | s017→**22** | **×2→×1** | Binary Continue drops count. |
| s021 (×2) | Attack | s019 Felled→24 | lands ×3 | “Felled” continue does **not** land on ×1/×2 menu |
| s021 (×2) | Flee | s017→**22** | **×2→×1** | Same as s016 |
| s022 (×1) | Attack/Flee | s034 / s036 | ×1 paths | Restored into start-reachability via s017→22 |

### Interpretation fixes (not remaps)
1. **Role misread:** debug `inferSlideRole` used caption “CAN'T ESCAPE” alone, so
   Attack→s018 looked like flee-fail. Now prefers inbound Attack/Flee option labels
   (`attack-result` vs `flee-fail`).
2. **Hotspot↔shape mapping:** Attack/Flee shape→target associations match POI
   TEXTLINK for s015/s016/s017/s018/s019/s021/s022 — **not** a resolve bug.
3. **Boredom:** “I'm bored…” on s015 is the passive on-slide dissolve (autoplayed
   with autoAdvance). Auto-nav 15→16 **is** authored and visually drops to ×2.
   Treating that auto leave as a “kill” matches the PPT assets/text; it conflicts
   with remembered “boredom≠kill”. **Documented conflict — no remap, no clearing
   the autoAdvance bit.**
4. **Attack=kill+counter:** No binary edge from the opening ×3 Attack lands on a
   Felled→lower-count menu. The Felled kill (s021→19) exists but Continue→24 (×3).
   **Documented conflict with remembered kill ladder.**
5. **Flee=fail+counter same count:** Binary flee-fail Continue→22 drops ×2→×1.
   Prior override→32 removed. **Documented conflict with remembered same-count
   counter.**

### Verify
- `tools/verify_advancement.py` — s017→22; zero `user_authorized_target_override`
- `tools/verify_combat_visual_options.py` — visual Attack/Flee; boredom→Flee→17→22
- `tools/verify_start_graph.py` — start reachability includes 19/21/22/34/36/42 again

## 2026-09-13 — exhaustive combat misread search (no remaps)

Prior note documented conflicts; this pass dug past ExHyperlink labels into
SSSlideInfoAtom bits, ExtTimeNode targets, InteractiveInfo parents, ExHyperlink
CString instances, asset-013 counts, and orphan slides. **No interpretation bug
found that yields remembered Attack/Flee/boredom play.** Binary remains oracle.

Artifact: `generated/combat_interpretation_audit.json` via
`tools/audit_combat_interpretation.py`.

### 1. Boredom / auto-advance — NOT a false synthesize

| Check | Result |
|-------|--------|
| SSSlideInfoAtom s015 | `rawHex=28230000…0016000400…` → slideTime=9000, **flags=0x0400 autoAdvance**, effectType=**22 newsflash** (POI: visual transition only) |
| s016/s021/s022 | slideTime=9000 but **flags=0** — authors stored times without enabling auto |
| “I'm bored…” | ExtTimeNode dissolve on shape **17427** (delay 3500ms); legacy AnimationInfoAtom automatic+synchronous |
| Goblin hide on s015? | **No** — anim targets only text 17418/17427, never asset-013 pics |
| Leave | auto 15→16; s016 text “Goblin fled of boredom…”, **asset-013 ×3→×2** |

Falsified: media-end misparse, effectType-as-advance, boredom dissolve as slide change.

### 2. Attack kill path — binding / off-by-one falsified

| Check | Result |
|-------|--------|
| s015 Attack 17419 | InteractiveInfo hlId **62**, action=Hyperlink, jump=NoJump; ExHyperlink **only** CString inst0 `"Slide 18"` |
| POI TEXTLINK | same 17419→Slide 18; address **null** |
| MouseOver? | InteractiveInfo parent instance=**0** (mouse-click) for all early combat options |
| Multi-InteractiveInfo/shape | **0** |
| Bounds | Attack y≈0.644 / flee y≈0.711 — no overlap |
| s018 | Caption CAN'T ESCAPE!! + motion paths; Continue→**24 still ×3** (HP 25→10) |
| Orphan **s023** | “Goblin x3 Attacks!” / 15 dmg →24; **inbound=[]**; string `"Slide 23"` **absent** from Document stream |

Cannot misread Attack→18 as →23: there is no hyperlink to 23. s021 Attack→19 Felled is a different menu’s edge; Continue still →24×3.

### 3. Flee → same-count counter — Continue→22 is real ×1

| Check | Result |
|-------|--------|
| s016/s021 Flee | →17 (binary) |
| s017 Continue | ExHyperlink **77** `"Slide 22"`; transition flags=[]; no AfterEffect slide jump |
| s022 art | **1× asset-013**; reconstructed PNG one goblin |
| s032 (×2 Attacks) | inbound **only** s016 Attack — not flee Continue |

Prior Continue→32 was a story override (removed db303a4). Not restorable under oracle policy.

### 4. Asset-count heuristic

`assetId==asset-013` picture count matches reconstructed screens (15:3, 16:2, 21:2, 22:1, 24:3). Not chroma-placeholder double-count.

### Irreducible conflicts (remembered vs this LAUNCH.pps)

1. Boredom ≠ kill — binary auto-leaves to authored ×2 boredom menu.
2. Opening Attack = kill+fewer goblins — binary Attack→18→24 keeps ×3 (orphan s023 unused).
3. Flee fail = counter same count — binary Continue→22 drops to ×1.

### Interpretation experiments left (not remaps)

1. **A (decisive):** Real PowerPoint slideshow oracle on this exact `.pps` (wait 9s / Attack / Flee+Continue).
2. **B:** Hash any alternate goblins builds vs `inventory.source.sha256`.
3. **C:** POI address null already confirmed.
4. **D (anti-pattern):** Do not clear autoAdvance or remap 17→32 / 18→23.

No code remaps. Runtime/extract targets unchanged.
