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

SOURCE_AUDIO_CUE_IDS = {
    "titlesong.wma": "linked:titlesong",
    "rocksong.wma": "linked:rocksong",
    "Ffvictory.mid": "linked:Ffvictory",
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
    transitions_by_slide: dict[int, dict[str, object]] | None = None,
    media_bindings_by_shape: dict[tuple[int, int], dict[str, object]] | None = None,
    slide_meta_by_slide: dict[int, dict[str, object]] | None = None,
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
            "clickable": bool(action.get("target_slide")),
            "behaviorStatus": "navigation" if action.get("target_slide") else "no_runtime_action",
        }
        if bounds:
            hotspot["bounds"] = normalize_bounds(bounds, width, height)
        if action_code == 6 and action.get("shape_id") is not None and media_bindings_by_shape is not None:
            media_binding = media_bindings_by_shape.get((slide, int(action["shape_id"])))
            if media_binding:
                hotspot["mediaBindingId"] = media_binding["id"]
                hotspot["mediaStatus"] = media_binding["status"]
                bounds_record = hotspot.get("bounds") or {}
                positive_area = bounds_record.get("width", 0) > 0 and bounds_record.get("height", 0) > 0
                hotspot["behaviorStatus"] = (
                    "clickable_media"
                    if media_binding.get("status") == "mapped" and positive_area
                    else "mapped_media_zero_area"
                    if media_binding.get("status") == "mapped"
                    else "unresolved_media"
                )
                hotspot["clickable"] = media_binding.get("status") == "mapped" and positive_area
            else:
                hotspot["behaviorStatus"] = "missing_media_binding"
        elif action_code == 0:
            hotspot["behaviorStatus"] = "explicit_noop"
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
        if slide_meta_by_slide is not None and index in slide_meta_by_slide:
            screen.update(slide_meta_by_slide[index])
        if transitions_by_slide is not None:
            screen["transition"] = transitions_by_slide.get(index)
        screens.append(screen)
    return screens


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


def copy_screens(
    screen_source: Path | None,
    output_dir: Path,
    screen_dir: str,
    slide_filter: set[int] | None = None,
) -> str:
    if screen_source is None or not screen_source.exists():
        return "pending_publishable_renders"
    screen_output = output_dir / screen_dir
    screen_output.mkdir(parents=True, exist_ok=True)
    copied = 0
    for source in sorted(screen_source.glob("slide-*.png")):
        # slide-012.png -> 12
        try:
            slide_number = int(source.stem.split("-")[1])
        except (IndexError, ValueError):
            slide_number = None
        if slide_filter is not None and slide_number not in slide_filter:
            continue
        shutil.copy2(source, screen_output / source.name)
        copied += 1
    if slide_filter is not None:
        # Partial publish still leaves a complete docs/screens tree if it already existed.
        total = len(list(screen_output.glob("slide-*.png")))
        return "custom_reconstruction" if total else "pending_publishable_renders"
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
        copied_entry["cue"] = source_audio_cue(copied_entry)
        result.append(copied_entry)
    return result


def source_audio_cue(audio_entry: dict[str, object]) -> dict[str, object]:
    source = str(audio_entry.get("source", ""))
    embedded_id = audio_entry.get("embeddedSoundId")
    if embedded_id is not None:
        return {
            "id": f"embedded:{int(embedded_id)}",
            "kind": "embedded_powerpoint_sound",
            "embeddedSoundId": int(embedded_id),
            "trigger": "referenced_by_powerpoint_sound_or_media_atom",
            "loop": False,
            "stop": False,
            "replaceExisting": True,
            "status": "source_backed",
        }
    return {
        "id": SOURCE_AUDIO_CUE_IDS.get(Path(source).name, f"source:{Path(source).stem}"),
        "kind": audio_entry.get("sourceKind", "linked_audio"),
        "trigger": "linked_source_file_inventory",
        "loop": False,
        "stop": False,
        "replaceExisting": True,
        "status": "source_backed" if audio_entry.get("outputs") else "no_browser_outputs",
    }


def legacy_animation_cue_behavior(legacy: dict[str, object] | None, command: str, start_seconds: float) -> dict[str, object]:
    flag_names = set(legacy.get("flagNames", [])) if legacy else set()
    return {
        "trigger": "animation_command",
        "command": command,
        "startSeconds": start_seconds,
        "loop": "loopSound" in flag_names,
        "stop": "stopSound" in flag_names or command == "stop",
        "replaceExisting": "stopSound" not in flag_names,
        "requiresUserGesture": True,
        "source": "AnimationInfoAtom/TimeCommandBehavior",
    }


