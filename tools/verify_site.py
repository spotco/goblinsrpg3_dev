"""Validate generated static site files without launching a browser."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def fail(message: str) -> None:
    raise SystemExit(message)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", type=Path, default=Path("docs"))
    args = parser.parse_args()

    manifest_path = args.site / "game-manifest.json"
    index_path = args.site / "index.html"
    app_path = args.site / "app.js"
    if not index_path.exists():
        fail("docs/index.html is missing")
    if not app_path.exists():
        fail("docs/app.js is missing")
    if not manifest_path.exists():
        fail("docs/game-manifest.json is missing")
    index_html = index_path.read_text(encoding="utf-8")
    app_js = app_path.read_text(encoding="utf-8")
    if 'id="layers"' not in index_html:
        fail("layer renderer root is missing from index.html")
    if "function renderLayers" not in app_js:
        fail("renderLayers function is missing from app.js")
    for required_function in (
        "function setupAnimations",
        "function advanceAnimation",
        "function runAnimationNode",
        "function applySetBehavior",
        "function applyEffectBehavior",
        "function applyAnimateBehavior",
        "function applyMotionBehavior",
        "function evaluatePowerPointFormula",
        "function motionEndpoint",
        "function parsedModifiers",
        "function nodeTiming",
        "function transitionList",
        "function nodeLocalId",
        "function triggerKey",
        "function nodeTriggerConditions",
        "function registerAnimationTriggerWaits",
        "function emitAnimationTrigger",
        "function applyCommandBehavior",
        "function playAudioSource",
        "function flushPendingAudioCommands",
    ):
        if required_function not in app_js:
            fail(f"{required_function} is missing from app.js")
    if "dataset.pptX" not in app_js or "dataset.pptY" not in app_js:
        fail("layer metric datasets are missing from app.js")
    if "ease-in-out" not in app_js or "autoReverse" not in app_js:
        fail("animation timing modifier support is missing from app.js")
    if "animationTriggerWaiters" not in app_js or "triggerEvent === 3" not in app_js or "triggerEvent === 4" not in app_js:
        fail("animation start/end trigger support is missing from app.js")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    animation_status = manifest.get("animationStatus", {})
    if animation_status.get("status") == "available":
        animation_path = args.site / animation_status["path"]
        if not animation_path.exists():
            fail(f"animation manifest is missing: {animation_status['path']}")
        animation_manifest = json.loads(animation_path.read_text(encoding="utf-8"))
        if animation_manifest.get("format") != "goblins-rpg3-animation-manifest-v1":
            fail("animation manifest has unexpected format")
        if animation_manifest.get("summary", {}).get("timeNodeContainers") != 2407:
            fail("animation manifest has unexpected time-node count")
    screens = manifest.get("screens", [])
    media_bindings = manifest.get("mediaBindings", [])
    mapped_media_bindings = [binding for binding in media_bindings if binding.get("status") == "mapped"]
    if len(screens) != 201:
        fail(f"expected 201 screens, found {len(screens)}")

    screen_ids = {screen["id"] for screen in screens}
    if manifest.get("startScreen") not in screen_ids:
        fail("start screen is not present in screens")

    missing_files = []
    missing_layer_files = []
    missing_targets = []
    zero_hotspots = []
    enabled_count = 0
    transition_count = 0
    layer_count = 0
    image_layer_count = 0
    animated_layer_count = 0
    for screen in screens:
        image_path = args.site / screen["image"]
        if not image_path.exists():
            missing_files.append(screen["image"])
        if screen.get("transition"):
            transition_count += 1
        for layer in screen.get("layers", []):
            layer_count += 1
            if layer.get("animated"):
                animated_layer_count += 1
            if layer.get("type") == "image":
                image_layer_count += 1
                layer_path = args.site / layer["instancePath"]
                if not layer_path.exists():
                    missing_layer_files.append(layer["instancePath"])
        for hotspot in screen.get("hotspots", []):
            if not hotspot.get("enabled"):
                continue
            enabled_count += 1
            bounds = hotspot.get("bounds") or {}
            if bounds.get("width", 0) <= 0 or bounds.get("height", 0) <= 0:
                zero_hotspots.append(hotspot["id"])
            target = f"slide-{int(hotspot['targetSlide']):03d}"
            if target not in screen_ids:
                missing_targets.append(hotspot["id"])

    if missing_files:
        fail(f"missing screen image files: {missing_files[:5]}")
    if missing_layer_files:
        fail(f"missing layer image files: {missing_layer_files[:5]}")
    if missing_targets:
        fail(f"hotspots target missing screens: {missing_targets[:5]}")
    if zero_hotspots:
        fail(f"enabled hotspots with zero area: {zero_hotspots[:5]}")
    if enabled_count != 194:
        fail(f"expected 194 enabled navigation hotspots, found {enabled_count}")
    if manifest.get("transitionStatus", {}).get("status") == "available":
        if manifest["transitionStatus"].get("count") != 201:
            fail("expected 201 extracted transitions in manifest status")
        if transition_count != 201:
            fail(f"expected 201 screen transitions, found {transition_count}")
    if len(media_bindings) != 11:
        fail(f"expected 11 media command bindings, found {len(media_bindings)}")
    if len(mapped_media_bindings) != 8:
        fail(f"expected 8 mapped media command bindings, found {len(mapped_media_bindings)}")
    if manifest.get("layerStatus", {}).get("status") == "available":
        if layer_count != 1182:
            fail(f"expected 1182 slide layers, found {layer_count}")
        if image_layer_count != 532:
            fail(f"expected 532 image layers, found {image_layer_count}")
        if animated_layer_count != 567:
            fail(f"expected 567 animated layers, found {animated_layer_count}")

    print("site verification passed")


if __name__ == "__main__":
    main()
