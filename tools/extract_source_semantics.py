"""Build a consolidated source-semantics report for the legacy deck."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def parse_poi_semantics(path: Path) -> dict[int, dict[str, Any]]:
    slides: dict[int, dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if not line:
            continue
        parts = line.split("\t")
        key = parts[0]
        if key == "SLIDE":
            slide = int(parts[1])
            slides.setdefault(slide, {})["shapeCount"] = int(parts[3])
        elif key == "SLIDEMETA":
            slide = int(parts[1])
            slides.setdefault(slide, {}).update(
                {
                    "title": parts[2] or None,
                    "slideName": parts[3] or None,
                    "masterSheet": parts[4] or None,
                    "slideLayout": parts[5] or None,
                    "followMasterBackground": parts[6].lower() == "true",
                    "followMasterObjects": parts[7].lower() == "true",
                    "followMasterScheme": parts[8].lower() == "true",
                    "hidden": parts[9].lower() == "true",
                }
            )
    return slides


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, default=Path("generated/inventory.json"))
    parser.add_argument("--poi-audit", type=Path, default=Path("generated/poi_audit.tsv"))
    parser.add_argument("--layers", type=Path, default=Path("generated/layers.json"))
    parser.add_argument("--animations", type=Path, default=Path("generated/animations.json"))
    parser.add_argument("--game-manifest", type=Path, default=Path("docs/game-manifest.json"))
    parser.add_argument("--output", type=Path, default=Path("generated/source_semantics.json"))
    args = parser.parse_args()

    inventory = load_json(args.inventory)
    layers = load_json(args.layers)
    animations = load_json(args.animations)
    game_manifest = load_json(args.game_manifest)
    poi_slides = parse_poi_semantics(args.poi_audit)

    transition_by_slide = {
        int(screen["slide"]): screen.get("transition")
        for screen in game_manifest.get("screens", [])
        if screen.get("transition") is not None
    }
    layers_by_slide = {int(slide["slide"]): slide.get("layers", []) for slide in layers.get("slides", [])}
    slide_records = inventory.get("slides", [])
    slides = []
    for index, slide_record in enumerate(slide_records, start=1):
        slide_layers = layers_by_slide.get(index, [])
        z_orders = [int(layer["zOrder"]) for layer in slide_layers]
        text_layers = [layer for layer in slide_layers if layer.get("type") == "text"]
        image_layers = [layer for layer in slide_layers if layer.get("type") == "image"]
        action_layers = [layer for layer in slide_layers if layer.get("actions")]
        slides.append(
            {
                "id": f"slide-{index:03d}",
                "slide": index,
                "sourceRecordOffset": slide_record.get("offset"),
                "sourceRecordLength": slide_record.get("length"),
                **poi_slides.get(index, {}),
                "layerCount": len(slide_layers),
                "imageLayerCount": len(image_layers),
                "textLayerCount": len(text_layers),
                "actionBoundLayerCount": len(action_layers),
                "zOrder": {
                    "min": min(z_orders) if z_orders else None,
                    "max": max(z_orders) if z_orders else None,
                    "contiguous": z_orders == list(range(len(z_orders))),
                },
                "transition": transition_by_slide.get(index),
            }
        )

    media_bindings = game_manifest.get("mediaBindings", [])
    audio_cues = game_manifest.get("audioCues", [])
    unresolved_media = [binding for binding in media_bindings if binding.get("status") != "mapped"]
    source_audio = game_manifest.get("audio", [])
    transition_sound_refs = [
        screen["transition"].get("soundRef")
        for screen in game_manifest.get("screens", [])
        if screen.get("transition") and screen["transition"].get("soundRef")
    ]

    summary = {
        "slides": len(slides),
        "slidesWithTitles": sum(1 for slide in slides if slide.get("title")),
        "hiddenSlides": sum(1 for slide in slides if slide.get("hidden")),
        "zOrderContiguousSlides": sum(1 for slide in slides if slide["zOrder"]["contiguous"]),
        "textRuns": len(inventory.get("text_runs", [])),
        "layerTextRuns": layers["summary"].get("textRuns"),
        "paragraphs": layers["summary"].get("paragraphs"),
        "transitions": len(transition_by_slide),
        "animationTimeNodeContainers": animations.get("summary", {}).get("timeNodeContainers"),
        "animationShapeTargets": animations.get("summary", {}).get("shapeTargets"),
        "sourceAudioEntries": len(source_audio),
        "audioCueRecords": len(audio_cues),
        "sourceBackedAudioCues": sum(1 for cue in audio_cues if cue.get("source")),
        "mediaCommandBindings": len(media_bindings),
        "mappedMediaCommandBindings": len(media_bindings) - len(unresolved_media),
        "unresolvedMediaCommandBindings": len(unresolved_media),
        "transitionSoundRefs": len(transition_sound_refs),
    }

    if summary["slides"] != 201:
        raise SystemExit(f"expected 201 slides, found {summary['slides']}")
    if summary["zOrderContiguousSlides"] != 201:
        raise SystemExit("not all slides have contiguous z-order metadata")
    if summary["transitions"] != 201:
        raise SystemExit(f"expected 201 transitions, found {summary['transitions']}")
    if summary["layerTextRuns"] != 695:
        raise SystemExit(f"expected 695 layer text runs, found {summary['layerTextRuns']}")
    if summary["mediaCommandBindings"] != 11:
        raise SystemExit(f"expected 11 media command bindings, found {summary['mediaCommandBindings']}")

    report = {
        "format": "goblins-rpg3-source-semantics-v1",
        "summary": summary,
        "audioSemantics": {
            "status": "explicit_with_unresolved_legacy_cue_ids" if unresolved_media else "fully_mapped",
            "sourceAudio": source_audio,
            "audioCues": audio_cues,
            "mediaBindings": media_bindings,
            "unresolvedMediaBindings": unresolved_media,
            "transitionSoundRefs": transition_sound_refs,
        },
        "slides": slides,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(
        "source semantics extraction passed: "
        f"{summary['slides']} slides, {summary['layerTextRuns']} layer text runs, "
        f"{summary['unresolvedMediaCommandBindings']} unresolved media bindings"
    )


if __name__ == "__main__":
    main()