def build_audio_cues(
    inventory: dict[str, object],
    timing_manifest_path: Path,
    copied_audio: list[dict[str, object]],
    media_bindings: list[dict[str, object]],
) -> list[dict[str, object]]:
    timing = json.loads(timing_manifest_path.read_text(encoding="utf-8")) if timing_manifest_path.exists() else {}
    animations = timing.get("animations", [])
    bindings_by_source: dict[str, list[dict[str, object]]] = {}
    for binding in media_bindings:
        if binding.get("audioSource"):
            bindings_by_source.setdefault(str(binding["audioSource"]), []).append(
                {
                    "id": binding["id"],
                    "slide": binding["slide"],
                    "shapeId": binding["shapeId"],
                    "legacyCueId": binding.get("legacyCueId"),
                    "cueBehavior": binding.get("cueBehavior"),
                }
            )

    cues = []
    for index, entry in enumerate(copied_audio, start=1):
        cue = dict(entry.get("cue") or source_audio_cue(entry))
        cue.update(
            {
                "source": entry.get("source"),
                "sourceIndex": index,
                "outputs": entry.get("outputs", []),
                "status": cue.get("status", entry.get("status")),
                "mediaBindings": bindings_by_source.get(str(entry.get("source")), []),
            }
        )
        embedded_id = entry.get("embeddedSoundId")
        if embedded_id is not None:
            cue["legacySoundAnimations"] = [
                {
                    "slide": item["slide"],
                    "shapeId": item["shapeId"],
                    "recordOffset": item["recordOffset"],
                    "flagNames": item.get("flagNames", []),
                    "behavior": legacy_animation_cue_behavior(item, "play", 0.0),
                }
                for item in animations
                if item.get("soundRef") == embedded_id or item.get("orderId") == embedded_id
            ]
        else:
            cue["legacySoundAnimations"] = []
        cues.append(cue)

    unresolved = [
        {
            "id": f"legacy-unresolved:{binding.get('legacyCueId')}",
            "kind": "unresolved_legacy_media_cue",
            "legacyCueId": binding.get("legacyCueId"),
            "status": "unresolved_audio_id",
            "mediaBinding": {
                "id": binding["id"],
                "slide": binding["slide"],
                "shapeId": binding["shapeId"],
                "cueBehavior": binding.get("cueBehavior"),
            },
            "reason": "Legacy cue id is referenced by a media-shape animation command but is not present in the embedded PowerPoint sound collection or linked source-audio inventory with a recoverable identifier.",
        }
        for binding in media_bindings
        if binding.get("status") != "mapped"
    ]
    return cues + unresolved


def build_media_bindings(
    inventory: dict[str, object],
    timing_manifest_path: Path,
    copied_audio: list[dict[str, object]],
) -> list[dict[str, object]]:
    if not timing_manifest_path.exists():
        return []
    timing = json.loads(timing_manifest_path.read_text(encoding="utf-8"))
    legacy_animations = {
        (int(item["slide"]), int(item["shapeId"])): item
        for item in timing.get("animations", [])
        if item.get("shapeId") is not None
    }
    audio_by_embedded_id = {
        int(item["embeddedSoundId"]): item
        for item in copied_audio
        if item.get("embeddedSoundId") is not None and item.get("outputs")
    }
    bindings = []
    for action in inventory.get("interactive_actions", []):
        if int(action.get("action_code", -1)) != 6 or action.get("shape_id") is None:
            continue
        slide = int(action["slide"])
        shape_id = int(action["shape_id"])
        legacy = legacy_animations.get((slide, shape_id))
        cue_id = int(legacy["orderId"]) if legacy else None
        audio_entry = audio_by_embedded_id.get(cue_id) if cue_id is not None else None
        binding = {
            "id": f"slide-{slide:03d}-shape-{shape_id}",
            "slide": slide,
            "shapeId": shape_id,
            "actionRecordOffset": action["record_offset"],
            "legacyCueId": cue_id,
            "command": "playFrom",
            "startSeconds": 0.0,
            "status": "mapped" if audio_entry else "unresolved_audio_id",
        }
        binding["cueBehavior"] = legacy_animation_cue_behavior(legacy, "playFrom", 0.0)
        if legacy:
            binding["legacyAnimation"] = {
                "recordOffset": legacy["recordOffset"],
                "flagNames": legacy["flagNames"],
                "rawHex": legacy["rawHex"],
            }
        if audio_entry:
            binding["audioSource"] = audio_entry["source"]
            binding["audioOutputs"] = audio_entry["outputs"]
            binding["audioCueId"] = (audio_entry.get("cue") or {}).get("id")
        else:
            binding["unresolvedReason"] = (
                "Legacy cue id is not present in converted embedded audio outputs. "
                "It may refer to a linked/deleted media object that needs PowerPoint reference validation."
            )
        bindings.append(binding)
    return bindings


