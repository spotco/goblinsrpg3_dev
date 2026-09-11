# Maintenance notes

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

