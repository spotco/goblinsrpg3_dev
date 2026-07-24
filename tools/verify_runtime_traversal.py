"""Validate static game navigation semantics for the browser runtime.

Browserless checks:
- Hotspot click wiring in app.js
- Stage continuum: anim queue → click-advance → no-op
- Enabled hotspot edges + sequential click-advance + auto-advance edges
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

from build_fidelity_reports import build_sequential_edges


def fail(message: str) -> None:
    raise SystemExit(message)


def screen_id(slide: int) -> str:
    return f"slide-{slide:03d}"


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def enabled_hotspot_edges(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    edges: list[dict[str, Any]] = []
    for screen in manifest.get("screens", []):
        source_id = screen.get("id")
        source_slide = screen.get("slide")
        for hotspot in screen.get("hotspots", []):
            if not hotspot.get("enabled"):
                continue
            target_slide = hotspot.get("targetSlide")
            if target_slide is None:
                continue
            edges.append(
                {
                    "source": source_id,
                    "sourceSlide": source_slide,
                    "hotspotId": hotspot.get("id"),
                    "shapeId": hotspot.get("shapeId"),
                    "target": screen_id(int(target_slide)),
                    "targetSlide": int(target_slide),
                    "bounds": hotspot.get("bounds") or {},
                    "kind": "hotspot",
                }
            )
    return edges


def verify_runtime_click_semantics(app_js: str) -> None:
    required_snippets = (
        "if (hotspot.targetSlide) {",
        "button.dataset.target = screenId(hotspot.targetSlide);",
        "event.stopPropagation();",
        "handleHotspotAction(hotspot);",
        "navigateTo(screenId(hotspot.targetSlide)",
        "function handleStageClick",
        "function screenAllowsStageClickAdvance",
        "advanceAnimation()",
        "click-advance-slide",
        "Math.max(sourceDelayMs, animationTimeline.durationMs)",
    )
    for snippet in required_snippets:
        if snippet not in app_js:
            fail(f"runtime navigation snippet is missing: {snippet}")

    # Stage listener must delegate to continuum handler (not always navigate).
    if 'stage.addEventListener("click"' not in app_js and "stage.addEventListener('click'" not in app_js:
        fail("stage click listener is missing")
    if "handleStageClick()" not in app_js:
        fail("stage click must call handleStageClick()")


def verify_edges(edges: list[dict[str, Any]], screen_ids: set[str]) -> None:
    missing_targets = [edge for edge in edges if edge["target"] not in screen_ids]
    if missing_targets:
        sample = ", ".join(str(edge.get("hotspotId") or edge.get("kind")) for edge in missing_targets[:5])
        fail(f"edge targets missing screens: {sample}")

    zero_area = []
    for edge in edges:
        if edge.get("kind") != "hotspot":
            continue
        bounds = edge.get("bounds") or {}
        if bounds.get("width", 0) <= 0 or bounds.get("height", 0) <= 0:
            zero_area.append(edge)
    if zero_area:
        sample = ", ".join(edge["hotspotId"] or "unknown" for edge in zero_area[:5])
        fail(f"enabled hotspots with zero area: {sample}")


def graph_summary(manifest: dict[str, Any], edges: list[dict[str, Any]]) -> dict[str, Any]:
    screens = manifest.get("screens", [])
    screen_ids = {screen["id"] for screen in screens}
    graph: dict[str, list[str]] = {sid: [] for sid in screen_ids}
    reverse_graph: dict[str, list[str]] = {sid: [] for sid in screen_ids}
    for edge in edges:
        graph[edge["source"]].append(edge["target"])
        reverse_graph[edge["target"]].append(edge["source"])

    start_screen = manifest.get("startScreen")
    reachable: set[str] = set()
    if start_screen in screen_ids:
        queue: deque[str] = deque([start_screen])
        reachable.add(start_screen)
        while queue:
            current = queue.popleft()
            for target in graph[current]:
                if target not in reachable:
                    reachable.add(target)
                    queue.append(target)

    terminals = sorted(sid for sid, targets in graph.items() if not targets)
    unreachable = sorted(screen_ids - reachable)
    inbound_zero = sorted(sid for sid, sources in reverse_graph.items() if not sources)

    return {
        "screens": len(screen_ids),
        "edges": len(edges),
        "startScreen": start_screen,
        "reachableFromStart": len(reachable),
        "unreachableScreens": unreachable,
        "terminalScreens": terminals,
        "screensWithoutInboundEdges": inbound_zero,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path("docs/game-manifest.json"))
    parser.add_argument("--app", type=Path, default=Path("docs/app.js"))
    parser.add_argument("--report", type=Path, default=Path("generated/runtime_traversal.json"))
    args = parser.parse_args()

    if not args.manifest.exists():
        fail(f"manifest is missing: {args.manifest}")
    if not args.app.exists():
        fail(f"runtime is missing: {args.app}")

    manifest = load_json(args.manifest)
    app_js = args.app.read_text(encoding="utf-8")
    verify_runtime_click_semantics(app_js)

    screens = manifest.get("screens", [])
    screen_ids = {screen["id"] for screen in screens}
    if manifest.get("startScreen") not in screen_ids:
        fail("start screen is not present in manifest screens")

    hotspot_edges = enabled_hotspot_edges(manifest)
    verify_edges(hotspot_edges, screen_ids)

    sequential = build_sequential_edges(manifest)
    seq_edges = []
    for edge in sequential.get("allSequentialEdges") or []:
        seq_edges.append(
            {
                "source": screen_id(int(edge["from"])),
                "sourceSlide": int(edge["from"]),
                "target": edge["toId"],
                "targetSlide": int(edge["to"]),
                "kind": edge["kind"],
                "resolveMethod": edge.get("resolveMethod"),
                "delayMs": edge.get("delayMs"),
            }
        )
    verify_edges(seq_edges, screen_ids)

    if sequential["summary"]["manualAdvanceEdgeCount"] != 9:
        fail(
            f"expected 9 manualAdvance sequential edges, "
            f"found {sequential['summary']['manualAdvanceEdgeCount']}"
        )
    if sequential["summary"]["autoAdvanceEdgeCount"] != 59:
        fail(
            f"expected 59 autoAdvance sequential edges, "
            f"found {sequential['summary']['autoAdvanceEdgeCount']}"
        )

    # Combined graph for QA report (hotspot + sequential)
    combined = hotspot_edges + seq_edges
    summary = graph_summary(manifest, combined)
    if summary["screens"] != 201:
        fail(f"expected 201 screens, found {summary['screens']}")

    # Hotspot-only edge count is policy-dependent (binary 194 + noop promotes - residual)
    if len(hotspot_edges) < 194:
        fail(f"hotspot edges regressed below 194: {len(hotspot_edges)}")

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(
            {
                "format": "goblins-rpg3-runtime-traversal-v2",
                "summary": {
                    "screens": summary["screens"],
                    "hotspotEdges": len(hotspot_edges),
                    "sequentialEdges": len(seq_edges),
                    "manualAdvanceEdges": sequential["summary"]["manualAdvanceEdgeCount"],
                    "fallbackStageClickEdges": sequential["summary"]["fallbackStageClickEdgeCount"],
                    "autoAdvanceEdges": sequential["summary"]["autoAdvanceEdgeCount"],
                    "combinedEdges": len(combined),
                    "startScreen": summary["startScreen"],
                    "reachableFromStartCombined": summary["reachableFromStart"],
                    "unreachableCount": len(summary["unreachableScreens"]),
                    "terminalCount": len(summary["terminalScreens"]),
                },
                "sequentialAdvance": sequential["summary"],
                "unreachableScreens": summary["unreachableScreens"],
                "terminalScreens": summary["terminalScreens"],
                "hotspotEdges": hotspot_edges,
                "sequentialEdges": seq_edges,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print(
        "runtime traversal verification passed: "
        f"{len(hotspot_edges)} hotspot edges, "
        f"{sequential['summary']['manualAdvanceEdgeCount']} manualAdvance, "
        f"{sequential['summary']['fallbackStageClickEdgeCount']} fallback stage-click, "
        f"{sequential['summary']['autoAdvanceEdgeCount']} auto-advance, "
        f"combined reachability from start={summary['reachableFromStart']}"
    )


if __name__ == "__main__":
    main()
