# Goblins RPG 3 browser port plan

## Goal and acceptance criteria

Turn the supplied PowerPoint game into a static site that can be hosted unchanged on GitHub Pages. The game will preserve the presentation's point-and-click navigation: the page background must **not** advance the game, and only the intended linked text/images (plus any explicitly designed in-game controls) may change state. It must work from a normal static HTTP server with no backend, database, or Office installation required by players.

The delivered site will include the extracted/converted assets, a declarative game manifest, a small browser runtime, source extraction tools, deployment instructions, and automated navigation checks.

## Confirmed source inventory

| Item | Finding |
| --- | --- |
| Presentation | `goblins3 v.1.0 LAUNCH.pps`, a PowerPoint 97–2003/OLE binary file (PowerPoint 2003-era), SHA-256 `5EF9EF5169B09119FD3E9CD7015FC8F25FF78BF104041CBC1EBBCA13BE45FA93` |
| Screen scope | 201 PowerPoint `Slide` records, using a 4:3 5760×4320 presentation coordinate system |
| Navigation | 217 interactive-action records and 194 hyperlink records; therefore the game is a navigation graph rather than a linear slide sequence |
| Visual assets | 115 embedded PNG blips and one embedded bitmap blip in the `Pictures` stream; the slide drawing/text records must also be rendered or recreated |
| Audio | Five embedded sound records and three supplied linked files: `titlesong.wma`, `rocksong.wma`, and `Ffvictory.mid` |

The counts are an extraction baseline, not yet a statement that every record is visible or reachable in play.

## Python utility decision

- `olefile` plus the project’s MS-PPT record parser is the primary path. It runs in the existing Python 3.14 virtual environment and does not require Winget, the Microsoft Store, Office, or a server at runtime.
- Apache POI is now validated as the non-Aspose reference path for the legacy `.pps`: it exposes slides, page size, pictures, picture instances, shapes, text, hyperlinks, embedded sounds, and slide transition atoms. It does not expose this deck's shape animation atoms through HSLF, so the Python OLE parser remains necessary for OfficeArt/client-data animation/action records.
- The Aspose.Slides experiment has been retired from the repo because evaluation output is watermarked and cannot be on the critical path. The Python 3.13/Aspose temp install and tracked Aspose scripts were removed during cleanup.
- `python-pptx` is not a solution for this input because it targets the modern OOXML `.pptx` format, not PowerPoint 97–2003 binary `.pps`.
- LibreOffice/UNO wrappers are another conversion route, but they still require a separate office application and are not Python-only. They are not a current dependency.

## Updated critical path findings

Complex PowerPoint animation support is now confirmed as required, not optional.

The source file contains PP10 timing-tree records in slide programmable tag binary blobs. These records are accessible with the local Python OLE/MS-PPT parser and are documented in `ANIMATION_EVALUATION.md` and `generated/timing_tree_audit.json`.

Confirmed animation data:

| Critical behavior | Confirmed data source |
| --- | --- |
| Chained/nested animations | 2,407 `RT_TimeExtTimeNodeContainer` records and 2,533 `RT_TimeNode` atoms |
| Click/next/previous animation triggering | `RT_TimeCondition` events `9` and `10` |
| Animation-to-animation triggering | `RT_TimeCondition` events `3` and `4`, referencing start/end of time nodes |
| Child sequence traversal | 135 `RT_TimeSequenceData` atoms |
| Lerp/interpolation mode | 18 `RT_TimeAnimateBehavior` atoms with `calcMode = 1`, documented by Microsoft as linear interpolation |
| Easing-style timing modifiers | 478 `RT_TimeModifier` atoms, including acceleration/deceleration/auto-reverse style modifier types |
| Keyframe values | 35 `RT_TimeAnimationValue` atoms with times at 0 ms, 500 ms, and 1000 ms |
| Text/image visibility and property changes | `RT_TimeVariant` strings such as `style.visibility`, `visible`, `ppt_x`, `ppt_y`, `#ppt_x`, and `#ppt_y` |
| Motion effects | 215 `RT_TimeMotionBehaviorContainer` records |
| Audio commands inside animations | 11 command behavior containers, 18 stop-audio trigger events, and 7 sound visual-target references |
| Target mapping | 1,015 shape animation references, all resolved to Apache POI-known slide shape ids |

