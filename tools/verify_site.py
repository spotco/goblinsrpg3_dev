"""Validate generated static site files without launching a browser."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def fail(message: str) -> None:
    raise SystemExit(message)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", type=Path, default=Path("docs"))
    args = parser.parse_args()

    manifest_path = args.site / "game-manifest.json"
    if not (args.site / "index.html").exists():
        fail("docs/index.html is missing")
    if not manifest_path.exists():
        fail("docs/game-manifest.json is missing")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    screens = manifest.get("screens", [])
    if len(screens) != 201:
        fail(f"expected 201 screens, found {len(screens)}")

    screen_ids = {screen["id"] for screen in screens}
    if manifest.get("startScreen") not in screen_ids:
        fail("start screen is not present in screens")

    missing_files = []
    missing_targets = []
    zero_hotspots = []
    enabled_count = 0
    for screen in screens:
        image_path = args.site / screen["image"]
        if not image_path.exists():
            missing_files.append(screen["image"])
        for hotspot in screen.get("hotspots", []):
            if not hotspot.get("enabled"):
                continue
            enabled_count += 1
            bounds = hotspot.get("bounds") or {}
            if bounds.get("width", 0) <= 0 or bounds.get("height", 0) <= 0:
                zero_hotspots.append(hotspot["id"])
            target = f"slide-{int(hotspot['targetSlide']):03d}"
            if target not in screen_ids:
                missing_targets.append(hotspot["id"])

    if missing_files:
        fail(f"missing screen image files: {missing_files[:5]}")
    if missing_targets:
        fail(f"hotspots target missing screens: {missing_targets[:5]}")
    if zero_hotspots:
        fail(f"enabled hotspots with zero area: {zero_hotspots[:5]}")
    if enabled_count != 194:
        fail(f"expected 194 enabled navigation hotspots, found {enabled_count}")

    print("site verification passed")


if __name__ == "__main__":
    main()
