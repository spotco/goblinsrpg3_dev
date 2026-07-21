"""Verify Apache POI audit output against extracted timing data."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--poi-audit", type=Path, default=Path("generated/poi_audit.tsv"))
    parser.add_argument("--timing", type=Path, default=Path("generated/timing_manifest.json"))
    args = parser.parse_args()

    lines = args.poi_audit.read_text(encoding="utf-8-sig").splitlines()
    timing = json.loads(args.timing.read_text(encoding="utf-8"))

    poi_shapes = set()
    counters = {
        "slides": 0,
        "pictures": 0,
        "pictureInstances": 0,
        "sounds": 0,
        "transitions": 0,
        "links": 0,
    }
    for line in lines:
        parts = line.split("\t")
        key = parts[0]
        if key == "slides=201":
            counters["slides"] = 201
        elif key == "pictures=116":
            counters["pictures"] = 116
        elif key == "sounds=5":
            counters["sounds"] = 5
        elif key == "SHAPE":
            poi_shapes.add((int(parts[1]), int(parts[3])))
        elif key == "PICTURE":
            counters["pictureInstances"] += 1
        elif key == "TRANSITION":
            counters["transitions"] += 1
        elif key in {"TEXTLINK", "SHAPELINK"}:
            counters["links"] += 1

    animations = timing["animations"]
    missing_animation_shapes = [
        (animation["slide"], animation["shapeId"])
        for animation in animations
        if (animation["slide"], animation["shapeId"]) not in poi_shapes
    ]
    assert counters["slides"] == 201, counters
    assert counters["pictures"] == 116, counters
    assert counters["sounds"] == 5, counters
    assert counters["pictureInstances"] == 532, counters
    assert counters["transitions"] == 201, counters
    assert counters["links"] == 194, counters
    assert len(timing["transitions"]) == 201
    assert len(animations) == 341
    assert not missing_animation_shapes, missing_animation_shapes[:10]
    print("POI audit verification passed")


if __name__ == "__main__":
    main()
