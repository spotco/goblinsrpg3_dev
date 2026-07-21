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
- Aspose.Slides for Python via .NET is a useful optional renderer: it supports legacy PPT/PPS and can export slide images without Microsoft PowerPoint, but its current Windows wheel requires Python `<3.14`, is proprietary, and evaluation output may be watermarked. It would require a separately installed Python 3.13 environment and a licensing decision.
- `python-pptx` is not a solution for this input because it targets the modern OOXML `.pptx` format, not PowerPoint 97–2003 binary `.pps`.
- LibreOffice/UNO wrappers are another conversion route, but they still require a separate office application and are not Python-only. They are not a current dependency.

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
   - [ ] Capture colors, fonts, fills, lines, and layering. Where a legacy drawing construct cannot be represented reliably in HTML, use a generated per-screen raster/SVG layer while keeping hotspots as data-driven browser controls.
   - [ ] Convert and associate all audio cues in browser-compatible formats.
   - Capture PowerPoint text, colors, fonts, fills, lines, and layering. Where a legacy drawing construct cannot be represented reliably in HTML, use a generated per-screen raster/SVG layer while keeping hotspots as data-driven browser controls.
   - Use the installed `ffmpeg` to create browser-compatible audio (prefer Ogg/Opus and MP3 fallback) from WMA; render the MIDI to an audio asset if browser MIDI playback cannot reproduce it consistently. Associate every converted file with its original cue and loop/trigger behavior.

3. **Establish visual reference renders before porting gameplay**
   - Render every source slide at a fixed 4:3 resolution using a controlled PowerPoint-compatible renderer. If a conversion tool changes visuals, compare it against a short set of reference screenshots from Microsoft PowerPoint and select/document the closest rendering path.
   - Store only the reusable/reference assets needed for development; retain an index that identifies the source slide and render settings for each screen.
   - Review all visible screens and hotspots, including branches that cannot be reached by straightforward play, and annotate special behavior (restart, modal-like reveal, repeated click, hidden object, or non-slide action).

4. **Implement the static web game**
   - Create a dependency-light HTML/CSS/JavaScript app with `index.html`, an asset directory, and a generated `game-manifest.json`. Use relative URLs only so the site works at a GitHub project-pages subpath.
   - Display a responsive 4:3 game stage. Render each screen at its original aspect ratio, letterbox it on wider/narrower displays, and position transparent semantic buttons from the extracted hotspot coordinates.
   - Drive state exclusively from the manifest: load the start screen, perform only declared actions, support required state/restart behavior, and keep blank-stage clicks inert. Do not expose browser history as an in-game action unless the original game has an equivalent control.
   - Start or resume audio only after the first user gesture to satisfy browser autoplay rules; implement explicit loop/stop/replace behavior from the source inventory and degrade gracefully when audio is unavailable.
   - Give invisible hotspots useful accessible labels and focus handling without adding visual controls that alter the original presentation.

5. **Validate fidelity and game logic**
   - Unit-test the extractor: input hash, expected stream/slide/action/asset counts, asset decoding, and absence of unresolved slide targets.
   - Add runtime tests that traverse every manifest edge, verify the target screen, confirm background clicks do not advance, and detect unreachable screens or accidental infinite loops. Maintain a manual playthrough checklist for major branches/endings.
   - Perform visual regression checks at the reference 4:3 size and manual browser QA on current Chromium/Firefox, desktop and mobile viewport sizes. Check text wrapping, hitboxes, z-order, image transparency, and audio behavior.

6. **Package for GitHub Pages**
   - Add a concise README covering local preview, extraction/build commands, attribution/licensing decisions, and GitHub Pages publishing from the chosen branch or Actions workflow.
   - Build into the repository's publish root (or `docs/`, if selected), verify it with a static HTTP server and a project-base-path URL, then enable/deploy GitHub Pages.
   - Commit the source code and required generated game assets; exclude temporary environments, raw intermediate dumps, and nonessential reference renders.

## Technical decisions to make after extraction

- **Screen rendering:** prefer a hybrid approach—faithful per-screen raster/SVG presentation layers plus independently positioned HTML hotspots—unless the structured slide data proves simple enough to recreate losslessly in DOM/CSS. This offers predictable visual fidelity for a 2005 PowerPoint game while preserving real click regions.
- **Audio format:** ship both Ogg/Opus and MP3 after validating browser playback and file sizes. Do not ship WMA as the playable web format.
- **Original behavior vs. browser ergonomics:** preserve all original navigation and no-click-to-advance behavior. Any optional restart, mute, or fullscreen affordance should be deliberately minimal and documented rather than silently changing the game.

## Current research workspace

`_port_analysis_tmp/` is a disposable investigation area. It contains a Python 3.14 virtual environment with `olefile` installed, two read-only inspection scripts, and the OLE record inventory used for the counts above. It is not part of the future web build and should be removed or ignored before release.
