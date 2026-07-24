"""Build generated/advancement_model.json for all screens (Phase A of advancement plan)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from advancement_lib import build_screen_advancement, summarize_model


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def self_link_status_map(game_manifest: dict) -> dict[str, str]:
    """Prefer hotspot resolveMethod; fall back for residual binary selfs."""
    statuses: dict[str, str] = {}
    for screen in game_manifest.get("screens") or []:
        slide = int(screen["slide"])
        for hotspot in screen.get("hotspots") or []:
            if hotspot.get("action") != "hyperlink":
                continue
            shape_id = hotspot.get("shapeId")
            key = f"{slide}:{shape_id}"
            method = hotspot.get("resolveMethod")
            target = hotspot.get("targetSlide")
            if method:
                statuses[key] = str(method)
            elif target is not None and int(target) == slide:
                statuses[key] = "confirmed_self_label_match"
    return statuses


def layer_texts_for_screen(screen: dict) -> list[str]:
    texts: list[str] = []
    for layer in screen.get("layers") or []:
        if layer.get("text"):
            texts.append(str(layer["text"]))
    for hotspot in screen.get("hotspots") or []:
        if hotspot.get("shapeText"):
            texts.append(str(hotspot["shapeText"]))
    return texts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-manifest", type=Path, default=Path("docs/game-manifest.json"))
    parser.add_argument("--animations", type=Path, default=Path("docs/animation-manifest.json"))
    parser.add_argument("--output", type=Path, default=Path("generated/advancement_model.json"))
    args = parser.parse_args()

    game = load_json(args.game_manifest)
    animations = load_json(args.animations) if args.animations.exists() else {"slides": []}
    anim_by_slide = {int(s["slide"]): s for s in animations.get("slides") or []}
    screens = game.get("screens") or []
    total = len(screens)
    statuses = self_link_status_map(game)

    entries = []
    for screen in screens:
        slide = int(screen["slide"])
        advancement = build_screen_advancement(
            slide=slide,
            total_slides=total,
            transition=screen.get("transition"),
            hotspots=screen.get("hotspots") or [],
            animation_slide=anim_by_slide.get(slide),
            self_link_status=statuses,
            layer_texts=layer_texts_for_screen(screen),
        )
        entries.append(
            {
                "slide": slide,
                "id": screen.get("id"),
                "hotspots": screen.get("hotspots") or [],
                "advancement": advancement,
            }
        )

    report = {
        "format": "goblins-rpg3-advancement-model-v1",
        "source": game.get("source"),
        "policy": {
            "manualAdvanceBit": "stage click advances to next sequential slide after OnNext queue empty",
            "autoAdvanceBit": "timer; runtime uses max(slideTimeMs, animationTimeline.durationMs)",
            "noAdvanceBits": "stage click does not change slides; hyperlinks/media only unless fallback",
            "selfHyperlinks": (
                "ExHyperlink friendly name only; port promotes continue/start, sole-image, "
                "and all-self combat menus to next with resolveMethod provenance; "
                "partial combat selfs kept as confirmed_self_combat"
            ),
            "deathTerminal": "DED/Press esc → restart only",
            "sourceUnchanged": True,
            "advancementPolicyVersion": (game.get("advancementPolicy") or {}).get("version"),
        },
        "summary": summarize_model(entries),
        "slides": entries,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    summary = report["summary"]
    print(
        f"Wrote {args.output} slides={summary['slideCount']} "
        f"clickAdvance={summary['clickAdvanceSlideCount']} "
        f"autoAdvance={summary['autoAdvanceSlideCount']} "
        f"stuck={summary['stuckSlideCount']}"
    )
    if summary["stuckSlides"]:
        print("Stuck slides (no leave path under current decode):")
        for item in summary["stuckSlides"][:25]:
            print(f"  s{item['slide']:03d} reason={item['reason']} flags={item['flagNames']}")


if __name__ == "__main__":
    main()
