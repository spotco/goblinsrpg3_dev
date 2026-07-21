"""Verify that animated PowerPoint targets have addressable browser layers."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


def fail(message: str) -> None:
    raise SystemExit(message)


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def iter_time_nodes(animation_manifest: dict[str, Any]):
    for slide in animation_manifest.get("slides", []):
        slide_number = int(slide["slide"])
        stack = list(slide.get("rootTimeNodes", []))
        while stack:
            node = stack.pop()
            yield slide_number, node
            stack.extend(node.get("children", []))


def collect_shape_targets(animation_manifest: dict[str, Any]) -> set[tuple[int, int]]:
    targets: set[tuple[int, int]] = set()
    for slide_number, node in iter_time_nodes(animation_manifest):
        for target in node.get("targets", []):
            if target.get("kind") == "shape" and target.get("shapeId") is not None:
                targets.add((slide_number, int(target["shapeId"])))
        for behavior in node.get("behaviors", []):
            for target in behavior.get("targets", []):
                if target.get("kind") == "shape" and target.get("shapeId") is not None:
                    targets.add((slide_number, int(target["shapeId"])))
    return targets


def collect_layer_maps(game_manifest: dict[str, Any]) -> tuple[dict[tuple[int, int], dict[str, Any]], set[tuple[int, int]]]:
    layers: dict[tuple[int, int], dict[str, Any]] = {}
    animated_layers: set[tuple[int, int]] = set()
    for screen in game_manifest.get("screens", []):
        slide_number = int(screen["slide"])
        for layer in screen.get("layers", []):
            if layer.get("shapeId") is None:
                continue
            key = (slide_number, int(layer["shapeId"]))
            layers[key] = layer
            if layer.get("animated"):
                animated_layers.add(key)
    return layers, animated_layers


def verify_runtime_uses_layers(app_js: str) -> None:
    required_snippets = (
        "const renderedLayers = renderLayers(screen);",
        "screenImage.hidden = renderedLayers;",
        "layersLayer.hidden = !renderedLayers;",
        "state.currentLayerElements.set(String(layer.shapeId), element);",
    )
    for snippet in required_snippets:
        if snippet not in app_js:
            fail(f"runtime layer rendering snippet is missing: {snippet}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-manifest", type=Path, default=Path("docs/game-manifest.json"))
    parser.add_argument("--animation-manifest", type=Path, default=Path("docs/animation-manifest.json"))
    parser.add_argument("--app", type=Path, default=Path("docs/app.js"))
    parser.add_argument("--report", type=Path, default=Path("generated/animated_layer_coverage.json"))
    args = parser.parse_args()

    game_manifest = load_json(args.game_manifest)
    animation_manifest = load_json(args.animation_manifest)
    app_js = args.app.read_text(encoding="utf-8")

    verify_runtime_uses_layers(app_js)
    shape_targets = collect_shape_targets(animation_manifest)
    layers, animated_layers = collect_layer_maps(game_manifest)

    missing_layers = sorted(shape_targets - set(layers))
    missing_animated_flags = sorted(shape_targets - animated_layers)
    animated_without_targets = sorted(animated_layers - shape_targets)

    if missing_layers:
        fail(f"animated shape targets without browser layers: {missing_layers[:10]}")
    if missing_animated_flags:
        fail(f"animated shape targets without animated layer flags: {missing_animated_flags[:10]}")
    if animated_without_targets:
        fail(f"animated layer flags without animation targets: {animated_without_targets[:10]}")

    layer_types = Counter(layers[target].get("type", "unknown") for target in shape_targets)
    slides_with_targets = {slide for slide, _shape_id in shape_targets}
    summary = {
        "shapeTargets": len(shape_targets),
        "animatedLayers": len(animated_layers),
        "coveredTargets": len(shape_targets) - len(missing_layers),
        "slidesWithAnimatedTargets": len(slides_with_targets),
        "layerTypes": dict(sorted(layer_types.items())),
        "missingLayers": len(missing_layers),
        "missingAnimatedFlags": len(missing_animated_flags),
        "animatedWithoutTargets": len(animated_without_targets),
    }

    if summary["shapeTargets"] != 567:
        fail(f"expected 567 unique animated shape targets, found {summary['shapeTargets']}")
    if summary["animatedLayers"] != 567:
        fail(f"expected 567 animated browser layers, found {summary['animatedLayers']}")
    if summary["coveredTargets"] != 567:
        fail(f"expected 567 covered animated targets, found {summary['coveredTargets']}")

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(
            {
                "format": "goblins-rpg3-animated-layer-coverage-v1",
                "summary": summary,
                "coveredTargets": [
                    {
                        "slide": slide,
                        "shapeId": shape_id,
                        "layerId": layers[(slide, shape_id)]["id"],
                        "type": layers[(slide, shape_id)].get("type"),
                    }
                    for slide, shape_id in sorted(shape_targets)
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print(
        "animated layer coverage verification passed: "
        f"{summary['coveredTargets']} covered targets across {summary['slidesWithAnimatedTargets']} slides"
    )


if __name__ == "__main__":
    main()
