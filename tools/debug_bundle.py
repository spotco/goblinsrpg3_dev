"""Package a minimal debug capture for one slide.

Creates generated/debug/bundles/slide-NNN/ with the autopsy JSON, PNG copies,
and a short README agents can follow.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from debug_lib import REPO_ROOT, build_slide_report, write_json


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("slide", type=int)
    parser.add_argument("--repo", type=Path, default=REPO_ROOT)
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args()

    report = build_slide_report(args.slide, repo_root=args.repo)
    bundle_dir = args.output_dir or (args.repo / "generated" / "debug" / "bundles" / f"slide-{args.slide:03d}")
    if bundle_dir.exists():
        shutil.rmtree(bundle_dir)
    bundle_dir.mkdir(parents=True, exist_ok=True)

    write_json(bundle_dir / "report.json", report)

    docs_png = args.repo / "docs" / "screens" / f"slide-{args.slide:03d}.png"
    gen_png = args.repo / "generated" / "reconstructed" / f"slide-{args.slide:03d}.png"
    if docs_png.exists():
        shutil.copy2(docs_png, bundle_dir / "docs-screen.png")
    if gen_png.exists():
        shutil.copy2(gen_png, bundle_dir / "generated-screen.png")

    # Copy up to a handful of image layer assets for offline inspection.
    copied = 0
    for layer in report.get("layers") or []:
        if layer.get("type") != "image" or not layer.get("instancePath"):
            continue
        rel = Path(str(layer["instancePath"]))
        for candidate in (args.repo / "docs" / rel, args.repo / rel):
            if candidate.exists():
                target = bundle_dir / "layers" / rel.name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(candidate, target)
                copied += 1
                break
        if copied >= 12:
            break

    readme = f"""# Debug bundle: slide {args.slide:03d}

## Quick start

1. Serve the site: `python tools/serve_docs.py --port 8765 --directory docs`
2. Open: http://127.0.0.1:8765/?debug=1&slide={args.slide}
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
python tools/debug_slide.py {args.slide}
python tools/probe_mechanic.py all --slide {args.slide}
python tools/audit_visual_risks.py --slides {args.slide}
```

Risk summary: total={report['riskCounts']['total']} high={report['riskCounts']['high']} medium={report['riskCounts']['medium']}
"""
    (bundle_dir / "README.md").write_text(readme, encoding="utf-8", newline="\n")
    print(f"Wrote debug bundle to {bundle_dir}")
    print(f"Risks: {report['riskCounts']}")


if __name__ == "__main__":
    main()
