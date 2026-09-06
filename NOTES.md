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

- Slide 2 queued `s002-tn0002` (media `playFrom`) then empty AfterEffect `s002-tn0007` (0 behaviors/children; Display/MediaVolume variants only).
- Prior continuum needed 3 hotspot clicks: build → empty no-op → hyperlink. Not RDP double-fire (1 mousedown/up/click per physical press).
- Fix: `advanceAnimation` skips empty interactive OnNext nodes (`!nodeSubtreeHasBehaviors`) and returns false when only empties drained so hyperlink can fire on the same click.
- Expected: click1 starts media; click2 leaves to slide 3. Same pattern on ~11 media AfterEffect placeholders deck-wide.
