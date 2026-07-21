"""Render screens without an Office renderer or evaluation watermark.

This is a development fallback: it composites extracted picture shapes, solid
fills, and source text runs into a 4:3 raster screen. It intentionally keeps
the source geometry in the manifest so a later browser renderer can replace
the raster layer with DOM/SVG when the visual review is complete.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def font_for(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for candidate in (
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("C:/Windows/Fonts/tahoma.ttf"),
        Path("C:/Windows/Fonts/segoeui.ttf"),
    ):
        if candidate.exists():
            return ImageFont.truetype(str(candidate), max(size, 1))
    return ImageFont.load_default()


def source_bounds(bounds: list[int] | None, scale: float) -> tuple[float, float, float, float] | None:
    if not bounds or len(bounds) != 4:
        return None
    # OfficeArt text/anchor order is top, left, right, bottom in master units.
    top, left, right, bottom = [value / 8.0 * scale for value in bounds]
    if right <= left or bottom <= top:
        return None
    return left, top, right, bottom


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, default=Path("generated/inventory.json"))
    parser.add_argument("--layout", type=Path, default=Path("generated/layout.json"))
    parser.add_argument("--assets", type=Path, default=Path("generated/assets"))
    parser.add_argument("--output", type=Path, default=Path("generated/reconstructed"))
    parser.add_argument("--scale", type=float, default=1.0)
    args = parser.parse_args()
    inventory = json.loads(args.inventory.read_text(encoding="utf-8"))
    layout = json.loads(args.layout.read_text(encoding="utf-8"))
    assets = {asset["id"]: Path(asset["path"]) for asset in inventory["embedded_assets"]}
    text_by_slide: dict[int, list[dict[str, object]]] = {}
    for text in inventory["text_runs"]:
        slide = text.get("slide")
        if slide is not None:
            text_by_slide.setdefault(int(slide), []).append(text)

    args.output.mkdir(parents=True, exist_ok=True)
    manifest = []
    width, height = round(720 * args.scale), round(540 * args.scale)
    for slide_data in layout:
        slide_number = int(slide_data["slide"])
        screen = Image.new("RGBA", (width, height), (0, 0, 0, 255))
        draw = ImageDraw.Draw(screen)
        # Composite in source z-order.
        for shape in slide_data["shapes"]:
            x = round(float(shape["x"]) * args.scale)
            y = round(float(shape["y"]) * args.scale)
            w = round(float(shape["width"]) * args.scale)
            h = round(float(shape["height"]) * args.scale)
            box = (x, y, x + w, y + h)
            fill = shape.get("fill") or {}
            if fill.get("type") == 1 and fill.get("solid_color"):
                color = fill["solid_color"]
                draw.rectangle(
                    box,
                    fill=(int(color.get("r", 0)), int(color.get("g", 0)), int(color.get("b", 0)), 255),
                )
            asset_id = shape.get("asset_id")
            if asset_id:
                source_asset = assets.get(asset_id)
                if source_asset:
                    with Image.open(source_asset) as image:
                        image = image.convert("RGBA").resize((max(w, 1), max(h, 1)), Image.Resampling.LANCZOS)
                        screen.alpha_composite(image, (x, y))
        # Draw source text after picture/fill layers. The source bounds are in
        # PowerPoint master units and are normalized in source_bounds().
        for text in text_by_slide.get(slide_number, []):
            box = source_bounds(text.get("bounds"), args.scale)
            value = str(text.get("text", "")).replace("\x00", "").replace("\r", "")
            if box is None or not value.strip():
                continue
            left, top, right, bottom = box
            size = max(8, round((bottom - top) * 0.72))
            draw.multiline_text((round(left), round(top)), value, font=font_for(size), fill=(255, 255, 255, 255))
        output = args.output / f"slide-{slide_number:03d}.png"
        screen.convert("RGB").save(output, format="PNG", optimize=True)
        manifest.append({"slide": slide_number, "path": output.as_posix(), "width": width, "height": height})
    (args.output / "render_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(f"Rendered {len(manifest)} reconstructed screens to {args.output}")


if __name__ == "__main__":
    main()
