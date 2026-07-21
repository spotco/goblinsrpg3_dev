"""Build the browser runtime manifest from extracted PowerPoint inventory."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


ACTION_NAMES = {
    0: "none",
    1: "macro",
    2: "run_program",
    3: "jump",
    4: "hyperlink",
    5: "ole",
    6: "media",
}


def clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, value))


def normalize_bounds(bounds: list[int], width: int, height: int) -> dict[str, object]:
    # OfficeArt client anchors in this file are top,left,right,bottom.
    top, left, right, bottom = bounds
    x1 = clamp(min(left, right), 0, width)
    x2 = clamp(max(left, right), 0, width)
    y1 = clamp(min(top, bottom), 0, height)
    y2 = clamp(max(top, bottom), 0, height)
    return {
        "raw": bounds,
        "x": x1 / width,
        "y": y1 / height,
        "width": (x2 - x1) / width,
        "height": (y2 - y1) / height,
        "clipped": [x1, y1, x2, y2],
    }


def build_screens(
    inventory: dict[str, object],
    screen_dir: str,
    layers_by_slide: dict[int, list[dict[str, object]]] | None = None,
) -> list[dict[str, object]]:
    presentation = inventory["presentation"]
    width = int(presentation["width"])
    height = int(presentation["height"])
    actions_by_slide: dict[int, list[dict[str, object]]] = {}
    for action in inventory["interactive_actions"]:
        slide = int(action["slide"])
        bounds = action.get("bounds")
        action_code = int(action.get("action_code", 0))
        hotspot: dict[str, object] = {
            "id": f"s{slide:03d}-a{action['record_offset']}",
            "shapeId": action.get("shape_id"),
            "actionCode": action_code,
            "action": ACTION_NAMES.get(action_code, f"unknown_{action_code}"),
            "soundRef": action.get("sound_ref"),
            "hyperlinkId": action.get("hyperlink_id"),
            "targetSlide": action.get("target_slide"),
            "targetLabel": action.get("target_label"),
            "flagsHex": action.get("flags_hex"),
            "label": action.get("target_label") or ACTION_NAMES.get(action_code, "action"),
            "enabled": bool(action.get("target_slide")),
        }
        if bounds:
            hotspot["bounds"] = normalize_bounds(bounds, width, height)
        actions_by_slide.setdefault(slide, []).append(hotspot)

    screens: list[dict[str, object]] = []
    for index, _slide in enumerate(inventory["slides"], start=1):
        screen = {
            "id": f"slide-{index:03d}",
            "slide": index,
            "image": f"{screen_dir}/slide-{index:03d}.png",
            "hotspots": actions_by_slide.get(index, []),
        }
        if layers_by_slide is not None:
            screen["layers"] = layers_by_slide.get(index, [])
        screens.append(screen)
    return screens


def copy_screens(screen_source: Path | None, output_dir: Path, screen_dir: str) -> str:
    if screen_source is None or not screen_source.exists():
        return "pending_publishable_renders"
    screen_output = output_dir / screen_dir
    screen_output.mkdir(parents=True, exist_ok=True)
    copied = 0
    for source in sorted(screen_source.glob("slide-*.png")):
        shutil.copy2(source, screen_output / source.name)
        copied += 1
    return "custom_reconstruction" if copied else "pending_publishable_renders"


def copy_audio(audio_manifest_path: Path, output_dir: Path) -> list[dict[str, object]]:
    if not audio_manifest_path.exists():
        return []
    audio_output = output_dir / "assets" / "audio"
    audio_output.mkdir(parents=True, exist_ok=True)
    result = []
    audio_manifest = json.loads(audio_manifest_path.read_text(encoding="utf-8"))
    for entry in audio_manifest:
        copied_outputs = []
        for output in entry.get("outputs", []):
            source_path = Path(output["path"])
            target_path = audio_output / source_path.name
            shutil.copy2(source_path, target_path)
            copied = dict(output)
            copied["path"] = f"assets/audio/{target_path.name}"
            copied_outputs.append(copied)
        copied_entry = dict(entry)
        copied_entry["outputs"] = copied_outputs
        result.append(copied_entry)
    return result


def copy_layers(layer_manifest_path: Path, output_dir: Path) -> tuple[dict[int, list[dict[str, object]]] | None, dict[str, object]]:
    if not layer_manifest_path.exists():
        return None, {"status": "missing"}

    layer_manifest = json.loads(layer_manifest_path.read_text(encoding="utf-8"))
    copied_images = 0
    layers_by_slide: dict[int, list[dict[str, object]]] = {}
    layer_output_root = output_dir / "assets" / "slide-assets"
    for slide in layer_manifest.get("slides", []):
        slide_number = int(slide["slide"])
        copied_layers = []
        for layer in slide.get("layers", []):
            copied_layer = dict(layer)
            if copied_layer.get("type") == "image":
                source_path = Path(str(copied_layer["instancePath"]))
                target_path = layer_output_root / f"slide-{slide_number:03d}" / source_path.name
                target_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_path, target_path)
                copied_layer["instancePath"] = target_path.relative_to(output_dir).as_posix()
                copied_images += 1
            copied_layers.append(copied_layer)
        layers_by_slide[slide_number] = copied_layers

    return layers_by_slide, {
        "status": "available",
        "summary": layer_manifest.get("summary", {}),
        "copiedImageInstances": copied_images,
    }


def copy_animation_manifest(animation_manifest_path: Path, output_dir: Path) -> dict[str, object]:
    if not animation_manifest_path.exists():
        return {"status": "missing"}
    animation_manifest = json.loads(animation_manifest_path.read_text(encoding="utf-8"))
    target = output_dir / "animation-manifest.json"
    target.write_text(json.dumps(animation_manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
    return {
        "status": "available",
        "path": target.relative_to(output_dir).as_posix(),
        "summary": animation_manifest.get("summary", {}),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, default=Path("generated/inventory.json"))
    parser.add_argument("--audio-manifest", type=Path, default=Path("generated/audio/audio_manifest.json"))
    parser.add_argument("--output", type=Path, default=Path("docs"))
    parser.add_argument("--screen-dir", default="screens")
    parser.add_argument("--screen-source", type=Path, default=Path("generated/reconstructed"))
    parser.add_argument("--layers", type=Path, default=Path("generated/layers.json"))
    parser.add_argument("--animations", type=Path, default=Path("generated/animations.json"))
    args = parser.parse_args()

    inventory = json.loads(args.inventory.read_text(encoding="utf-8"))
    args.output.mkdir(parents=True, exist_ok=True)
    screen_status = copy_screens(args.screen_source, args.output, args.screen_dir)
    layers_by_slide, layer_status = copy_layers(args.layers, args.output)
    animation_status = copy_animation_manifest(args.animations, args.output)
    manifest = {
        "title": "Goblins RPG 3",
        "source": inventory["source"],
        "presentation": inventory["presentation"],
        "startScreen": "slide-001",
        "screenImageStatus": screen_status,
        "layerStatus": layer_status,
        "animationStatus": animation_status,
        "audio": copy_audio(args.audio_manifest, args.output),
        "screens": build_screens(inventory, args.screen_dir, layers_by_slide),
    }
    output_path = args.output / "game-manifest.json"
    output_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"Wrote {output_path} with {len(manifest['screens'])} screens")


if __name__ == "__main__":
    main()
