"""Generate a manual visual-review checklist from generated manifests."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-manifest", type=Path, default=Path("docs/game-manifest.json"))
    parser.add_argument("--render-manifest", type=Path, default=Path("generated/reconstructed/render_manifest.json"))
    parser.add_argument("--runtime-traversal", type=Path, default=Path("generated/runtime_traversal.json"))
    parser.add_argument("--output", type=Path, default=Path("generated/visual_review_checklist.json"))
    args = parser.parse_args()

    game = load_json(args.game_manifest)
    renders = load_json(args.render_manifest)
    traversal = load_json(args.runtime_traversal) if args.runtime_traversal.exists() else {}
    unreachable = set(traversal.get("unreachableScreens", []))
    cyclic = set(traversal.get("cyclicScreens", []))
    render_by_slide = {int(item["slide"]): item for item in renders.get("slides", [])}
    screens = []
    for screen in game.get("screens", []):
        slide = int(screen["slide"])
        layers = screen.get("layers", [])
        hotspots = screen.get("hotspots", [])
        enabled_hotspots = [hotspot for hotspot in hotspots if hotspot.get("enabled")]
        animated_layers = [layer for layer in layers if layer.get("animated")]
        transformed_layers = [
            layer
            for layer in layers
            if (layer.get("transform") or {}).get("rotation")
            or (layer.get("transform") or {}).get("flipHorizontal")
            or (layer.get("transform") or {}).get("flipVertical")
        ]
        flags = []
        if screen["id"] in unreachable:
            flags.append("unreachable_from_hotspot_graph")
        if screen["id"] in cyclic:
            flags.append("cycle_participant")
        if animated_layers:
            flags.append("animated_layers")
        if transformed_layers:
            flags.append("transformed_layers")
        if len(enabled_hotspots) == 0:
            flags.append("no_enabled_hotspots")
        if any(not hotspot.get("enabled") for hotspot in hotspots):
            flags.append("non_navigation_or_media_actions")

        screens.append(
            {
                "id": screen["id"],
                "slide": slide,
                "render": (render_by_slide.get(slide) or {}).get("path"),
                "browserScreen": screen.get("image"),
                "enabledHotspots": len(enabled_hotspots),
                "totalHotspots": len(hotspots),
                "layerCount": len(layers),
                "animatedLayerCount": len(animated_layers),
                "transformedLayerCount": len(transformed_layers),
                "flags": flags,
                "reviewStatus": "pending_manual_review",
                "notes": "",
            }
        )

    report = {
        "format": "goblins-rpg3-visual-review-checklist-v1",
        "source": {
            "gameManifest": args.game_manifest.as_posix(),
            "renderManifest": args.render_manifest.as_posix(),
            "runtimeTraversal": args.runtime_traversal.as_posix() if args.runtime_traversal.exists() else None,
        },
        "summary": {
            "screens": len(screens),
            "pendingManualReview": len(screens),
            "screensWithEnabledHotspots": sum(1 for item in screens if item["enabledHotspots"] > 0),
            "screensWithAnimatedLayers": sum(1 for item in screens if item["animatedLayerCount"] > 0),
            "screensWithTransformedLayers": sum(1 for item in screens if item["transformedLayerCount"] > 0),
            "unreachableFromHotspotGraph": sum(1 for item in screens if "unreachable_from_hotspot_graph" in item["flags"]),
        },
        "screens": screens,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"Wrote {args.output} with {len(screens)} visual-review items")


if __name__ == "__main__":
    main()
