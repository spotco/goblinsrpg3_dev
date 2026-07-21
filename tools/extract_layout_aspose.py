"""Extract unwatermarked shape/layout metadata with Aspose.Slides.

Aspose's full-slide render is evaluation-watermarked, but its object model can
still provide useful geometry, fill/line metadata, and original picture bytes.
This output is data for a later renderer; it is not itself a playable screen.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import aspose.slides as slides


def color_info(color) -> dict[str, int] | None:
    if color is None:
        return None
    return {
        channel: int(getattr(color, channel, 0) or 0)
        for channel in ("r", "g", "b", "a")
    }


def fill_info(fill) -> dict[str, object] | None:
    if fill is None:
        return None
    result: dict[str, object] = {"type": int(fill.fill_type)}
    try:
        result["solid_color"] = color_info(fill.solid_fill_color)
    except Exception:
        result["solid_color"] = None
    return result


def line_info(line) -> dict[str, object] | None:
    if line is None:
        return None
    width = float(line.width)
    result: dict[str, object] = {"width": width if math.isfinite(width) else None}
    try:
        result["fill"] = fill_info(line.fill_format)
    except Exception:
        result["fill"] = None
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--inventory", type=Path, default=Path("generated/inventory.json"))
    parser.add_argument("--output", type=Path, default=Path("generated/layout.json"))
    args = parser.parse_args()
    inventory = json.loads(args.inventory.read_text(encoding="utf-8"))
    assets_by_hash = {asset["sha256"]: asset["id"] for asset in inventory["embedded_assets"]}

    presentation = slides.Presentation(str(args.source))
    result: list[dict[str, object]] = []
    try:
        for slide_number, slide in enumerate(presentation.slides, start=1):
            shapes = []
            for index, shape in enumerate(slide.shapes):
                item: dict[str, object] = {
                    "index": index,
                    "class": type(shape).__name__,
                    "name": shape.name,
                    "x": float(shape.x),
                    "y": float(shape.y),
                    "width": float(shape.width),
                    "height": float(shape.height),
                    "z_order": index,
                    "fill": fill_info(getattr(shape, "fill_format", None)),
                    "line": line_info(getattr(shape, "line_format", None)),
                }
                text_frame = getattr(shape, "text_frame", None)
                if text_frame is not None and text_frame.text:
                    text = str(text_frame.text)
                    item["aspose_text"] = None if "evaluation version limitation" in text else text
                    item["text_is_evaluation_limited"] = "evaluation version limitation" in text
                picture_format = getattr(shape, "picture_format", None)
                if picture_format is not None:
                    image_bytes = bytes(picture_format.picture.image.binary_data)
                    image_hash = hashlib.sha256(image_bytes).hexdigest()
                    item["image_sha256"] = image_hash
                    item["asset_id"] = assets_by_hash.get(image_hash)
                shapes.append(item)
            result.append({"slide": slide_number, "shapes": shapes})
    finally:
        close = getattr(presentation, "close", None)
        if close is not None:
            close()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8", newline="\n"
    )
    print(f"Extracted layout metadata for {len(result)} slides to {args.output}")


if __name__ == "__main__":
    main()
