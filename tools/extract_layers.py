"""Build a non-Aspose slide layer manifest from Apache POI audit output.

The browser port needs image/text objects as separately addressable layers so
PowerPoint animations can target them. This script consumes the POI audit TSV
for slide shape bounds/text/picture instances, the embedded asset inventory for
source image payloads, and the PP10 timing audit for known animation targets.
It writes a generated layer manifest and copies every picture instance to its
own per-slide file.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


def parse_poi_audit(path: Path) -> tuple[dict[str, object], dict[int, list[dict[str, object]]]]:
    metadata: dict[str, object] = {}
    shapes: dict[tuple[int, int], dict[str, object]] = {}
    by_slide: dict[int, list[dict[str, object]]] = {}

    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if not line:
            continue
        parts = line.split("\t")
        key = parts[0]
        if "=" in key and len(parts) == 1:
            name, value = key.split("=", 1)
            metadata[name] = value
            continue
        if key == "SHAPE":
            slide = int(parts[1])
            z_order = int(parts[2])
            shape_id = int(parts[3])
            shape = {
                "slide": slide,
                "zOrder": z_order,
                "shapeId": shape_id,
                "kind": parts[4],
                "name": parts[5],
                "bounds": {
                    "x": float(parts[6]),
                    "y": float(parts[7]),
                    "width": float(parts[8]),
                    "height": float(parts[9]),
                },
            }
            shapes[(slide, shape_id)] = shape
            by_slide.setdefault(slide, []).append(shape)
        elif key == "PICTURE":
            slide = int(parts[1])
            shape_id = int(parts[3])
            shape = shapes.get((slide, shape_id))
            if shape is None:
                continue
            shape["picture"] = {
                "pictureIndex": int(parts[4]),
                "pictureType": parts[5],
                "sourceBytes": int(parts[6]),
            }
        elif key == "TEXT":
            slide = int(parts[1])
            shape_id = int(parts[3])
            shape = shapes.get((slide, shape_id))
            if shape is None:
                continue
            shape["text"] = parts[4].replace("\\r", "\r").replace("\\n", "\n") if len(parts) >= 5 else ""

    return metadata, by_slide


def normal_bounds(bounds: dict[str, float], width: float, height: float) -> dict[str, object]:
    x = bounds["x"]
    y = bounds["y"]
    w = bounds["width"]
    h = bounds["height"]
    return {
        "x": x / width,
        "y": y / height,
        "width": w / width,
        "height": h / height,
        "points": bounds,
    }


def copy_picture_instance(
    source_asset: Path,
    output_root: Path,
    slide: int,
    shape_id: int,
    asset_suffix: str,
) -> Path:
    slide_dir = output_root / f"slide-{slide:03d}"
    slide_dir.mkdir(parents=True, exist_ok=True)
    target = slide_dir / f"shape-{shape_id}.{asset_suffix}"
    shutil.copy2(source_asset, target)
    return target


def resolve_picture_asset(
    embedded_assets: list[dict[str, object]],
    picture_index: int,
    source_bytes: int,
) -> dict[str, object]:
    # HSLFPictureShape#getPictureIndex is usually 1-based against the bitmap
    # list, but this deck has at least one non-extracted/non-bitmap picture in
    # POI's numbering near the end. Prefer nearby index candidates whose byte
    # count matches the POI picture payload, then fall back to a unique byte-size
    # match.
    candidates = []
    for asset_index in (picture_index - 1, picture_index - 2, picture_index):
        if 0 <= asset_index < len(embedded_assets):
            asset = embedded_assets[asset_index]
            if int(asset["bytes"]) == source_bytes:
                candidates.append(asset)
    if candidates:
        return candidates[0]

    by_size = [asset for asset in embedded_assets if int(asset["bytes"]) == source_bytes]
    if len(by_size) == 1:
        return by_size[0]

    raise ValueError(
        f"Could not resolve POI picture index {picture_index} with source byte count {source_bytes}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, default=Path("generated/inventory.json"))
    parser.add_argument("--poi-audit", type=Path, default=Path("generated/poi_audit.tsv"))
    parser.add_argument("--timing-tree", type=Path, default=Path("generated/timing_tree_audit.json"))
    parser.add_argument("--output", type=Path, default=Path("generated/layers.json"))
    parser.add_argument("--asset-output", type=Path, default=Path("generated/slide-assets"))
    args = parser.parse_args()

    inventory = json.loads(args.inventory.read_text(encoding="utf-8"))
    timing_tree = json.loads(args.timing_tree.read_text(encoding="utf-8"))
    metadata, shapes_by_slide = parse_poi_audit(args.poi_audit)

    page_size = str(metadata.get("pageSize", "720x540")).split("x")
    page_width = float(page_size[0])
    page_height = float(page_size[1])
    embedded_assets = inventory["embedded_assets"]
    animation_targets = {
        int(slide): set(map(int, shape_ids))
        for slide, shape_ids in timing_tree.get("animationTargets", {}).get("shapeTargetsBySlide", {}).items()
    }

    slides: list[dict[str, object]] = []
    image_instance_count = 0
    text_layer_count = 0
    animated_layer_count = 0

    for slide in range(1, int(metadata.get("slides", len(shapes_by_slide))) + 1):
        layers: list[dict[str, object]] = []
        for shape in sorted(shapes_by_slide.get(slide, []), key=lambda item: int(item["zOrder"])):
            shape_id = int(shape["shapeId"])
            animated = shape_id in animation_targets.get(slide, set())
            base = {
                "id": f"slide-{slide:03d}-shape-{shape_id}",
                "slide": slide,
                "shapeId": shape_id,
                "zOrder": shape["zOrder"],
                "kind": shape["kind"],
                "name": shape["name"],
                "bounds": normal_bounds(shape["bounds"], page_width, page_height),
                "animated": animated,
            }
            if animated:
                animated_layer_count += 1
            if "picture" in shape:
                picture = shape["picture"]
                asset = resolve_picture_asset(
                    embedded_assets,
                    int(picture["pictureIndex"]),
                    int(picture["sourceBytes"]),
                )
                source_asset = Path(asset["path"])
                suffix = source_asset.suffix.lstrip(".") or "png"
                instance_path = copy_picture_instance(source_asset, args.asset_output, slide, shape_id, suffix)
                layer = {
                    **base,
                    "type": "image",
                    "assetId": asset["id"],
                    "sourceAssetPath": asset["path"],
                    "instancePath": instance_path.as_posix(),
                    "pictureIndex": picture["pictureIndex"],
                    "pictureType": picture["pictureType"],
                    "sourceBytes": picture["sourceBytes"],
                }
                image_instance_count += 1
            elif "text" in shape:
                layer = {**base, "type": "text", "text": shape.get("text", "")}
                text_layer_count += 1
            else:
                layer = {**base, "type": "shape"}
            layers.append(layer)
        slides.append({"slide": slide, "layers": layers})

    report = {
        "format": "goblins-rpg3-layer-manifest-v1",
        "source": inventory["source"],
        "pageSize": {"width": page_width, "height": page_height, "units": "points"},
        "coordinateSource": "Apache POI HSLF shape anchors",
        "assetOutput": args.asset_output.as_posix(),
        "slides": slides,
        "summary": {
            "slides": len(slides),
            "layers": sum(len(slide["layers"]) for slide in slides),
            "imageInstances": image_instance_count,
            "textLayers": text_layer_count,
            "animatedLayers": animated_layer_count,
            "animatedShapeTargets": sum(len(targets) for targets in animation_targets.values()),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(
        f"Wrote {args.output} with {image_instance_count} image instances, "
        f"{text_layer_count} text layers, {animated_layer_count} animated layers"
    )


if __name__ == "__main__":
    main()
