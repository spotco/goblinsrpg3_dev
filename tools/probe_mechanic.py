"""Compare PowerPoint source truth vs port mapping for one mechanic class."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from debug_lib import (
    REPO_ROOT,
    animation_by_slide,
    build_slide_report,
    load_animation_manifest,
    load_game_manifest,
)


MECHANICS = ("wordart", "hotspots", "animation", "media", "background", "pictures", "all")


def probe_wordart(report: dict, poi_shapes: list[dict]) -> dict:
    items = []
    for shape in poi_shapes:
        geo = shape.get("geoText")
        shape_type = str(shape.get("shapeType") or "")
        if not geo and not shape_type.startswith("TEXT_"):
            continue
        if shape_type in {"TEXT_BOX"} and not geo:
            continue
        layer = next((item for item in report["layers"] if item.get("shapeId") == shape.get("shapeId")), None)
        items.append(
            {
                "shapeId": shape.get("shapeId"),
                "shapeType": shape_type,
                "poiText": shape.get("text"),
                "geoText": geo,
                "layerText": None if layer is None else layer.get("text"),
                "layerWordArt": None if layer is None else layer.get("wordArt"),
                "status": (
                    "ok"
                    if layer and str(layer.get("text") or "").strip()
                    else "missing_in_layers"
                    if geo
                    else "no_text_source"
                ),
            }
        )
    return {"mechanic": "wordart", "slide": report["slide"], "items": items}


def probe_hotspots(report: dict) -> dict:
    items = []
    for hotspot in report.get("hotspots") or []:
        target = hotspot.get("targetSlide")
        items.append(
            {
                "id": hotspot.get("id"),
                "shapeId": hotspot.get("shapeId"),
                "action": hotspot.get("action"),
                "targetSlide": target,
                "clickable": hotspot.get("clickable"),
                "behaviorStatus": hotspot.get("behaviorStatus"),
                "bounds": hotspot.get("bounds"),
                "selfLink": target == report["slide"],
                "mediaBindingId": hotspot.get("mediaBindingId"),
            }
        )
    return {"mechanic": "hotspots", "slide": report["slide"], "items": items}


def probe_media(report: dict, game_manifest: dict) -> dict:
    bindings = {
        binding.get("id"): binding
        for binding in game_manifest.get("mediaBindings") or []
        if int(binding.get("slide") or 0) == report["slide"]
    }
    items = []
    for hotspot in report.get("hotspots") or []:
        if hotspot.get("action") != "media" and not hotspot.get("mediaBindingId"):
            continue
        binding = bindings.get(hotspot.get("mediaBindingId")) if hotspot.get("mediaBindingId") else None
        if binding is None:
            for candidate in bindings.values():
                if candidate.get("shapeId") == hotspot.get("shapeId"):
                    binding = candidate
                    break
        audio_path = None
        if binding and binding.get("audioOutputs"):
            audio_path = (binding["audioOutputs"][0] or {}).get("path")
        elif binding and binding.get("audioSource"):
            audio_path = binding.get("audioSource")
        exists = False
        if audio_path:
            exists = (REPO_ROOT / "docs" / str(audio_path)).exists() or (REPO_ROOT / str(audio_path)).exists()
        items.append(
            {
                "hotspotId": hotspot.get("id"),
                "shapeId": hotspot.get("shapeId"),
                "behaviorStatus": hotspot.get("behaviorStatus"),
                "binding": binding,
                "audioPath": audio_path,
                "audioExists": exists,
            }
        )
    return {"mechanic": "media", "slide": report["slide"], "items": items, "bindings": list(bindings.values())}


def probe_background(report: dict) -> dict:
    return {
        "mechanic": "background",
        "slide": report["slide"],
        "poiBackground": report.get("background"),
        "manifestBackgroundColor": report.get("backgroundColor"),
        "png": report.get("png"),
        "notes": [
            "Runtime uses screen.backgroundColor on #stage when present.",
            "When layers exist, the composite PNG is hidden; sparse layers can look empty.",
        ],
    }


def probe_pictures(report: dict) -> dict:
    items = []
    for layer in report.get("layers") or []:
        if layer.get("type") != "image":
            continue
        path = layer.get("instancePath")
        docs_path = REPO_ROOT / "docs" / str(path) if path else None
        gen_path = REPO_ROOT / str(path) if path else None
        items.append(
            {
                "layerId": layer.get("id"),
                "shapeId": layer.get("shapeId"),
                "instancePath": path,
                "existsInDocs": bool(docs_path and docs_path.exists()),
                "existsInGenerated": bool(gen_path and gen_path.exists()),
                "bounds": layer.get("bounds"),
            }
        )
    poi_pictures = [shape for shape in report.get("poiShapes") or [] if shape.get("picture")]
    return {"mechanic": "pictures", "slide": report["slide"], "layers": items, "poiPictures": poi_pictures}


def probe_animation(report: dict, animation_slide: dict | None) -> dict:
    layer_ids = {int(layer["shapeId"]) for layer in report.get("layers") or [] if layer.get("shapeId") is not None}
    targets = []

    def walk(node: dict) -> None:
        for target in node.get("targets") or []:
            if not isinstance(target, dict):
                continue
            shape_id = target.get("shapeId") or target.get("targetId") or target.get("spid")
            try:
                shape_id_int = int(shape_id)
            except (TypeError, ValueError):
                continue
            targets.append(
                {
                    "nodeId": node.get("id"),
                    "shapeId": shape_id_int,
                    "hasLayer": shape_id_int in layer_ids,
                }
            )
        for child in node.get("children") or []:
            if isinstance(child, dict):
                walk(child)

    if animation_slide:
        for root in animation_slide.get("rootTimeNodes") or []:
            if isinstance(root, dict):
                walk(root)
    return {
        "mechanic": "animation",
        "slide": report["slide"],
        "available": animation_slide is not None,
        "rootCount": len((animation_slide or {}).get("rootTimeNodes") or []),
        "targets": targets,
        "missingLayers": [item for item in targets if not item["hasLayer"]],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mechanic", choices=MECHANICS, help="Mechanic class to probe")
    parser.add_argument("--slide", type=int, required=True)
    parser.add_argument("--repo", type=Path, default=REPO_ROOT)
    parser.add_argument("--json", action="store_true", help="Print full JSON only")
    args = parser.parse_args()

    report = build_slide_report(args.slide, repo_root=args.repo)
    game_manifest = load_game_manifest(args.repo / "docs" / "game-manifest.json")
    animation_manifest = load_animation_manifest()
    animation_slide = animation_by_slide(animation_manifest, args.slide)
    poi_shapes = report.get("poiShapes") or []

    results = []
    selected = MECHANICS[:-1] if args.mechanic == "all" else (args.mechanic,)
    for mechanic in selected:
        if mechanic == "wordart":
            results.append(probe_wordart(report, poi_shapes))
        elif mechanic == "hotspots":
            results.append(probe_hotspots(report))
        elif mechanic == "media":
            results.append(probe_media(report, game_manifest))
        elif mechanic == "background":
            results.append(probe_background(report))
        elif mechanic == "pictures":
            results.append(probe_pictures(report))
        elif mechanic == "animation":
            results.append(probe_animation(report, animation_slide))

    payload = {
        "format": "goblins-rpg3-mechanic-probe-v1",
        "slide": args.slide,
        "mechanics": results,
        "risks": [risk for risk in report.get("risks") or [] if args.mechanic == "all" or risk["code"].startswith(args.mechanic) or args.mechanic in risk["code"]],
        "browserUrl": f"http://127.0.0.1:8765/?debug=1&slide={args.slide}",
    }

    if args.json:
        print(json.dumps(payload, indent=2))
        return

    print(f"probe slide={args.slide} mechanic={args.mechanic}")
    for block in results:
        print(f"== {block['mechanic']} ==")
        if block["mechanic"] == "wordart":
            for item in block["items"]:
                print(
                    f"  shape {item['shapeId']} type={item['shapeType']} "
                    f"poi={item['poiText']!r} geo={item.get('geoText')} layer={item['layerText']!r} status={item['status']}"
                )
            if not block["items"]:
                print("  (no wordart/geotext shapes)")
        elif block["mechanic"] == "hotspots":
            for item in block["items"]:
                print(
                    f"  {item['id']} action={item['action']} target={item['targetSlide']} "
                    f"clickable={item['clickable']} selfLink={item['selfLink']} status={item['behaviorStatus']}"
                )
            if not block["items"]:
                print("  (no hotspots)")
        elif block["mechanic"] == "media":
            for item in block["items"]:
                print(
                    f"  hotspot={item['hotspotId']} binding={bool(item['binding'])} "
                    f"audio={item['audioPath']} exists={item['audioExists']} status={item['behaviorStatus']}"
                )
            if not block["items"]:
                print("  (no media hotspots)")
        elif block["mechanic"] == "background":
            print(f"  poi={block['poiBackground']}")
            print(f"  manifestBackgroundColor={block['manifestBackgroundColor']}")
            print(f"  png={block['png']}")
        elif block["mechanic"] == "pictures":
            for item in block["layers"]:
                print(
                    f"  {item['layerId']} docs={item['existsInDocs']} gen={item['existsInGenerated']} path={item['instancePath']}"
                )
            if not block["layers"]:
                print("  (no image layers)")
        elif block["mechanic"] == "animation":
            print(f"  available={block['available']} roots={block['rootCount']} targets={len(block['targets'])}")
            for item in block["missingLayers"][:20]:
                print(f"  missing layer for shape {item['shapeId']} (node {item['nodeId']})")
            if block["available"] and not block["missingLayers"]:
                print("  all observed targets have layers")
    print(f"Browser: {payload['browserUrl']}")


if __name__ == "__main__":
    main()
