"""Verify advancement model + game-manifest + runtime hooks stay aligned."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from advancement_lib import build_screen_advancement


def fail(message: str) -> None:
    raise SystemExit(message)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


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
    parser.add_argument("--advancement-model", type=Path, default=Path("generated/advancement_model.json"))
    parser.add_argument("--app", type=Path, default=Path("docs/app.js"))
    parser.add_argument("--animations", type=Path, default=Path("docs/animation-manifest.json"))
    args = parser.parse_args()

    if not args.game_manifest.exists():
        fail("game-manifest.json missing")
    if not args.app.exists():
        fail("docs/app.js missing")

    app_js = args.app.read_text(encoding="utf-8")
    for snippet in (
        "function handleStageClick",
        "function screenAllowsStageClickAdvance",
        "stageClickAdvancesSlide",
        "click-advance-slide",
        "advanceAnimation()",
    ):
        if snippet not in app_js:
            fail(f"runtime advancement hook missing: {snippet}")

    game = load_json(args.game_manifest)
    screens = game.get("screens") or []
    if len(screens) != 201:
        fail(f"expected 201 screens, found {len(screens)}")
    if not game.get("advancementPolicy"):
        fail("game-manifest missing advancementPolicy")
    policy_version = (game.get("advancementPolicy") or {}).get("version")
    if policy_version is None or int(policy_version) < 4:
        fail("advancementPolicy.version must be >= 4 (noop continue/mirror resolve policy)")

    animations = load_json(args.animations) if args.animations.exists() else {"slides": []}
    anim_by_slide = {int(s["slide"]): s for s in animations.get("slides") or []}

    missing_adv = [s["id"] for s in screens if "advancement" not in s]
    if missing_adv:
        fail(f"screens missing advancement block: {missing_adv[:5]}")

    # Recompute policy for every slide and compare stageClickAdvancesSlide / autoAdvance.
    mismatches = []
    for screen in screens:
        slide = int(screen["slide"])
        recomputed = build_screen_advancement(
            slide=slide,
            total_slides=len(screens),
            transition=screen.get("transition"),
            hotspots=screen.get("hotspots") or [],
            animation_slide=anim_by_slide.get(slide),
            layer_texts=layer_texts_for_screen(screen),
        )
        embedded = screen["advancement"]
        if bool(embedded.get("stageClickAdvancesSlide")) != bool(recomputed.get("stageClickAdvancesSlide")):
            mismatches.append(slide)
        if bool(embedded.get("autoAdvance")) != bool(recomputed.get("autoAdvance")):
            mismatches.append(slide)
    if mismatches:
        fail(f"advancement mismatch vs recomputed policy on slides {sorted(set(mismatches))[:10]}")

    # Known manualAdvance opening story slides must allow stage click advance.
    for slide in (3, 4, 5, 6, 7, 8):
        screen = screens[slide - 1]
        if not screen["advancement"].get("stageClickAdvancesSlide"):
            fail(f"slide {slide} should stageClickAdvancesSlide (manualAdvance)")
        if screen["advancement"].get("nextSequentialId") != f"slide-{slide + 1:03d}":
            fail(f"slide {slide} nextSequentialId wrong")

    # Hyperlink hub sample: slide 17 continue should not require stage click advance.
    s17 = screens[16]
    flags = (s17.get("transition") or {}).get("flagNames") or []
    if "manualAdvance" not in flags and s17["advancement"].get("stageClickAdvancesSlide"):
        fail("slide 17 should not stage-click advance without manualAdvance bit")

    # Working hyperlink fixture still present.
    cont = [
        h
        for h in s17.get("hotspots") or []
        if h.get("action") == "hyperlink" and h.get("targetSlide") == 22
    ]
    if not cont:
        fail("slide 17 hyperlink to slide 22 missing (regression oracle)")

    # Slide 2: binary self promoted to next (start continue policy).
    s2 = screens[1]
    if s2["advancement"].get("stageClickAdvancesSlide"):
        fail("slide 2 should not stage-click advance (leave via resolved start hotspot)")
    promoted = [
        h
        for h in s2.get("hotspots") or []
        if h.get("action") == "hyperlink"
        and h.get("resolveMethod") == "self_continue_to_next"
        and h.get("targetSlide") == 3
        and h.get("originalTargetSlide") == 2
    ]
    if not promoted:
        fail("slide 2 start hotspot should resolve self_continue_to_next → slide 3")
    if s2["advancement"].get("stuckReason"):
        fail(f"slide 2 should not be stuck after resolve, got {s2['advancement'].get('stuckReason')}")
    if "non_self_hyperlink" not in (s2["advancement"].get("leavePaths") or []):
        fail("slide 2 should have non_self_hyperlink leave path after promote")

    # Death terminals are not stuck.
    for slide in (30, 197):
        sc = screens[slide - 1]
        if not sc["advancement"].get("deathTerminal"):
            fail(f"slide {slide} should be deathTerminal")
        if sc["advancement"].get("stuckReason"):
            fail(f"slide {slide} death should not be stuck")
        if "restart_only" not in (sc["advancement"].get("leavePaths") or []):
            fail(f"slide {slide} should list restart_only leave path")
        if sc["advancement"].get("terminalKind") != "death":
            fail(f"slide {slide} terminalKind should be death")
        if not sc["advancement"].get("terminalNotes"):
            fail(f"slide {slide} missing terminalNotes")
    s200 = screens[199]
    if not s200["advancement"].get("deathTerminal"):
        fail("slide 200 should be deathTerminal (end card)")
    if s200["advancement"].get("terminalKind") != "end_card":
        fail("slide 200 terminalKind should be end_card")
    if "non_self_hyperlink" not in (s200["advancement"].get("leavePaths") or []):
        fail("slide 200 end card should keep hyperlink leave")

    # Slide 46 Ubergoblin: all combat options promote to death cutscene 47.
    s46 = screens[45]
    if s46["advancement"].get("stuckReason"):
        fail(f"slide 46 should not be stuck after combat_all_self resolve: {s46['advancement'].get('stuckReason')}")
    combat_promoted = [
        h
        for h in s46.get("hotspots") or []
        if h.get("action") == "hyperlink"
        and h.get("resolveMethod") == "combat_all_self_to_next_outcome"
        and h.get("targetSlide") == 47
        and h.get("originalTargetSlide") == 46
    ]
    if len(combat_promoted) < 3:
        fail(
            f"slide 46 expected 3 combat_all_self_to_next_outcome → 47 hotspots, "
            f"found {len(combat_promoted)}"
        )
    if "non_self_hyperlink" not in (s46["advancement"].get("leavePaths") or []):
        fail("slide 46 should leave via non_self_hyperlink after combat promote")

    # No residual stuck slides under policy v3.
    stuck = [s for s in screens if (s.get("advancement") or {}).get("stuckReason")]
    stuck_slides = sorted(int(s["slide"]) for s in stuck)
    if stuck_slides:
        fail(f"unexpected stuck slides after combat all-self resolve: {stuck_slides}")

    if args.advancement_model.exists():
        model = load_json(args.advancement_model)
        if model.get("format") != "goblins-rpg3-advancement-model-v1":
            fail("advancement_model format unexpected")
        if model.get("summary", {}).get("slideCount") != 201:
            fail("advancement_model slideCount unexpected")
        if model.get("summary", {}).get("stuckSlideCount") != 0:
            fail(
                f"expected 0 stuck slides after resolve, "
                f"found {model.get('summary', {}).get('stuckSlideCount')}"
            )

    print("advancement verification passed")


if __name__ == "__main__":
    main()