This changes the critical path: the browser port cannot rely only on slide screenshots plus hyperlink hotspots. It needs a shape/text/image/audio layer that can be independently animated, plus a JavaScript timing scheduler capable of matching the PowerPoint timing tree.

Critical path work added from the animation findings:

1. Extract every image object instance on every slide as an addressable renderable layer, not only as burned-in slide screenshots. The existing `Pictures` stream extraction proves embedded bitmap payloads are available, but the port still needs per-slide placement, z-order, clipping/cropping, and reuse mapping for each image instance.
2. Preserve text as addressable layer objects where it participates in animation. Burned-in text is acceptable only for static background reference layers; animated text needs extracted text runs, bounds, style, paragraph/character ranges, and timing targets.
3. Decode PP10 timing trees into a normalized manifest that preserves parent/child structure, node ids, sequence rules, trigger conditions, durations, delays, fill/restart behavior, interpolation modes, modifiers, behavior type, keyframes/formulas, target shape/sound ids, and command behavior.
4. Implement a JavaScript animation scheduler that supports PowerPoint-style parallel and sequential time nodes, `OnNext`/`OnPrev`, start/end-of-node triggers, delayed activation, acceleration/deceleration modifiers, linear interpolation, motion paths, visibility/set effects, and audio commands.
5. Validate the decoder and player against selected PowerPoint reference slides before applying it globally. The current audit proves data availability; it does not yet prove playback fidelity.

## Implementation plan

1. **Freeze and inventory the source**
   - [x] Keep the `.pps` and original audio read-only as the reference copy; record the presentation hash and source stream inventory.
   - [x] Produce a repeatable baseline OLE record/slide/sound/media inventory in `generated/inventory.json`.
   - [ ] Resolve persistent slide IDs, title/master/layout records, text runs, z-order, animation/transition records, and all sound-reference semantics.
   - [x] Produce a reviewable JSON report for slides, shape objects, asset inventory, and directed navigation edges (source screen, hotspot rectangle, action, target screen), including non-slide actions.

2. **Build a deterministic legacy-PowerPoint extractor**
   - [x] Add `tools/extract_ppt.py`, which reads the OLE streams with `olefile`, walks the MS-PPT record tree, and writes a generated inventory.
   - [x] Extract PNG bitmap payloads losslessly; decode/convert the single DIB image to PNG; preserve source record IDs, dimensions, and hashes.
   - [x] Parse hyperlink/action records into stable game-screen IDs. Map each action to its owning shape and PowerPoint coordinates; do not infer a “next slide” fallback.
   - [x] Capture PowerPoint text runs and their source shape/bounds metadata.
   - [x] Capture per-slide image/text/shape layer metadata without Aspose using `tools/extract_layers.py`.
   - [x] Validate Apache POI against the original `.pps` with `tools/poi/PoiAudit.java`; record the findings in `POI_EVALUATION.md`.
   - [x] Extract first-pass slide transition and shape animation timing data with `tools/extract_timing.py`.
   - [x] Confirm complex PP10 animation timing trees are present and accessible; record the evidence in `generated/timing_tree_audit.json` and `ANIMATION_EVALUATION.md`.
   - [x] Extract per-slide image instances as separate addressable objects, including source asset id, bounds, z-order, and animation target id.
   - [x] Extract text objects as separate addressable objects, including text values, bounds, z-order, and animation target id.
   - [ ] Improve layer extraction for crop/clip, transforms, fill/line style, text style, paragraph/character target ranges, and hyperlink/action binding on layers.
   - [x] Implement a PP10 timing-tree decoder that emits a JS-ready manifest for nested time nodes, node ids, triggers, sequence data, interpolation modes, acceleration/deceleration/auto-reverse modifiers, behavior containers, keyframes/formulas, motion paths, text/image visibility changes, and sound commands.
   - [ ] Improve font, text wrapping, line geometry, and full visual layering fidelity. Where a legacy drawing construct cannot be represented reliably in HTML, use a generated per-screen raster/SVG layer while keeping hotspots as data-driven browser controls.
   - [x] Convert the linked WMA files to browser-compatible MP3 and Opus assets in `generated/audio/` with `tools/convert_audio.py`.
   - [x] Extract embedded PowerPoint WAV sounds and convert them to browser-compatible MP3 and Opus assets.
   - [ ] Render `Ffvictory.mid` to sampled browser audio with a selected soundfont/synth path.
   - [x] Associate media-shape animation commands with converted embedded audio where the legacy cue id resolves to an embedded sound id; keep unresolved cue ids explicit in `mediaBindings`.
   - [ ] Associate all converted files with their original cue and loop/trigger behavior.

