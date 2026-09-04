"""Phase 5 fidelity offline reports: sequential edges, auto-advance timing, opening trains, motion paths.

Writes:
  generated/sequential_advance_edges.json
  generated/auto_advance_timing.json
  generated/opening_animation_trains.json
  generated/motion_path_inventory.json
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from animation_timeline import (
    count_iterate,
    count_on_next,
    count_sub_effects,
    inventory_behaviors,
    inventory_builds,
    slide_animation_timeline,
)
from motion_path_lib import classify_path, motion_endpoint, sample_motion_path

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
        builds = inventory_builds(anim)
        on_next = count_on_next(anim)
        sub_effects = count_sub_effects(anim)
        iterate_count = count_iterate(anim)
        para_names = set(builds.keys())
        # AsAWhole / allAtOnce are correct as whole-shape; letter/word iterate is residual.
        if iterate_count:
            approx = (
                "TimeIterateData present (byWord/byLetter) — runtime still applies "
                "whole-shape; letter/word stagger residual (Phase 5.2.1)."
            )
        elif para_names and para_names <= {"asAWhole", "allAtOnce"}:
            approx = (
                "ParaBuild is asAWhole/allAtOnce — whole-shape playback matches PPT build mode; "
                "AfterEffect Hide-on-Next-Click subEffects defer to next OnNext; "
                "other subEffects schedule with parent / OnEnd triggers."
            )
        elif para_names:
            approx = (
                f"ParaBuild modes {sorted(para_names)} — level/custom builds still whole-shape "
                "unless multi-paragraph DOM split is added (Phase 5.2.1)."
            )
        else:
            approx = "No ParaBuild on this slide; subEffects expanded when present."
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
                "subEffectCount": sub_effects,
                "paraBuildKindCounts": builds,
                "iterateDataCount": iterate_count,
                "hasSetOrEffect": any(
                    k.lower().find("set") >= 0 or k.lower().find("effect") >= 0 for k in behaviors
                ),
                "approximationNote": approx,
            }
        )

    anim_summary = animations.get("summary") or {}
    return {
        "format": "goblins-rpg3-opening-animation-trains-v1",
        "slides": list(OPENING_SLIDES),
        "summary": {
            "slideCount": len(rows),
            "totalOnNext": sum(r["onNextConditionCount"] for r in rows),
            "slidesWithSetOrEffect": sum(1 for r in rows if r["hasSetOrEffect"]),
            "openingSubEffectCount": sum(r["subEffectCount"] for r in rows),
            "openingParaBuildCount": sum(sum(r["paraBuildKindCounts"].values()) for r in rows),
            "openingIterateCount": sum(r["iterateDataCount"] for r in rows),
            "deckSubEffectContainers": anim_summary.get("subEffectContainers"),
            "deckParaBuildCount": anim_summary.get("paraBuildCount"),
            "deckIterateDataCount": anim_summary.get("iterateDataCount"),
            "deckParaBuildKinds": anim_summary.get("paraBuildKinds"),
            "deckIterateKinds": anim_summary.get("iterateKinds"),
        },
        "trains": rows,
        "runtimeSupport": {
            "onNextQueue": True,
            "setVisibility": True,
            "effectFadeDissolve": True,
            "subEffectContainers": "expanded as node.subEffects; scheduled with parent (Phase 5.2)",
            "paraBuildAsAWhole": "decoded + whole-shape correct for TLPB_AsAWhole (Phase 5.2)",
            "paraBuildByLevel": "decoded; multi-paragraph level builds residual (Phase 5.2.1)",
            "timeIterateByWordLetter": "decoded; runtime whole-shape residual (Phase 5.2.1)",
            "motionPathSampling": "arc-length M/L/C samples (Phase 5.4); rotation/color/filter absent in deck",
        },
    }


def _walk_nodes(roots: list) -> list:
    stack = list(roots or [])
    nodes = []
    while stack:
        node = stack.pop()
        nodes.append(node)
        stack.extend(node.get("subEffects") or [])
        stack.extend(node.get("children") or [])
    return nodes


def build_motion_path_inventory(animations: dict) -> dict:
    kind_counts: Counter[str] = Counter()
    paths: list[dict] = []
    complex_examples: list[dict] = []
    invalid = 0
    for slide_entry in animations.get("slides") or []:
        slide = int(slide_entry["slide"])
        for node in _walk_nodes(slide_entry.get("rootTimeNodes") or []):
            for behavior in node.get("behaviors") or []:
                if behavior.get("kind") != "motion":
                    continue
                path = None
                for variant in behavior.get("variants") or []:
                    parsed = variant.get("parsed") or {}
                    value = parsed.get("stringValue")
                    if isinstance(value, str) and value.lstrip().upper().startswith("M"):
                        path = value
                        break
                if not path:
                    invalid += 1
                    kind_counts["missing_path"] += 1
                    continue
                kind = classify_path(path)
                kind_counts[kind] += 1
                sampled = sample_motion_path(path, sample_count=48)
                endpoint = motion_endpoint(path)
                row = {
                    "slide": slide,
                    "nodeId": node.get("id"),
                    "kind": kind,
                    "endpoint": endpoint,
                    "sampleCount": (sampled or {}).get("sampleCount"),
                    "pathLengthEstimate": (sampled or {}).get("pathLengthEstimate"),
                    "commandKey": ((sampled or {}).get("parsed") or {}).get("commandKey"),
                    "segmentCount": ((sampled or {}).get("parsed") or {}).get("segmentCount"),
                    "pathPreview": path[:120],
                }
                paths.append(row)
                if kind == "cubic" and len(complex_examples) < 12:
                    mid = (sampled or {}).get("midpoint")
                    complex_examples.append(
                        {
                            **row,
                            "start": ((sampled or {}).get("parsed") or {}).get("start"),
                            "midpoint": mid,
                            "end": endpoint,
                        }
                    )

    # Unit fixtures: offline contract for sampler math.
    line = sample_motion_path("M 0 0 L 1 0 ", sample_count=5)
    cubic = sample_motion_path("M 0 0 C 0 1 1 1 1 0 ", sample_count=5)
    fixtures = {
        "lineEndpoint": (line or {}).get("endpoint"),
        "lineSampleCount": (line or {}).get("sampleCount"),
        "cubicEndpoint": (cubic or {}).get("endpoint"),
        "cubicMidY": ((cubic or {}).get("midpoint") or {}).get("y"),
        "cubicKind": ((cubic or {}).get("parsed") or {}).get("kind"),
    }

    return {
        "format": "goblins-rpg3-motion-path-inventory-v1",
        "policy": (
            "Runtime samples M/L/C paths by approximate arc length (48 samples); "
            "applies multi-keyframe WAAPI transform. Endpoint matches path end. "
            "Rotation/color/filter property anims: none observed in this deck."
        ),
        "summary": {
            "motionPathCount": len(paths),
            "invalidOrMissingPathCount": invalid,
            "kindCounts": dict(sorted(kind_counts.items())),
            "slidesWithMotion": len({row["slide"] for row in paths}),
            "cubicPathCount": kind_counts.get("cubic", 0),
            "linePathCount": kind_counts.get("line", 0),
            "polylinePathCount": kind_counts.get("polyline", 0),
            "rotationColorFilterInDeck": False,
        },
        "fixtures": fixtures,
        "complexExamples": complex_examples,
        "paths": paths,
        "runtimeSupport": {
            "motionPathSampling": True,
            "commands": ["M", "L", "C", "Z"],
            "sampleCountDefault": 48,
            "rotation": "not present in deck variants",
            "color": "not present in deck variants",
            "filter": "not present in deck variants",
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
    motion = build_motion_path_inventory(animations)

    for name, payload in (
        ("sequential_advance_edges.json", sequential),
        ("auto_advance_timing.json", timing),
        ("opening_animation_trains.json", opening),
        ("motion_path_inventory.json", motion),
    ):
        path = out_dir / name
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8", newline="\n")
        print(f"Wrote {path}")

    print(
        f"stageClick={sequential['summary']['stageClickEdgeCount']} "
        f"(manual={sequential['summary']['manualAdvanceEdgeCount']} "
        f"fallback={sequential['summary']['fallbackStageClickEdgeCount']}) "
        f"auto={sequential['summary']['autoAdvanceEdgeCount']} "
        f"autoExtended={timing['summary']['extendedByAnimationCount']} "
        f"motionPaths={motion['summary']['motionPathCount']} "
        f"cubic={motion['summary']['cubicPathCount']}"
    )


if __name__ == "__main__":
    main()
