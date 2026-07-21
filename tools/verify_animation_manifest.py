"""Regression checks for the generated PP10 animation manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", nargs="?", type=Path, default=Path("generated/animations.json"))
    parser.add_argument("--layers", type=Path, default=Path("generated/layers.json"))
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    layers = json.loads(args.layers.read_text(encoding="utf-8"))
    summary = manifest["summary"]

    assert manifest["format"] == "goblins-rpg3-animation-manifest-v1"
    assert summary["slidesWithAnimations"] == 197
    assert summary["timeNodeContainers"] == 2407
    assert summary["recordCounts"]["RT_TimeNode"] == 2533
    assert summary["recordCounts"]["RT_TimeCondition"] == 2093
    assert summary["recordCounts"]["RT_TimeModifier"] == 478
    assert summary["recordCounts"]["RT_TimeSequenceData"] == 135
    assert summary["recordCounts"]["RT_TimeVariant"] == 6078
    assert summary["shapeTargets"] == 567
    assert summary["soundTargets"] == 1
    assert summary["unresolvedShapeTargets"] == []
    assert summary["conditionEvents"] == {"0": 1538, "1": 130, "3": 7, "4": 108, "9": 146, "10": 146, "11": 18}
    assert summary["modifierTypes"] == {"0": 12, "3": 229, "4": 227, "5": 10}
    assert summary["animateCalcModes"] == {"1": 18}

    layer_targets = {
        (int(slide["slide"]), int(layer["shapeId"]))
        for slide in layers["slides"]
        for layer in slide["layers"]
        if layer.get("animated")
    }
    manifest_targets = set()
    for slide in manifest["slides"]:
        slide_number = int(slide["slide"])
        stack = list(slide["rootTimeNodes"])
        while stack:
            node = stack.pop()
            for target in node.get("targets", []):
                if target.get("kind") == "shape":
                    manifest_targets.add((slide_number, int(target["shapeId"])))
            stack.extend(node.get("children", []))
    assert manifest_targets == layer_targets
    print("animation manifest verification passed")


if __name__ == "__main__":
    main()