3. **Establish visual reference renders before porting gameplay**
   - [x] Retire the watermarked Aspose renderer path and keep `tools/render_reconstructed.py` on the non-Aspose layer manifest.
   - [x] Generate a first-pass unwatermarked reconstructed raster layer with `tools/render_reconstructed.py` and copy it into `docs/screens/` for browser playability.
   - [ ] Select a publishable non-watermarked render path. Options are a manual Microsoft PowerPoint export or a custom HTML/SVG reconstruction from extracted OfficeArt/POI records.
   - [ ] Render every source slide at a fixed 4:3 resolution using the selected controlled PowerPoint-compatible renderer. If a conversion tool changes visuals, compare it against a short set of reference screenshots from Microsoft PowerPoint and select/document the closest rendering path.
   - Store only the reusable/reference assets needed for development; retain an index that identifies the source slide and render settings for each screen.
   - Review all visible screens and hotspots, including branches that cannot be reached by straightforward play, and annotate special behavior (restart, modal-like reveal, repeated click, hidden object, or non-slide action).

4. **Implement the static web game**
   - [x] Create a dependency-light HTML/CSS/JavaScript app in `docs/` with `index.html`, an asset directory, and generated `game-manifest.json`. Use relative URLs only so the site works at a GitHub project-pages subpath.
   - [x] Display a responsive 4:3 game stage. Render each screen at its original aspect ratio, letterbox it on wider/narrower displays, and position transparent semantic buttons from the extracted hotspot coordinates.
   - [x] Drive basic navigation state exclusively from the manifest: load the start screen, perform only declared slide-link actions, provide restart/mute controls, and keep blank-stage clicks inert.
   - [ ] Support any required non-slide action, reveal/state, and exact restart behavior found during manual review. Do not expose browser history as an in-game action unless the original game has an equivalent control.
   - [x] Include non-Aspose layer data and per-slide image-instance files in `docs/game-manifest.json` for the browser runtime.
   - [x] Include decoded PP10 animation timing-tree data as `docs/animation-manifest.json` and load it in the browser runtime.
   - [x] Implement a layer renderer for separately addressable slide images, text, and shape placeholders; keep screenshot/reconstructed raster layers as static fallback/reference layers.
   - [x] Implement the first JavaScript animation scheduler pass: decoded slide lookup, `OnNext` click queueing, delayed node execution, visibility set effects, and basic fade/dissolve opacity effects.
   - [x] Implement first-pass numeric `ppt_x`/`ppt_y`/`ppt_w`/`ppt_h` animation playback and simple motion-path endpoint transforms from decoded PP10 variants.
   - [x] Implement first-pass animation command audio playback for mapped media-shape `playFrom(0.0)` commands, queued until the first user gesture for browser autoplay compliance.
   - [x] Wire extracted slide transition data into the browser manifest and apply a first-pass browser fade for non-default transitions.
   - [x] Implement first-pass acceleration/deceleration timing functions and auto-reverse handling for CSS-based opacity, property, and simple motion animations.
   - [x] Implement first-pass start/end-of-node trigger scheduling for decoded PP10 condition events 3 and 4.
   - [ ] Implement JavaScript slide transitions and shape/text/image/audio animation playback from the full PP10 timing-tree manifest, using `generated/timing_manifest.json` only as the legacy/simple timing fallback.
   - [ ] Implement PowerPoint-style animation scheduling: parallel/sequential time nodes, chained start/end triggers, `OnNext`/`OnPrev`, delays, fill/restart behavior, linear interpolation, acceleration/deceleration modifiers, auto-reverse, motion paths, visibility/set effects, and audio commands.
   - Start or resume audio only after the first user gesture to satisfy browser autoplay rules; implement explicit loop/stop/replace behavior from the source inventory and degrade gracefully when audio is unavailable.
   - Give invisible hotspots useful accessible labels and focus handling without adding visual controls that alter the original presentation.

