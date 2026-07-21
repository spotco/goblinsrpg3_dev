"""Regression checks for the first extraction baseline."""

from __future__ import annotations

import json
from pathlib import Path


EXPECTED_SOURCE_SHA256 = "5ef9ef5169b09119fd3e9cd7015fc8f25ff78bf104041cbc1ebbca13be45fa93"


def main() -> None:
    inventory_path = Path("generated/inventory.json")
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    assert inventory["source"]["sha256"] == EXPECTED_SOURCE_SHA256
    assert len(inventory["slides"]) == 201
    assert inventory["record_type_counts"]["1006"] == 201
    assert inventory["record_type_counts"]["4083"] == 217
    assert inventory["record_type_counts"]["4055"] == 194
    assert len(inventory["hyperlinks"]) == 194
    assert len(inventory["objects"]) == 1591
    assert len(inventory["interactive_actions"]) == 217
    assert len(inventory["navigation_edges"]) == 194
    assert all(action["shape_id"] is not None for action in inventory["interactive_actions"])
    assert all(action["bounds"] is not None for action in inventory["interactive_actions"])
    assert all(edge["target_slide"] for edge in inventory["navigation_edges"])
    assert len(inventory["embedded_assets"]) == 116
    assert sum(asset["encoding"] == "png" for asset in inventory["embedded_assets"]) == 115
    assert sum(asset["encoding"] == "dib->png" for asset in inventory["embedded_assets"]) == 1
    for asset in inventory["embedded_assets"]:
        path = Path(asset["path"])
        assert path.exists(), path
        assert path.stat().st_size == asset["bytes"], path
    print("inventory verification passed")


if __name__ == "__main__":
    main()
