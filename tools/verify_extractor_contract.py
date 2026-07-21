"""Verify the legacy PowerPoint extractor contract."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from PIL import Image


EXPECTED_SOURCE_SHA256 = "5ef9ef5169b09119fd3e9cd7015fc8f25ff78bf104041cbc1ebbca13be45fa93"


def fail(message: str) -> None:
    raise SystemExit(message)


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("goblins3 v.1.0 LAUNCH.pps"))
    parser.add_argument("--inventory", type=Path, default=Path("generated/inventory.json"))
    parser.add_argument("--report", type=Path, default=Path("generated/extractor_contract.json"))
    args = parser.parse_args()

    if not args.source.exists():
        fail(f"source presentation is missing: {args.source}")
    source_sha256 = hashlib.sha256(args.source.read_bytes()).hexdigest()
    if source_sha256 != EXPECTED_SOURCE_SHA256:
        fail(f"unexpected source sha256: {source_sha256}")

    inventory = load_json(args.inventory)
    if inventory.get("source", {}).get("sha256") != EXPECTED_SOURCE_SHA256:
        fail("inventory source hash does not match expected source")

    expected_counts = {
        "slides": 201,
        "interactiveActions": 217,
        "navigationEdges": 194,
        "hyperlinks": 194,
        "objects": 1591,
        "textRuns": 357,
        "embeddedAssets": 116,
        "pngAssets": 115,
        "dibAssets": 1,
    }
    actual_counts = {
        "slides": len(inventory.get("slides", [])),
        "interactiveActions": len(inventory.get("interactive_actions", [])),
        "navigationEdges": len(inventory.get("navigation_edges", [])),
        "hyperlinks": len(inventory.get("hyperlinks", [])),
        "objects": len(inventory.get("objects", [])),
        "textRuns": len(inventory.get("text_runs", [])),
        "embeddedAssets": len(inventory.get("embedded_assets", [])),
        "pngAssets": sum(asset.get("encoding") == "png" for asset in inventory.get("embedded_assets", [])),
        "dibAssets": sum(asset.get("encoding") == "dib->png" for asset in inventory.get("embedded_assets", [])),
    }
    if actual_counts != expected_counts:
        fail(f"extractor counts changed: expected {expected_counts}, found {actual_counts}")

    unresolved_edges = [edge for edge in inventory.get("navigation_edges", []) if not edge.get("target_slide")]
    if unresolved_edges:
        fail(f"navigation edges with unresolved target slides: {unresolved_edges[:5]}")

    malformed_actions = [
        action
        for action in inventory.get("interactive_actions", [])
        if action.get("shape_id") is None or action.get("bounds") is None
    ]
    if malformed_actions:
        fail(f"interactive actions missing shape/bounds context: {malformed_actions[:5]}")

    decoded_assets = []
    for asset in inventory.get("embedded_assets", []):
        path = Path(asset["path"])
        if not path.exists():
            fail(f"embedded asset file is missing: {path}")
        if path.stat().st_size != int(asset["bytes"]):
            fail(f"embedded asset size changed: {path}")
        with Image.open(path) as image:
            width, height = image.size
            mode = image.mode
        if width != int(asset["width"]) or height != int(asset["height"]) or mode != asset["mode"]:
            fail(f"embedded asset decode metadata changed: {path}")
        decoded_assets.append(
            {
                "id": asset["id"],
                "path": asset["path"],
                "width": width,
                "height": height,
                "mode": mode,
                "encoding": asset["encoding"],
            }
        )

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(
            {
                "format": "goblins-rpg3-extractor-contract-v1",
                "source": {
                    "path": args.source.as_posix(),
                    "sha256": source_sha256,
                },
                "counts": actual_counts,
                "decodedAssetSample": decoded_assets[:20],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print("extractor contract verification passed")


if __name__ == "__main__":
    main()
