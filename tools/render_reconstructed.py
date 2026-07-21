"""Render screens from the non-Aspose layer manifest.

This is a development fallback: it composites extracted picture instances and
text layers into a 4:3 raster screen. It intentionally keeps the source
geometry in the manifest so the browser renderer/animation player can use the
same addressable layer data directly.
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


def pixel_box(bounds: dict[str, object], scale: float) -> tuple[int, int, int, int]:
    points = bounds["points"]
    x = round(float(points["x"]) * scale)
    y = round(float(points["y"]) * scale)
    w = round(float(points["width"]) * scale)
    h = round(float(points["height"]) * scale)
    return x, y, max(w, 1), max(h, 1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--layers", type=Path, default=Path("generated/layers.json"))
    parser.add_argument("--output", type=Path, default=Path("generated/reconstructed"))
    parser.add_argument("--scale", type=float, default=1.0)
    args = parser.parse_args()
    layer_manifest = json.loads(args.layers.read_text(encoding="utf-8"))

    args.output.mkdir(parents=True, exist_ok=True)
    manifest = []
    width, height = round(720 * args.scale), round(540 * args.scale)
    for slide_data in layer_manifest["slides"]:
        slide_number = int(slide_data["slide"])
        screen = Image.new("RGBA", (width, height), (0, 0, 0, 255))
        draw = ImageDraw.Draw(screen)
        # Composite in source z-order.
        for layer in slide_data["layers"]:
            x, y, w, h = pixel_box(layer["bounds"], args.scale)
            if layer["type"] == "image":
                source_asset = Path(layer["instancePath"])
                if source_asset.exists():
                    with Image.open(source_asset) as image:
                        image = image.convert("RGBA").resize((w, h), Image.Resampling.LANCZOS)
                        screen.alpha_composite(image, (x, y))
            elif layer["type"] == "text":
                value = str(layer.get("text", "")).replace("\x00", "").replace("\r", "")
                if not value.strip():
                    continue
                size = max(8, round(h * 0.72))
                draw.multiline_text((x, y), value, font=font_for(size), fill=(255, 255, 255, 255))
            else:
                continue
        output = args.output / f"slide-{slide_number:03d}.png"
        screen.convert("RGB").save(output, format="PNG", optimize=True)
        manifest.append({"slide": slide_number, "path": output.as_posix(), "width": width, "height": height})
    (args.output / "render_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(f"Rendered {len(manifest)} reconstructed screens to {args.output}")


if __name__ == "__main__":
    main()