5. **Validate fidelity and game logic**
   - Unit-test the extractor: input hash, expected stream/slide/action/asset counts, asset decoding, and absence of unresolved slide targets.
   - [x] Add static-server smoke validation for the generated `docs/` app, manifest, and first screen asset.
   - [x] Add regression verification for the PP10 timing-tree audit: timing blob counts, key timing records, trigger events, modifier types, sequence data, variant strings, and absence of unresolved shape targets.
   - [x] Add regression verification for the decoded PP10 animation manifest: nested time-node count, trigger events, behavior kinds, modifier types, interpolation modes, and layer-target alignment.
   - [x] Add extractor regression tests for per-slide image/text object extraction, including copied image-instance files and resolved animated shape targets.
   - [x] Add site verification for layer-rendering hooks and generated layer image files.
   - [x] Add site verification for first-pass animation scheduler hooks.
   - [x] Add site verification for numeric animation and simple motion playback hooks.
   - [x] Add site verification for extracted transition data on all screens.
   - [x] Add regression verification for embedded audio extraction/conversion and mapped media command bindings.
   - [x] Add site verification for first-pass acceleration/deceleration and auto-reverse runtime hooks.
   - [x] Add site verification for first-pass start/end animation trigger runtime hooks.
   - [ ] Add stricter extractor regression tests for no animated object left only in a burned-in background layer after animation playback starts using layers directly.
   - [ ] Add animation-player tests for representative timing features: linear interpolation, acceleration/deceleration modifiers, chained start/end triggers, `OnNext`/`OnPrev` sequence traversal, visibility changes, motion paths, and sound commands.
   - [x] Add runtime tests that traverse every manifest edge, verify the target screen, confirm background clicks do not advance, and detect unreachable screens or accidental infinite loops.
   - [ ] Maintain a manual playthrough checklist for major branches/endings.
   - Perform visual regression checks at the reference 4:3 size and manual browser QA on current Chromium/Firefox, desktop and mobile viewport sizes. Check text wrapping, hitboxes, z-order, image transparency, and audio behavior.

6. **Package for GitHub Pages**
   - [x] Add a concise README covering local preview, extraction/build commands, current limitations, and GitHub Pages publishing from `docs/`.
   - [x] Build into the repository's `docs/` publish root and verify it with a static HTTP server.
   - [ ] Enable/deploy GitHub Pages after the repository is pushed to GitHub.
   - Commit the source code and required generated game assets; exclude temporary environments, raw intermediate dumps, and nonessential reference renders.

## Technical decisions to make after extraction

- **Screen rendering:** prefer a hybrid approach—faithful per-screen raster/SVG presentation layers plus independently positioned HTML hotspots—unless the structured slide data proves simple enough to recreate losslessly in DOM/CSS. This offers predictable visual fidelity for a 2005 PowerPoint game while preserving real click regions.
- **Audio format:** ship both Ogg/Opus and MP3 after validating browser playback and file sizes. Do not ship WMA as the playable web format.
- **Original behavior vs. browser ergonomics:** preserve all original navigation and no-click-to-advance behavior. Any optional restart, mute, or fullscreen affordance should be deliberately minimal and documented rather than silently changing the game.

## Current research workspace

`_port_analysis_tmp/` is a disposable investigation area. It contains the Python virtual environment, portable JDK, Apache POI bundle, read-only inspection scripts, and the OLE record inventory used for the counts above. The retired Python 3.13/Aspose experiment was removed. This directory is not part of the future web build and should remain ignored before release.
