"""Shared helpers for slide autopsy, visual-risk audit, and mechanic probes."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_optional_string(value: str) -> str | None:
    if value == "" or value.lower() == "null":
        return None
    return value


def clean_geotext(value: str) -> str:
    text = value.replace("\x00", "").strip()
    if len(text) >= 2 and text.startswith("+") and text.endswith("+"):
        text = text[1:-1]
    return text


def parse_slide_list(value: str | None) -> set[int] | None:
    """Parse ``2,14-16,20`` into a set of slide numbers. None means all."""
    if value is None or str(value).strip() == "" or str(value).strip().lower() == "all":
        return None
    slides: set[int] = set()
    for part in str(value).split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start_s, end_s = part.split("-", 1)
            start_i = int(start_s)
            end_i = int(end_s)
            if end_i < start_i:
                start_i, end_i = end_i, start_i
            slides.update(range(start_i, end_i + 1))
        else:
            slides.add(int(part))
    return slides


def parse_poi_audit(path: Path) -> tuple[dict[str, str], dict[int, list[dict[str, Any]]], dict[int, dict[str, Any]]]:
    metadata: dict[str, str] = {}
    shapes: dict[tuple[int, int], dict[str, Any]] = {}
    by_slide: dict[int, list[dict[str, Any]]] = {}
    backgrounds: dict[int, dict[str, Any]] = {}

    if not path.exists():
        return metadata, by_slide, backgrounds

    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if not line:
            continue
        parts = line.split("\t")
        key = parts[0]
        if "=" in key and len(parts) == 1:
            name, value = key.split("=", 1)
            metadata[name] = value
            continue
        if key == "SLIDEBG":
            slide = int(parts[1])
            backgrounds[slide] = {
                "fillType": int(parts[2]),
                "foregroundColor": parse_optional_string(parts[3]),
                "backgroundColor": parse_optional_string(parts[4]),
                "picture": parse_optional_string(parts[5]) if len(parts) > 5 else None,
            }
            continue
        if key == "SHAPE":
            slide = int(parts[1])
            shape = {
                "slide": slide,
                "zOrder": int(parts[2]),
                "shapeId": int(parts[3]),
                "kind": parts[4],
                "name": parts[5],
                "bounds": {
                    "x": float(parts[6]),
                    "y": float(parts[7]),
                    "width": float(parts[8]),
                    "height": float(parts[9]),
                },
            }
            shapes[(slide, int(parts[3]))] = shape
            by_slide.setdefault(slide, []).append(shape)
        elif key == "GEOMETRY":
            shape = shapes.get((int(parts[1]), int(parts[3])))
            if shape is not None:
                shape["shapeType"] = parse_optional_string(parts[4])
                shape["rotation"] = float(parts[5])
                shape["flipHorizontal"] = parts[6].lower() == "true"
                shape["flipVertical"] = parts[7].lower() == "true"
                shape["placeholder"] = parts[8].lower() == "true"
        elif key == "STYLE":
            shape = shapes.get((int(parts[1]), int(parts[3])))
            if shape is not None:
                shape["style"] = {
                    "fillColor": parse_optional_string(parts[4]),
                    "lineColor": parse_optional_string(parts[5]),
                    "lineWidth": float(parts[6]),
                    "lineDash": parse_optional_string(parts[7]),
                }
        elif key == "TEXT":
            shape = shapes.get((int(parts[1]), int(parts[3])))
            if shape is not None:
                shape["text"] = (
                    "" if len(parts) < 5 or parts[4] == "null" else parts[4].replace("\\r", "\r").replace("\\n", "\n")
                )
        elif key == "GEOTEXT":
            shape = shapes.get((int(parts[1]), int(parts[3])))
            if shape is not None:
                raw = "" if len(parts) < 5 or parts[4] == "null" else parts[4].replace("\\r", "\r").replace("\\n", "\n")
                shape["geoText"] = {
                    "rawUnicode": raw,
                    "unicode": clean_geotext(raw),
                    "fontFamily": parse_optional_string(parts[5]) if len(parts) > 5 else None,
                }
        elif key == "PICTURE":
            shape = shapes.get((int(parts[1]), int(parts[3])))
            if shape is not None:
                shape["picture"] = {
                    "pictureIndex": int(parts[4]),
                    "pictureType": parts[5],
                    "sourceBytes": int(parts[6]),
                }
    return metadata, by_slide, backgrounds


def layer_area(layer: dict[str, Any]) -> float:
    bounds = layer.get("bounds") or {}
    return float(bounds.get("width") or 0) * float(bounds.get("height") or 0)


def color_luma(color: str | None) -> float | None:
    if not color or not isinstance(color, str):
        return None
    text = color.lstrip("#")
    if len(text) < 6:
        return None
    try:
        r = int(text[0:2], 16)
        g = int(text[2:4], 16)
        b = int(text[4:6], 16)
    except ValueError:
        return None
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255.0


def is_word_art_type(shape_type: str | None) -> bool:
    if not shape_type:
        return False
    if not shape_type.startswith("TEXT_"):
        return False
    return shape_type not in {"TEXT_BOX", "TEXT_PLAIN"}


def png_stats(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"exists": False, "path": path.as_posix()}
    info: dict[str, Any] = {
        "exists": True,
        "path": path.as_posix(),
        "bytes": path.stat().st_size,
    }
    try:
        from PIL import Image

        with Image.open(path) as image:
            rgb = image.convert("RGB")
            width, height = rgb.size
            info["width"] = width
            info["height"] = height
            samples = {
                "topLeft": rgb.getpixel((0, 0)),
                "center": rgb.getpixel((width // 2, height // 2)),
                "bottomRight": rgb.getpixel((width - 1, height - 1)),
            }
            info["samples"] = samples
            # Subsample for speed on 720x540.
            step = max(width * height // 4000, 1)
            pixels = list(rgb.getdata())
            nonblack = sum(1 for index, (r, g, b) in enumerate(pixels) if index % step == 0 and r + g + b > 30)
            sampled = max((len(pixels) + step - 1) // step, 1)
            info["nonBlackSampleRatio"] = round(nonblack / sampled, 4)
    except Exception as error:  # noqa: BLE001 - diagnostic helper
        info["error"] = str(error)
    return info


def collect_screen_risks(
    *,
    slide: int,
    screen: dict[str, Any] | None,
    layers_slide: dict[str, Any] | None,
    poi_shapes: list[dict[str, Any]] | None,
    background: dict[str, Any] | None,
    png_path: Path | None,
    animation_slide: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    risks: list[dict[str, Any]] = []

    def add(code: str, severity: str, message: str, evidence: dict[str, Any] | None = None) -> None:
        risks.append(
            {
                "slide": slide,
                "code": code,
                "severity": severity,
                "message": message,
                "evidence": evidence or {},
            }
        )

    layers = (screen or {}).get("layers") or (layers_slide or {}).get("layers") or []
    hotspots = (screen or {}).get("hotspots") or []
    bg_color = (screen or {}).get("backgroundColor") or (layers_slide or {}).get("backgroundColor")
    if background and not bg_color:
        bg_color = background.get("foregroundColor")

    # POI vs layers WordArt / empty text
    for shape in poi_shapes or []:
        shape_id = shape.get("shapeId")
        poi_text = str(shape.get("text") or "").strip()
        geo = shape.get("geoText") or {}
        geo_text = str(geo.get("unicode") or "").strip()
        shape_type = shape.get("shapeType")
        if geo_text and not poi_text:
            layer = next((item for item in layers if item.get("shapeId") == shape_id), None)
            layer_text = str((layer or {}).get("text") or "").strip()
            if not layer_text:
                add(
                    "empty_text_wordart_unrecovered",
                    "high",
                    f"Shape {shape_id} has geotext {geo_text!r} but layer text is empty",
                    {"shapeId": shape_id, "geoText": geo, "shapeType": shape_type},
                )
            elif not (layer or {}).get("wordArt"):
                add(
                    "wordart_not_flagged",
                    "medium",
                    f"Shape {shape_id} has geotext but layer.wordArt is false",
                    {"shapeId": shape_id, "layerText": layer_text},
                )
        if is_word_art_type(shape_type) and not poi_text and not geo_text:
            add(
                "wordart_no_text_source",
                "medium",
                f"WordArt-like shape {shape_id} ({shape_type}) has no POI text and no geotext",
                {"shapeId": shape_id, "shapeType": shape_type, "name": shape.get("name")},
            )

    # Layer content coverage
    max_area = max((layer_area(layer) for layer in layers), default=0.0)
    image_layers = [layer for layer in layers if layer.get("type") == "image"]
    text_layers = [layer for layer in layers if layer.get("type") == "text"]
    non_empty_text = [layer for layer in text_layers if str(layer.get("text") or "").strip()]
    large_images = [layer for layer in image_layers if layer_area(layer) >= 0.5]
    if not large_images and max_area < 0.2 and len(non_empty_text) <= 2:
        add(
            "sparse_visual_coverage",
            "medium",
            "Slide has no large image layer and only sparse text/shapes",
            {
                "layerCount": len(layers),
                "imageLayers": len(image_layers),
                "nonEmptyTextLayers": len(non_empty_text),
                "maxLayerArea": round(max_area, 4),
            },
        )

    # Contrast heuristics for text on light backgrounds
    bg_luma = color_luma(bg_color if isinstance(bg_color, str) else None)
    if bg_luma is not None and bg_luma > 0.8:
        for layer in non_empty_text:
            runs = layer.get("textRuns") or []
            first = runs[0] if runs else {}
            font_color = first.get("fontColor") if isinstance(first, dict) else None
            text_luma = color_luma(font_color if isinstance(font_color, str) else None)
            if text_luma is not None and text_luma > 0.75:
                add(
                    "low_contrast_text",
                    "low",
                    f"Light text on light slide background for shape {layer.get('shapeId')}",
                    {
                        "shapeId": layer.get("shapeId"),
                        "text": str(layer.get("text") or "")[:80],
                        "fontColor": font_color,
                        "backgroundColor": bg_color,
                    },
                )

    # Hotspots
    for hotspot in hotspots:
        target = hotspot.get("targetSlide")
        if hotspot.get("action") == "hyperlink" and target == slide:
            add(
                "self_hyperlink",
                "high",
                f"Hotspot {hotspot.get('id')} hyperlinks to the same slide",
                {"hotspotId": hotspot.get("id"), "shapeId": hotspot.get("shapeId"), "targetSlide": target},
            )
        bounds = hotspot.get("bounds") or {}
        area = float(bounds.get("width") or 0) * float(bounds.get("height") or 0)
        if hotspot.get("clickable") and area <= 0:
            add(
                "zero_area_hotspot",
                "high",
                f"Clickable hotspot {hotspot.get('id')} has zero area",
                {"hotspotId": hotspot.get("id"), "bounds": bounds},
            )
        if hotspot.get("behaviorStatus") in {"unresolved_media", "missing_media_binding"}:
            add(
                "unresolved_media",
                "high",
                f"Hotspot {hotspot.get('id')} media is unresolved",
                {
                    "hotspotId": hotspot.get("id"),
                    "behaviorStatus": hotspot.get("behaviorStatus"),
                    "mediaBindingId": hotspot.get("mediaBindingId"),
                },
            )
        if area > 0 and area < 0.0005 and hotspot.get("clickable"):
            add(
                "tiny_hotspot",
                "low",
                f"Hotspot {hotspot.get('id')} is very small",
                {"hotspotId": hotspot.get("id"), "area": area},
            )

    # Image instance paths
    for layer in image_layers:
        instance = layer.get("instancePath")
        if not instance:
            add(
                "image_layer_missing_path",
                "high",
                f"Image layer {layer.get('id')} has no instancePath",
                {"layerId": layer.get("id"), "shapeId": layer.get("shapeId")},
            )
            continue
        candidates = [REPO_ROOT / str(instance), REPO_ROOT / "docs" / str(instance), REPO_ROOT / "generated" / str(instance)]
        # instancePath in docs manifest is relative to docs/
        docs_rel = REPO_ROOT / "docs" / str(instance)
        gen_rel = REPO_ROOT / str(instance)
        if not docs_rel.exists() and not gen_rel.exists():
            # also try stripping docs/ prefix duplicates
            if not any(path.exists() for path in candidates):
                add(
                    "missing_layer_image_file",
                    "high",
                    f"Image file missing for layer {layer.get('id')}",
                    {"instancePath": instance, "checked": [docs_rel.as_posix(), gen_rel.as_posix()]},
                )

    # Animation targets without layers
    if animation_slide:
        layer_shape_ids = {int(layer["shapeId"]) for layer in layers if layer.get("shapeId") is not None}

        def walk(node: dict[str, Any]) -> None:
            for target in node.get("targets") or []:
                shape_id = target.get("shapeId") if isinstance(target, dict) else None
                if shape_id is None and isinstance(target, dict):
                    # visual element targets sometimes use targetId / spid
                    shape_id = target.get("targetId") or target.get("spid")
                if shape_id is None:
                    continue
                try:
                    shape_id_int = int(shape_id)
                except (TypeError, ValueError):
                    continue
                if shape_id_int not in layer_shape_ids:
                    add(
                        "animation_target_missing_layer",
                        "high",
                        f"Animation targets shape {shape_id_int} with no layer",
                        {"shapeId": shape_id_int, "nodeId": node.get("id")},
                    )
            for child in node.get("children") or []:
                if isinstance(child, dict):
                    walk(child)

        for root in animation_slide.get("rootTimeNodes") or []:
            if isinstance(root, dict):
                walk(root)

    # PNG stats heuristics
    if png_path is not None:
        stats = png_stats(png_path)
        if not stats.get("exists"):
            add("missing_screen_png", "high", "Reconstructed/screen PNG is missing", {"path": png_path.as_posix()})
        else:
            ratio = stats.get("nonBlackSampleRatio")
            if isinstance(ratio, (int, float)) and ratio < 0.02 and not large_images:
                add(
                    "nearly_empty_png",
                    "medium",
                    "Screen PNG is nearly empty (few non-black samples)",
                    {"path": stats.get("path"), "nonBlackSampleRatio": ratio, "bytes": stats.get("bytes")},
                )

    # Layers hide PNG note when both exist and layers sparse
    if layers and large_images == [] and png_path and png_path.exists():
        add(
            "layers_mode_hides_png",
            "info",
            "Runtime hides the composite PNG when any layers exist; sparse layers may look incomplete",
            {"layerCount": len(layers), "png": png_path.as_posix()},
        )

    return risks


def load_game_manifest(path: Path = REPO_ROOT / "docs" / "game-manifest.json") -> dict[str, Any]:
    return load_json(path)


def load_layers_manifest(path: Path = REPO_ROOT / "generated" / "layers.json") -> dict[str, Any]:
    return load_json(path)


def load_animation_manifest(
    path: Path | None = None,
) -> dict[str, Any] | None:
    candidates = [
        path,
        REPO_ROOT / "docs" / "animation-manifest.json",
        REPO_ROOT / "generated" / "animations.json",
    ]
    for candidate in candidates:
        if candidate and candidate.exists():
            return load_json(candidate)
    return None


def screen_by_slide(manifest: dict[str, Any], slide: int) -> dict[str, Any] | None:
    for screen in manifest.get("screens") or []:
        if int(screen.get("slide") or 0) == slide:
            return screen
    return None


def layers_by_slide(layers_manifest: dict[str, Any], slide: int) -> dict[str, Any] | None:
    for entry in layers_manifest.get("slides") or []:
        if int(entry.get("slide") or 0) == slide:
            return entry
    return None


def animation_by_slide(animation_manifest: dict[str, Any] | None, slide: int) -> dict[str, Any] | None:
    if not animation_manifest:
        return None
    for entry in animation_manifest.get("slides") or []:
        if int(entry.get("slide") or 0) == slide:
            return entry
    return None


def build_slide_report(
    slide: int,
    *,
    repo_root: Path = REPO_ROOT,
    game_manifest_path: Path | None = None,
    layers_path: Path | None = None,
    poi_audit_path: Path | None = None,
    animation_path: Path | None = None,
) -> dict[str, Any]:
    game_manifest = load_game_manifest(game_manifest_path or repo_root / "docs" / "game-manifest.json")
    layers_manifest = load_layers_manifest(layers_path or repo_root / "generated" / "layers.json")
    animation_manifest = load_animation_manifest(animation_path)
    _, poi_by_slide, backgrounds = parse_poi_audit(poi_audit_path or repo_root / "generated" / "poi_audit.tsv")

    screen = screen_by_slide(game_manifest, slide)
    layers_slide = layers_by_slide(layers_manifest, slide)
    animation_slide = animation_by_slide(animation_manifest, slide)
    poi_shapes = poi_by_slide.get(slide, [])
    background = backgrounds.get(slide)

    docs_png = repo_root / "docs" / "screens" / f"slide-{slide:03d}.png"
    gen_png = repo_root / "generated" / "reconstructed" / f"slide-{slide:03d}.png"
    png_path = docs_png if docs_png.exists() else gen_png

    risks = collect_screen_risks(
        slide=slide,
        screen=screen,
        layers_slide=layers_slide,
        poi_shapes=poi_shapes,
        background=background,
        png_path=png_path,
        animation_slide=animation_slide,
    )

    layers = (screen or {}).get("layers") or (layers_slide or {}).get("layers") or []
    type_counts: dict[str, int] = {}
    for layer in layers:
        kind = str(layer.get("type") or "unknown")
        type_counts[kind] = type_counts.get(kind, 0) + 1

    return {
        "format": "goblins-rpg3-slide-debug-v1",
        "slide": slide,
        "screenId": f"slide-{slide:03d}",
        "paths": {
            "gameManifest": (game_manifest_path or repo_root / "docs" / "game-manifest.json").as_posix(),
            "layers": (layers_path or repo_root / "generated" / "layers.json").as_posix(),
            "poiAudit": (poi_audit_path or repo_root / "generated" / "poi_audit.tsv").as_posix(),
            "docsPng": docs_png.as_posix(),
            "generatedPng": gen_png.as_posix(),
        },
        "background": background,
        "backgroundColor": (screen or {}).get("backgroundColor") or (layers_slide or {}).get("backgroundColor"),
        "transition": (screen or {}).get("transition"),
        "hotspots": (screen or {}).get("hotspots") or [],
        "layerSummary": {
            "count": len(layers),
            "typeCounts": type_counts,
            "animated": sum(1 for layer in layers if layer.get("animated")),
            "wordArt": sum(1 for layer in layers if layer.get("wordArt")),
            "maxArea": round(max((layer_area(layer) for layer in layers), default=0.0), 4),
        },
        "layers": [
            {
                "id": layer.get("id"),
                "shapeId": layer.get("shapeId"),
                "type": layer.get("type"),
                "kind": layer.get("kind"),
                "shapeType": layer.get("shapeType"),
                "name": layer.get("name"),
                "text": layer.get("text"),
                "wordArt": layer.get("wordArt"),
                "geoText": layer.get("geoText"),
                "instancePath": layer.get("instancePath"),
                "animated": layer.get("animated"),
                "bounds": layer.get("bounds"),
                "style": layer.get("style"),
            }
            for layer in layers
        ],
        "poiShapes": [
            {
                "shapeId": shape.get("shapeId"),
                "kind": shape.get("kind"),
                "name": shape.get("name"),
                "shapeType": shape.get("shapeType"),
                "text": shape.get("text"),
                "geoText": shape.get("geoText"),
                "picture": shape.get("picture"),
                "style": shape.get("style"),
                "bounds": shape.get("bounds"),
            }
            for shape in poi_shapes
        ],
        "animation": {
            "available": animation_slide is not None,
            "rootCount": len((animation_slide or {}).get("rootTimeNodes") or []),
            "recordCounts": (animation_slide or {}).get("recordCounts"),
        },
        "png": png_stats(png_path),
        "risks": risks,
        "riskCounts": {
            "total": len(risks),
            "high": sum(1 for risk in risks if risk["severity"] == "high"),
            "medium": sum(1 for risk in risks if risk["severity"] == "medium"),
            "low": sum(1 for risk in risks if risk["severity"] == "low"),
            "info": sum(1 for risk in risks if risk["severity"] == "info"),
        },
        "suggestedTools": [
            f"python tools/debug_slide.py {slide}",
            f"python tools/probe_mechanic.py wordart --slide {slide}",
            f"python tools/probe_mechanic.py hotspots --slide {slide}",
            f"python tools/probe_mechanic.py animation --slide {slide}",
            f"python tools/probe_mechanic.py media --slide {slide}",
            f"python tools/probe_mechanic.py background --slide {slide}",
            f"http://127.0.0.1:8765/?debug=1&slide={slide}",
        ],
    }


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8", newline="\n")
