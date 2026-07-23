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
    family_candidates: list[Path] = []
    if "impact" in normalized:
        family_candidates.extend(
            [
                Path("C:/Windows/Fonts/impact.ttf"),
                Path("C:/Windows/Fonts/Impact.ttf"),
            ]
        )
    elif "arial black" in normalized:
        family_candidates.append(Path("C:/Windows/Fonts/ariblk.ttf"))
    elif "broadway" in normalized:
        family_candidates.append(Path("C:/Windows/Fonts/BROADW.TTF"))
        family_candidates.append(Path("C:/Windows/Fonts/broadway.ttf"))
    elif "arial" in normalized:
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
    word_art = bool(layer.get("wordArt"))
    # WordArt fill colors the glyphs, not a rectangular plate behind them.
    if not word_art:
        draw_layer_box(layer_draw, layer, (0, 0, w, h), scale)
    text_style = layer.get("textStyle") or {}
    text_runs = layer.get("textRuns") or []
    first_run = text_runs[0] if isinstance(text_runs, list) and text_runs else {}
    left_inset = round(float(text_style.get("leftInset", 0) if isinstance(text_style, dict) else 0) * scale)
    top_inset = round(float(text_style.get("topInset", 0) if isinstance(text_style, dict) else 0) * scale)
    right_inset = round(float(text_style.get("rightInset", 0) if isinstance(text_style, dict) else 0) * scale)
    family = first_run.get("fontFamily") if isinstance(first_run, dict) else None
    if word_art and isinstance(layer.get("geoText"), dict) and layer["geoText"].get("fontFamily"):
        family = layer["geoText"]["fontFamily"]
    if word_art:
        # Fit WordArt into the shape box (width and height). POI placeholder runs are ~18pt.
        size = max(12, round(h * 0.72))
        font = font_for(size, family if isinstance(family, str) else None)
        measure = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
        while size > 8:
            bbox = measure.multiline_textbbox((0, 0), value, font=font)
            text_w = bbox[2] - bbox[0]
            text_h = bbox[3] - bbox[1]
            if text_w <= max(w - 4, 1) and text_h <= max(h - 4, 1):
                break
            size -= 2
            font = font_for(size, family if isinstance(family, str) else None)
    elif isinstance(first_run, dict) and first_run.get("fontSize") is not None:
        size = max(8, round(float(first_run.get("fontSize", 18)) * scale))
        font = font_for(size, family if isinstance(family, str) else None)
    else:
        size = max(8, round(h * 0.45))
        font = font_for(size, family if isinstance(family, str) else None)
    color = hex_color(
        first_run.get("fontColor") if isinstance(first_run, dict) and isinstance(first_run.get("fontColor"), str) else None,
        (255, 255, 255, 255),
    )
    text_width = max(w - left_inset - right_inset, 1)
    if isinstance(text_style, dict) and text_style.get("wordWrap") is not False and not word_art:
        value = wrap_text_for_box(value, font, text_width)
    if word_art:
        bbox = layer_draw.multiline_textbbox((0, 0), value, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        tx = max(round((w - text_w) / 2 - bbox[0]), 0)
        ty = max(round((h - text_h) / 2 - bbox[1]), 0)
        style = layer.get("style") or {}
        line = style.get("lineColor") if isinstance(style, dict) else None
        if isinstance(line, str) and line.lower().startswith("#fff"):
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, 1), (-1, 1), (1, -1)):
                layer_draw.multiline_text((tx + dx, ty + dy), value, font=font, fill=(255, 255, 255, 255))
        layer_draw.multiline_text((tx, ty), value, font=font, fill=color)
    else:
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


def parse_slide_filter(value: str | None) -> set[int] | None:
    if value is None or not str(value).strip() or str(value).strip().lower() == "all":
        return None
    selected: set[int] = set()
    for part in str(value).split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start_s, end_s = part.split("-", 1)
            start_i, end_i = int(start_s), int(end_s)
            if end_i < start_i:
                start_i, end_i = end_i, start_i
            selected.update(range(start_i, end_i + 1))
        else:
            selected.add(int(part))
    return selected


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--layers", type=Path, default=Path("generated/layers.json"))
    parser.add_argument("--output", type=Path, default=Path("generated/reconstructed"))
    parser.add_argument("--scale", type=float, default=1.0)
    parser.add_argument(
        "--slides",
        type=str,
        default=None,
        help="Optional subset to re-render, e.g. 2,14-16. Merges into existing render_manifest.json.",
    )
    args = parser.parse_args()
    layer_manifest = json.loads(args.layers.read_text(encoding="utf-8"))
    selected = parse_slide_filter(args.slides)

    args.output.mkdir(parents=True, exist_ok=True)
    rendered_entries: dict[int, dict[str, object]] = {}
    # Preserve prior full-deck manifest entries when doing partial re-renders.
    existing_manifest_path = args.output / "render_manifest.json"
    if selected is not None and existing_manifest_path.exists():
        existing = json.loads(existing_manifest_path.read_text(encoding="utf-8"))
        for item in existing.get("slides") or []:
            rendered_entries[int(item["slide"])] = item

    width, height = round(720 * args.scale), round(540 * args.scale)
    rendered_now = 0
    for slide_data in layer_manifest["slides"]:
        slide_number = int(slide_data["slide"])
        if selected is not None and slide_number not in selected:
            continue
        # Source slides use a solid white background fill; only explicit black
        # full-bleed shapes should darken the canvas.
        bg = hex_color(
            slide_data.get("backgroundColor") if isinstance(slide_data.get("backgroundColor"), str) else None,
            (255, 255, 255, 255),
        )
        screen = Image.new("RGBA", (width, height), bg)
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
        rendered_entries[slide_number] = {
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
        rendered_now += 1

    slides = [rendered_entries[key] for key in sorted(rendered_entries)]
    manifest = {
        "format": "goblins-rpg3-render-manifest-v2",
        "renderer": RENDERER_ID,
        "sourceLayerManifest": args.layers.as_posix(),
        "renderSettings": {
            "scale": args.scale,
            "width": width,
            "height": height,
            "background": "#ffffff",
            "path": "custom non-Aspose layer reconstruction",
            "slideFilter": args.slides,
        },
        "summary": {
            "slideCount": len(slides),
            "imageCount": sum(int(item["imageLayerCount"]) for item in slides),
            "textCount": sum(int(item["textLayerCount"]) for item in slides),
            "transformedLayerCount": sum(int(item["transformedLayerCount"]) for item in slides),
            "renderedThisRun": rendered_now,
        },
        "slides": slides,
    }
    (args.output / "render_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(f"Rendered {rendered_now} reconstructed screens to {args.output} (manifest entries={len(slides)})")


if __name__ == "__main__":
    main()
