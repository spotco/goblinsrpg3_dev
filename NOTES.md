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
