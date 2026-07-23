"""Build a single-slide autopsy report for faster port debugging.

Reads POI audit, layers, game-manifest, animation data, and reconstructed PNG
stats, then writes a structured risk report under generated/debug/.
"""

from __future__ import annotations

import argparse
import webbrowser
from pathlib import Path

from debug_lib import REPO_ROOT, build_slide_report, write_json


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("slide", type=int, help="1-based slide number")
    parser.add_argument("--repo", type=Path, default=REPO_ROOT)
    parser.add_argument("--output-dir", type=Path, default=None, help="Defaults to <repo>/generated/debug")
    parser.add_argument("--open", action="store_true", help="Print browser debug URL and open if possible")
    parser.add_argument("--print", dest="print_report", action="store_true", help="Print summary to stdout")
    args = parser.parse_args()

    report = build_slide_report(args.slide, repo_root=args.repo)
    output_dir = args.output_dir or (args.repo / "generated" / "debug")
    output_path = output_dir / f"slide-{args.slide:03d}.json"
    write_json(output_path, report)

    summary = (
        f"slide {args.slide}: risks={report['riskCounts']['total']} "
        f"(high={report['riskCounts']['high']}, medium={report['riskCounts']['medium']}, "
        f"low={report['riskCounts']['low']}, info={report['riskCounts']['info']}) "
        f"layers={report['layerSummary']['count']} hotspots={len(report['hotspots'])}"
    )
    print(summary)
    print(f"Wrote {output_path}")
    for risk in report["risks"]:
        print(f"  [{risk['severity']}] {risk['code']}: {risk['message']}")

    url = f"http://127.0.0.1:8765/?debug=1&slide={args.slide}"
    print(f"Browser debug URL: {url}")
    if args.open:
        try:
            webbrowser.open(url)
        except Exception as error:  # noqa: BLE001
            print(f"Could not open browser: {error}")

    if args.print_report:
        import json

        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
