"""Render screens from the non-Aspose layer manifest.

This is a development fallback: it composites extracted picture instances and
text layers into a 4:3 raster screen. It intentionally keeps the source
geometry in the manifest so the browser renderer/animation player can use the
same addressable layer data directly.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


RENDERER_ID = "goblins-layer-reconstruction-v2"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def transformed_layer_image(layer_image: Image.Image, layer: dict[str, object]) -> Image.Image:
    transform = layer.get("transform") or {}
    if not isinstance(transform, dict):
        return layer_image
    result = layer_image
    if transform.get("flipHorizontal"):
        result = result.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    if transform.get("flipVertical"):
        result = result.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    rotation = float(transform.get("rotation") or 0)
    if rotation:
        # PowerPoint positive rotation is clockwise; Pillow positive rotation is
        # counter-clockwise.  Keep the original layer center by rendering in a
        # transparent expanded box and later pasting around the same center.
        result = result.rotate(-rotation, expand=True, resample=Image.Resampling.BICUBIC)
    return result


def paste_centered(screen: Image.Image, layer_image: Image.Image, box: tuple[int, int, int, int]) -> None:
    x, y, w, h = box
    cx = x + w / 2
    cy = y + h / 2
    px = round(cx - layer_image.width / 2)
    py = round(cy - layer_image.height / 2)
    screen.alpha_composite(layer_image, (px, py))


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


def wrap_text_for_box(value: str, font: ImageFont.FreeTypeFont | ImageFont.ImageFont, width: int) -> str:
    if width <= 4:
        return value
    output_lines = []
    measure = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    for source_line in value.splitlines() or [""]:
        if not source_line:
            output_lines.append("")
            continue
        words = source_line.split(" ")
        current = words[0]
        for word in words[1:]:
            candidate = f"{current} {word}"
            bbox = measure.textbbox((0, 0), candidate, font=font)
            if bbox[2] - bbox[0] <= width:
                current = candidate
            else:
                output_lines.append(current)
                current = word
        output_lines.append(current)
    return "\n".join(output_lines)


def render_text_layer(layer: dict[str, object], box: tuple[int, int, int, int], scale: float) -> Image.Image | None:
    _x, _y, w, h = box
    value = str(layer.get("text", "")).replace("\x00", "").replace("\r", "")
    if not value.strip():
        return None
    layer_image = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    layer_draw = ImageDraw.Draw(layer_image)
    draw_layer_box(layer_draw, layer, (0, 0, w, h), scale)
    text_style = layer.get("textStyle") or {}
    text_runs = layer.get("textRuns") or []
    first_run = text_runs[0] if isinstance(text_runs, list) and text_runs else {}
    left_inset = round(float(text_style.get("leftInset", 0) if isinstance(text_style, dict) else 0) * scale)
    top_inset = round(float(text_style.get("topInset", 0) if isinstance(text_style, dict) else 0) * scale)
    right_inset = round(float(text_style.get("rightInset", 0) if isinstance(text_style, dict) else 0) * scale)
    size = max(8, round(float(first_run.get("fontSize", 18) if isinstance(first_run, dict) else 18) * scale))
    family = first_run.get("fontFamily") if isinstance(first_run, dict) else None
    font = font_for(size, family)
    color = hex_color(
        first_run.get("fontColor") if isinstance(first_run, dict) and isinstance(first_run.get("fontColor"), str) else None,
        (255, 255, 255, 255),
    )
    text_width = max(w - left_inset - right_inset, 1)
    if isinstance(text_style, dict) and text_style.get("wordWrap") is not False:
        value = wrap_text_for_box(value, font, text_width)
    layer_draw.multiline_text((left_inset, top_inset), value, font=font, fill=color)
    return layer_image


def render_image_layer(layer: dict[str, object], box: tuple[int, int, int, int], scale: float) -> Image.Image | None:
    _x, _y, w, h = box
    layer_image = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    layer_draw = ImageDraw.Draw(layer_image)
    draw_layer_box(layer_draw, layer, (0, 0, w, h), scale)
    source_asset = Path(layer["instancePath"])
    if source_asset.exists():
        with Image.open(source_asset) as image:
            image = image.convert("RGBA").resize((w, h), Image.Resampling.LANCZOS)
            layer_image.alpha_composite(image, (0, 0))
    return layer_image


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--layers", type=Path, default=Path("generated/layers.json"))
    parser.add_argument("--output", type=Path, default=Path("generated/reconstructed"))
    parser.add_argument("--scale", type=float, default=1.0)
    args = parser.parse_args()
    layer_manifest = json.loads(args.layers.read_text(encoding="utf-8"))

    args.output.mkdir(parents=True, exist_ok=True)
    slides = []
    width, height = round(720 * args.scale), round(540 * args.scale)
    for slide_data in layer_manifest["slides"]:
        slide_number = int(slide_data["slide"])
        screen = Image.new("RGBA", (width, height), (0, 0, 0, 255))
        draw = ImageDraw.Draw(screen)
        # Composite in source z-order.
        layer_count = 0
        image_count = 0
        text_count = 0
        transformed_count = 0
        for layer in slide_data["layers"]:
            x, y, w, h = pixel_box(layer["bounds"], args.scale)
            layer_image = None
            if layer["type"] == "image":
                layer_image = render_image_layer(layer, (x, y, w, h), args.scale)
                image_count += 1
            elif layer["type"] == "text":
                layer_image = render_text_layer(layer, (x, y, w, h), args.scale)
                text_count += 1
            else:
                layer_image = Image.new("RGBA", (w, h), (0, 0, 0, 0))
                draw_layer_box(ImageDraw.Draw(layer_image), layer, (0, 0, w, h), args.scale)
            if layer_image is None:
                continue
            transformed = transformed_layer_image(layer_image, layer)
            transform = layer.get("transform") or {}
            if isinstance(transform, dict) and (
                transform.get("rotation") or transform.get("flipHorizontal") or transform.get("flipVertical")
            ):
                transformed_count += 1
            paste_centered(screen, transformed, (x, y, w, h))
            layer_count += 1
        output = args.output / f"slide-{slide_number:03d}.png"
        screen.convert("RGB").save(output, format="PNG", optimize=True)
        slides.append(
            {
                "slide": slide_number,
                "path": output.as_posix(),
                "width": width,
                "height": height,
                "bytes": output.stat().st_size,
                "sha256": sha256(output),
                "layerCount": layer_count,
                "imageLayerCount": image_count,
                "textLayerCount": text_count,
                "transformedLayerCount": transformed_count,
            }
        )
    manifest = {
        "format": "goblins-rpg3-render-manifest-v2",
        "renderer": RENDERER_ID,
        "sourceLayerManifest": args.layers.as_posix(),
        "renderSettings": {
            "scale": args.scale,
            "width": width,
            "height": height,
            "background": "#000000",
            "path": "custom non-Aspose layer reconstruction",
        },
        "summary": {
            "slideCount": len(slides),
            "imageCount": sum(item["imageLayerCount"] for item in slides),
            "textCount": sum(item["textLayerCount"] for item in slides),
            "transformedLayerCount": sum(item["transformedLayerCount"] for item in slides),
        },
        "slides": slides,
    }
    (args.output / "render_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(f"Rendered {len(slides)} reconstructed screens to {args.output}")


if __name__ == "__main__":
    main()
