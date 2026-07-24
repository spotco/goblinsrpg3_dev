"""Verify start-directed graph baseline and sealed-island analysis stay stable."""

from __future__ import annotations

import json
from pathlib import Path

from analyze_start_graph import EXPECTED_SEALED_ISLANDS, EXPECTED_START_REACHABLE, main as rebuild_analysis
from scan_advancement_coverage import build_runtime_out, bfs


def fail(message: str) -> None:
    raise SystemExit(message)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    game_path = root / "docs" / "game-manifest.json"
    analysis_path = root / "generated" / "start_graph_analysis.json"

    if not game_path.exists():
        fail("docs/game-manifest.json missing")

    # Rebuild analysis so verify is self-contained.
    rebuild_analysis()
    if not analysis_path.exists():
        fail("start_graph_analysis.json missing after rebuild")

    game = load_json(game_path)
    screens = game.get("screens") or []
    if len(screens) != 201:
        fail(f"expected 201 screens, found {len(screens)}")

    outbound = build_runtime_out(screens)
    from_start = bfs(outbound, 1)
    if from_start != set(EXPECTED_START_REACHABLE):
        missing = sorted(set(EXPECTED_START_REACHABLE) - from_start)
        extra = sorted(from_start - set(EXPECTED_START_REACHABLE))
        fail(
            "start reachability drifted from baseline "
            f"(missing={missing[:15]}, extra={extra[:15]}, count={len(from_start)})"
        )

    # Early loop still re-enters combat hub.
    if 21 not in outbound.get(42, set()):
        fail("s042 should still hyperlink/resolve to s021 (early loop re-entry)")

    # No edge from baseline set into sealed islands (binary+runtime).
    for island in EXPECTED_SEALED_ISLANDS:
        for slide in EXPECTED_START_REACHABLE:
            leaked = outbound.get(slide, set()) & island
            if leaked:
                fail(f"unexpected edge from start component s{slide} into island {sorted(leaked)}")

    # Island internals still leave-able (s046 combat promote etc.).
    s46 = screens[45]
    if s46["advancement"].get("stuckReason"):
        fail("s046 should remain leave-able after combat promote")
    combat = [
        h
        for h in s46.get("hotspots") or []
        if h.get("resolveMethod") == "combat_all_self_to_next_outcome" and h.get("targetSlide") == 47
    ]
    if len(combat) < 3:
        fail("s046 combat_all_self_to_next_outcome → 47 missing")

    analysis = load_json(analysis_path)
    summary = analysis.get("summary") or {}
    if not summary.get("sourceLimitation"):
        fail("analysis should mark sourceLimitation true until bridges proven")
    if summary.get("inventedBridgeApplied"):
        fail("inventedBridgeApplied should be false (no silent story bridges)")
    if summary.get("reachableFromStartCount") != len(EXPECTED_START_REACHABLE):
        fail("analysis reachable count mismatch")
    if not summary.get("matchesExpectedBaseline"):
        fail("analysis baseline match flag false")

    # s043 / s055 remain zero-inbound roots in analysis.
    zero = {int(z["slide"]) for z in analysis.get("zeroInboundSlides") or []}
    for root in (43, 55):
        if root not in zero:
            fail(f"expected zero-inbound root s{root:03d} still present")

    print("start graph verification passed")
    print(
        f"  reachableFromStart={len(from_start)} "
        f"sealedIslands={len(EXPECTED_SEALED_ISLANDS)} "
        f"sourceLimitation=true"
    )


if __name__ == "__main__":
    main()
