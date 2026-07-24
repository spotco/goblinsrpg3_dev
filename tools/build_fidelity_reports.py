"""Phase 5 fidelity offline reports: sequential edges, auto-advance timing, opening trains.

Writes:
  generated/sequential_advance_edges.json
  generated/auto_advance_timing.json
  generated/opening_animation_trains.json
"""

from __future__ import annotations

import json
from pathlib import Path

from animation_timeline import (
    count_on_next,
    inventory_behaviors,
    slide_animation_timeline,
)

ROOT = Path(__file__).resolve().parents[1]
OPENING_SLIDES = (3, 4, 5, 6, 7, 8, 12, 13, 14)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def build_sequential_edges(game: dict) -> dict:
    edges = []
    manual = []
    fallback = []
    auto = []
    for screen in game.get("screens") or []:
        slide = int(screen["slide"])
        adv = screen.get("advancement") or {}
        flags = set((screen.get("transition") or {}).get("flagNames") or [])
        next_id = adv.get("nextSequentialId")
        next_slide = adv.get("nextSequentialSlide")
        if adv.get("stageClickAdvancesSlide") and next_id:
            method = adv.get("stageClickResolveMethod") or (
                "manualAdvance_bit" if "manualAdvance" in flags else "unknown"
            )
            edge = {
                "from": slide,
                "to": next_slide,
                "toId": next_id,
                "kind": "stage_click_advance",
                "resolveMethod": method,
                "onNextConditionCount": adv.get("onNextConditionCount"),
            }
            edges.append(edge)
            if method == "manualAdvance_bit" or "manualAdvance" in flags:
                manual.append(edge)
            else:
                fallback.append(edge)
        if adv.get("autoAdvance") and next_id:
            edge = {
                "from": slide,
                "to": next_slide,
                "toId": next_id,
                "kind": "auto_advance",
                "delayMs": adv.get("autoAdvanceDelayMs"),
            }
            edges.append(edge)
            auto.append(edge)

    return {
        "format": "goblins-rpg3-sequential-advance-edges-v1",
        "summary": {
            "stageClickEdgeCount": len(manual) + len(fallback),
            "manualAdvanceEdgeCount": len(manual),
            "fallbackStageClickEdgeCount": len(fallback),
            "autoAdvanceEdgeCount": len(auto),
            "totalSequentialEdges": len(edges),
        },
        "manualAdvanceEdges": manual,
        "fallbackStageClickEdges": fallback,
        "autoAdvanceEdges": auto,
        "allSequentialEdges": edges,
    }


def build_auto_advance_timing(game: dict, animations: dict) -> dict:
    anim_by = {int(s["slide"]): s for s in animations.get("slides") or []}
    rows = []
    extended = 0
    for screen in game.get("screens") or []:
        adv = screen.get("advancement") or {}
        if not adv.get("autoAdvance"):
            continue
        slide = int(screen["slide"])
        slide_time = adv.get("autoAdvanceDelayMs")
        if slide_time is None:
            slide_time = (screen.get("transition") or {}).get("slideTimeMs")
        timeline = slide_animation_timeline(anim_by.get(slide))
        source = float(slide_time or 0)
        anim_ms = float(timeline.get("durationMs") or 0)
        effective = max(source, anim_ms)
        if anim_ms > source:
            extended += 1
        rows.append(
            {
                "slide": slide,
                "slideTimeMs": source,
                "animationTimelineMs": anim_ms,
                "effectiveDelayMs": effective,
                "extendedByAnimation": anim_ms > source,
                "animationRootCount": timeline.get("rootCount"),
                "onNextConditionCount": adv.get("onNextConditionCount"),
            }
        )

    return {
        "format": "goblins-rpg3-auto-advance-timing-v1",
        "policy": "runtime scheduledDelayMs = max(slideTimeMs, animationTimeline.durationMs)",
        "summary": {
            "autoAdvanceSlideCount": len(rows),
            "extendedByAnimationCount": extended,
            "maxEffectiveDelayMs": max((r["effectiveDelayMs"] for r in rows), default=0),
        },
        "slides": rows,
    }


def build_opening_trains(game: dict, animations: dict) -> dict:
    anim_by = {int(s["slide"]): s for s in animations.get("slides") or []}
    rows = []
    for slide in OPENING_SLIDES:
        screen = game["screens"][slide - 1]
        adv = screen.get("advancement") or {}
        anim = anim_by.get(slide)
        timeline = slide_animation_timeline(anim)
        behaviors = inventory_behaviors(anim)
        on_next = count_on_next(anim)
        rows.append(
            {
                "slide": slide,
                "stageClickAdvancesSlide": adv.get("stageClickAdvancesSlide"),
                "stageClickResolveMethod": adv.get("stageClickResolveMethod"),
                "onNextConditionCount": on_next,
                "advancementOnNextCount": adv.get("onNextConditionCount"),
                "animationTimelineMs": timeline.get("durationMs"),
                "rootCount": timeline.get("rootCount"),
                "behaviorKindCounts": behaviors,
                "hasSetOrEffect": any(
                    k.lower().find("set") >= 0 or k.lower().find("effect") >= 0 for k in behaviors
                ),
                "approximationNote": (
                    "Runtime plays OnNext queue + set/effect/animate first-pass; "
                    "multi-step dissolve trains may still approximate whole-shape."
                ),
            }
        )

    return {
        "format": "goblins-rpg3-opening-animation-trains-v1",
        "slides": list(OPENING_SLIDES),
        "summary": {
            "slideCount": len(rows),
            "totalOnNext": sum(r["onNextConditionCount"] for r in rows),
            "slidesWithSetOrEffect": sum(1 for r in rows if r["hasSetOrEffect"]),
        },
        "trains": rows,
        "runtimeSupport": {
            "onNextQueue": True,
            "setVisibility": True,
            "effectFadeDissolve": True,
            "paraBuildIterate": "whole-shape approximation (Phase 5.2 open)",
            "subEffectContainers": "not fully expanded (Phase 5.2 open)",
        },
    }


def main() -> None:
    game = load_json(ROOT / "docs" / "game-manifest.json")
    animations = load_json(ROOT / "docs" / "animation-manifest.json")
    out_dir = ROOT / "generated"
    out_dir.mkdir(parents=True, exist_ok=True)

    sequential = build_sequential_edges(game)
    timing = build_auto_advance_timing(game, animations)
    opening = build_opening_trains(game, animations)

    for name, payload in (
        ("sequential_advance_edges.json", sequential),
        ("auto_advance_timing.json", timing),
        ("opening_animation_trains.json", opening),
    ):
        path = out_dir / name
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8", newline="\n")
        print(f"Wrote {path}")

    print(
        f"stageClick={sequential['summary']['stageClickEdgeCount']} "
        f"(manual={sequential['summary']['manualAdvanceEdgeCount']} "
        f"fallback={sequential['summary']['fallbackStageClickEdgeCount']}) "
        f"auto={sequential['summary']['autoAdvanceEdgeCount']} "
        f"autoExtended={timing['summary']['extendedByAnimationCount']}"
    )


if __name__ == "__main__":
    main()
