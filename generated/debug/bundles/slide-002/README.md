# Debug bundle: slide 002

## Quick start

1. Serve the site: `python tools/serve_docs.py --port 8765 --directory docs`
2. Open: http://127.0.0.1:8765/?debug=1&slide=2
3. In the browser console:
   - `goblinsRpg3Debug.dumpScreen()`
   - `goblinsRpg3Debug.listProblems()`
   - `goblinsRpg3Debug.snapshot()`

## Offline reports in this folder

- `report.json` — autopsy + risks
- `docs-screen.png` / `generated-screen.png` — composites if present
- `layers/` — sample image layer files

## Follow-up commands

```powershell
python tools/debug_slide.py 2
python tools/probe_mechanic.py all --slide 2
python tools/audit_visual_risks.py --slides 2
```

Risk summary: total=4 high=1 medium=1