def copy_layers(
    layer_manifest_path: Path, output_dir: Path
) -> tuple[dict[int, list[dict[str, object]]] | None, dict[int, dict[str, object]], dict[str, object]]:
    if not layer_manifest_path.exists():
        return None, {}, {"status": "missing"}

    layer_manifest = json.loads(layer_manifest_path.read_text(encoding="utf-8"))
    copied_images = 0
    layers_by_slide: dict[int, list[dict[str, object]]] = {}
    slide_meta_by_slide: dict[int, dict[str, object]] = {}
    layer_output_root = output_dir / "assets" / "slide-assets"
    for slide in layer_manifest.get("slides", []):
        slide_number = int(slide["slide"])
        meta: dict[str, object] = {}
        if slide.get("backgroundColor"):
            meta["backgroundColor"] = slide["backgroundColor"]
        if slide.get("background"):
            meta["background"] = slide["background"]
        if meta:
            slide_meta_by_slide[slide_number] = meta
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

    return layers_by_slide, slide_meta_by_slide, {
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


def load_transitions(timing_manifest_path: Path) -> tuple[dict[int, dict[str, object]], dict[str, object]]:
    if not timing_manifest_path.exists():
        return {}, {"status": "missing"}
    timing = json.loads(timing_manifest_path.read_text(encoding="utf-8"))
    transitions = {int(item["slide"]): item for item in timing.get("transitions", [])}
    return transitions, {"status": "available", "count": len(transitions)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, default=Path("generated/inventory.json"))
    parser.add_argument("--audio-manifest", type=Path, default=Path("generated/audio/audio_manifest.json"))
    parser.add_argument("--output", type=Path, default=Path("docs"))
    parser.add_argument("--screen-dir", default="screens")
    parser.add_argument("--screen-source", type=Path, default=Path("generated/reconstructed"))
    parser.add_argument("--layers", type=Path, default=Path("generated/layers.json"))
    parser.add_argument("--animations", type=Path, default=Path("generated/animations.json"))
    parser.add_argument("--timing", type=Path, default=Path("generated/timing_manifest.json"))
    parser.add_argument(
        "--slides",
        type=str,
        default=None,
        help="Optional subset of screen PNGs to refresh, e.g. 2,14-16. Full manifest is still rebuilt.",
    )
    args = parser.parse_args()

    inventory = json.loads(args.inventory.read_text(encoding="utf-8"))
    args.output.mkdir(parents=True, exist_ok=True)
    slide_filter = parse_slide_filter(args.slides)
    screen_status = copy_screens(args.screen_source, args.output, args.screen_dir, slide_filter)
    layers_by_slide, slide_meta_by_slide, layer_status = copy_layers(args.layers, args.output)
    animation_status = copy_animation_manifest(args.animations, args.output)
    transitions_by_slide, transition_status = load_transitions(args.timing)
    copied_audio = copy_audio(args.audio_manifest, args.output)
    media_bindings = build_media_bindings(inventory, args.timing, copied_audio)
    media_bindings_by_shape = {
        (int(binding["slide"]), int(binding["shapeId"])): binding for binding in media_bindings
    }
    audio_cues = build_audio_cues(inventory, args.timing, copied_audio, media_bindings)
    manifest = {
        "title": "Goblins RPG 3",
        "source": inventory["source"],
        "presentation": inventory["presentation"],
        "startScreen": "slide-001",
        "screenImageStatus": screen_status,
        "layerStatus": layer_status,
        "animationStatus": animation_status,
        "transitionStatus": transition_status,
        "audio": copied_audio,
        "audioCues": audio_cues,
        "mediaBindings": media_bindings,
        "screens": build_screens(
            inventory,
            args.screen_dir,
            layers_by_slide,
            transitions_by_slide,
            media_bindings_by_shape,
            slide_meta_by_slide,
        ),
    }
    output_path = args.output / "game-manifest.json"
    output_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"Wrote {output_path} with {len(manifest['screens'])} screens")


if __name__ == "__main__":
    main()
