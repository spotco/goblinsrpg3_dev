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


def hex_color(value: str | None, fallback: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    if not value:
        return fallback
    text = value.lstrip("#")
    if len(text) == 8:
        return tuple(int(text[index : index + 2], 16) for index in range(0, 8, 2))  # type: ignore[return-value]
    if len(text) == 6:
        r, g, b = (int(text[index : index + 2], 16) for index in range(0, 6, 2))
        return r, g, b, 255
    return fallback


def font_for(size: int, family: str | None = None) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    normalized = (family or "").lower()
    family_candidates = []
    if "arial" in normalized:
        family_candidates.append(Path("C:/Windows/Fonts/arial.ttf"))
    elif "tahoma" in normalized:
        family_candidates.append(Path("C:/Windows/Fonts/tahoma.ttf"))
    elif "times" in normalized:
        family_candidates.append(Path("C:/Windows/Fonts/times.ttf"))
    for candidate in (
        *family_candidates,
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


def draw_layer_box(draw: ImageDraw.ImageDraw, layer: dict[str, object], box: tuple[int, int, int, int], scale: float) -> None:
    x, y, w, h = box
    style = layer.get("style") or {}
    if not isinstance(style, dict):
        return
    fill = hex_color(style.get("fillColor") if isinstance(style.get("fillColor"), str) else None, (0, 0, 0, 0))
    line = hex_color(style.get("lineColor") if isinstance(style.get("lineColor"), str) else None, (0, 0, 0, 0))
    line_width = max(round(float(style.get("lineWidth") or 0) * scale), 1)
    if fill[3] > 0:
        draw.rectangle((x, y, x + w, y + h), fill=fill)
    if line[3] > 0 and float(style.get("lineWidth") or 0) > 0:
        draw.rectangle((x, y, x + w, y + h), outline=line, width=line_width)


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
            draw_layer_box(draw, layer, (x, y, w, h), args.scale)
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
                text_style = layer.get("textStyle") or {}
                text_runs = layer.get("textRuns") or []
                first_run = text_runs[0] if isinstance(text_runs, list) and text_runs else {}
                left_inset = round(float(text_style.get("leftInset", 0) if isinstance(text_style, dict) else 0) * args.scale)
                top_inset = round(float(text_style.get("topInset", 0) if isinstance(text_style, dict) else 0) * args.scale)
                size = max(8, round(float(first_run.get("fontSize", 18) if isinstance(first_run, dict) else 18) * args.scale))
                family = first_run.get("fontFamily") if isinstance(first_run, dict) else None
                color = hex_color(
                    first_run.get("fontColor") if isinstance(first_run, dict) and isinstance(first_run.get("fontColor"), str) else None,
                    (255, 255, 255, 255),
                )
                draw.multiline_text((x + left_inset, y + top_inset), value, font=font_for(size, family), fill=color)
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
