"""Verify Phase 5 fidelity offline contracts (sequential edges, auto timing, opening trains)."""

from __future__ import annotations

import json
from pathlib import Path

from build_fidelity_reports import main as rebuild_fidelity


def fail(message: str) -> None:
    raise SystemExit(message)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    rebuild_fidelity()

    app_js = (root / "docs" / "app.js").read_text(encoding="utf-8")
    game = load_json(root / "docs" / "game-manifest.json")

    # Runtime contracts for 5.3 / 5.5
    for snippet in (
        "Math.max(sourceDelayMs, animationTimeline.durationMs)",
        "function animationTimelineForScreen",
        "function handleStageClick",
        "function screenAllowsStageClickAdvance",
        "click-advance-slide",
        "advanceAnimation()",
    ):
        if snippet not in app_js:
            fail(f"runtime fidelity snippet missing: {snippet}")

    sequential = load_json(root / "generated" / "sequential_advance_edges.json")
    if sequential.get("format") != "goblins-rpg3-sequential-advance-edges-v1":
        fail("sequential_advance_edges format unexpected")
    summary = sequential.get("summary") or {}
    if summary.get("manualAdvanceEdgeCount") != 9:
        fail(
            f"expected 9 manualAdvance stage-click edges, "
            f"found {summary.get('manualAdvanceEdgeCount')}"
        )
    if summary.get("fallbackStageClickEdgeCount", 0) < 1:
        fail("expected at least one fallback stage-click edge")
    if summary.get("autoAdvanceEdgeCount") != 59:
        fail(f"expected 59 auto-advance edges, found {summary.get('autoAdvanceEdgeCount')}")

    # Opening manualAdvance story train 3-8, 12-13 present
    manual_from = {e["from"] for e in sequential.get("manualAdvanceEdges") or []}
    for slide in (3, 4, 5, 6, 7, 8, 12, 13):
        if slide not in manual_from:
            fail(f"manualAdvance edge missing from slide {slide}")
        # next is sequential
        edge = next(e for e in sequential["manualAdvanceEdges"] if e["from"] == slide)
        if edge["to"] != slide + 1:
            fail(f"slide {slide} stage-click next should be {slide + 1}, got {edge['to']}")

    # Manifest agrees
    for slide in (3, 4, 5, 6, 7, 8, 12, 13):
        adv = game["screens"][slide - 1]["advancement"]
        if not adv.get("stageClickAdvancesSlide"):
            fail(f"manifest slide {slide} should stageClickAdvancesSlide")
        if adv.get("nextSequentialId") != f"slide-{slide + 1:03d}":
            fail(f"manifest slide {slide} nextSequentialId wrong")

    timing = load_json(root / "generated" / "auto_advance_timing.json")
    if timing.get("format") != "goblins-rpg3-auto-advance-timing-v1":
        fail("auto_advance_timing format unexpected")
    if timing.get("summary", {}).get("autoAdvanceSlideCount") != 59:
        fail("auto_advance timing row count != 59")
    for row in timing.get("slides") or []:
        if row["effectiveDelayMs"] < row["slideTimeMs"]:
            fail(f"slide {row['slide']} effective delay < slideTimeMs")
        if row["effectiveDelayMs"] != max(row["slideTimeMs"], row["animationTimelineMs"]):
            fail(f"slide {row['slide']} effective delay math wrong")
        if row["slideTimeMs"] <= 0:
            fail(f"slide {row['slide']} autoAdvance with non-positive slideTime")

    opening = load_json(root / "generated" / "opening_animation_trains.json")
    if opening.get("format") != "goblins-rpg3-opening-animation-trains-v1":
        fail("opening_animation_trains format unexpected")
    if len(opening.get("trains") or []) != 9:
        fail("expected 9 opening train slides (3-8,12-14)")
    for train in opening.get("trains") or []:
        if train.get("onNextConditionCount") != train.get("advancementOnNextCount"):
            # allow if advancement recomputed differently — warn as fail if both present and differ
            if train.get("advancementOnNextCount") is not None:
                fail(
                    f"slide {train['slide']} onNext mismatch "
                    f"anim={train.get('onNextConditionCount')} "
                    f"adv={train.get('advancementOnNextCount')}"
                )
        if "subEffectCount" not in train:
            fail(f"slide {train['slide']} missing subEffectCount (Phase 5.2)")

    support = opening.get("runtimeSupport") or {}
    if "expanded" not in str(support.get("subEffectContainers") or "").lower():
        fail("runtimeSupport.subEffectContainers should report expanded (Phase 5.2)")
    if "Phase 5.2 open" in str(support.get("paraBuildIterate") or ""):
        fail("runtimeSupport still marks paraBuildIterate as Phase 5.2 open")
    if "Phase 5.4" not in str(support.get("motionPathSampling") or ""):
        fail("runtimeSupport.motionPathSampling should mention Phase 5.4")
    for snippet in (
        "function scheduleSubEffectNodes",
        "animation:subeffects-scheduled",
        "node.subEffects",
        "function sampleMotionPath",
        "function parseMotionPath",
        "function densifyMotionPath",
        "function pointOnCubic",
    ):
        if snippet not in app_js:
            fail(f"runtime fidelity snippet missing: {snippet}")

    motion = load_json(root / "generated" / "motion_path_inventory.json")
    if motion.get("format") != "goblins-rpg3-motion-path-inventory-v1":
        fail("motion_path_inventory format unexpected")
    msum = motion.get("summary") or {}
    if msum.get("motionPathCount") != 215:
        fail(f"expected 215 motion paths, found {msum.get('motionPathCount')}")
    if msum.get("cubicPathCount", 0) < 1:
        fail("expected at least one cubic motion path")
    if msum.get("linePathCount", 0) < 1:
        fail("expected at least one line motion path")
    fixtures = motion.get("fixtures") or {}
    line_end = fixtures.get("lineEndpoint") or {}
    if abs(float(line_end.get("x", -1)) - 1.0) > 1e-6 or abs(float(line_end.get("y", -1))) > 1e-6:
        fail(f"line fixture endpoint wrong: {line_end}")
    cubic_end = fixtures.get("cubicEndpoint") or {}
    if abs(float(cubic_end.get("x", -1)) - 1.0) > 1e-6 or abs(float(cubic_end.get("y", -1))) > 1e-6:
        fail(f"cubic fixture endpoint wrong: {cubic_end}")
    # Mid of M 0 0 C 0 1 1 1 1 0 at t=0.5 is y=0.75 analytically.
    mid_y = float(fixtures.get("cubicMidY") or 0)
    if mid_y < 0.5:
        fail(f"cubic mid Y too low for curved path (still endpoint-only?): {mid_y}")

    print("fidelity verification passed")
    print(
        f"  manualAdvanceEdges={summary['manualAdvanceEdgeCount']} "
        f"fallbackStageClick={summary['fallbackStageClickEdgeCount']} "
        f"autoEdges={summary['autoAdvanceEdgeCount']} "
        f"autoExtendedByAnim={timing['summary']['extendedByAnimationCount']}"
    )
    print(
        f"  opening trains onNext total={opening['summary']['totalOnNext']} "
        f"setOrEffectSlides={opening['summary']['slidesWithSetOrEffect']} "
        f"openingSubEffects={opening['summary'].get('openingSubEffectCount')} "
        f"deckSubEffects={opening['summary'].get('deckSubEffectContainers')}"
    )
    print(
        f"  motionPaths={msum.get('motionPathCount')} "
        f"line={msum.get('linePathCount')} cubic={msum.get('cubicPathCount')} "
        f"polyline={msum.get('polylinePathCount')}"
    )


if __name__ == "__main__":
    main()
