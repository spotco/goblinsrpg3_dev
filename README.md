# Goblins RPG 3 browser port

This repository contains a static browser port of the original PowerPoint 97-2003 `.pps` game source.

The current playable build lives in `docs/`, which is suitable for GitHub Pages configured to publish from the `docs` folder on the `master` branch. The build uses reconstructed unwatermarked slide PNGs plus transparent HTML hotspots generated from the PowerPoint hyperlink/action records.

## Local preview

Run a static server from the repository root:

```powershell
python -m http.server 8765 --directory docs
```

Then open:

```text
http://127.0.0.1:8765/
```

Add `?debug=1` to show hotspot rectangles.

## Rebuild generated data

The extraction tools use Python packages listed in `tools/requirements.txt`.

```powershell
python tools/extract_ppt.py "goblins3 v.1.0 LAUNCH.pps"
python tools/convert_audio.py
python tools/build_game_manifest.py
python tools/verify_inventory.py generated/inventory.json
python tools/verify_site.py
```

The optional layout/rendering tools require the separate Python 3.13/Aspose.Slides setup noted in `PLAN.md`:

```powershell
python tools/extract_layout_aspose.py "goblins3 v.1.0 LAUNCH.pps"
python tools/render_reconstructed.py
python tools/build_game_manifest.py
```

## Current limitations

- The screen PNGs are a first-pass reconstruction, not a verified pixel-perfect PowerPoint export.
- `Ffvictory.mid` is identified in the audio manifest but still needs rendering through a MIDI synth/soundfont.
- Audio cue timing/loop behavior still needs to be associated with the extracted PowerPoint action records.
- Manual playthrough and visual review are still required before calling this final.
