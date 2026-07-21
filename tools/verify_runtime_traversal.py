"""Validate static game navigation semantics for the browser runtime.

This is intentionally browserless: it verifies that the generated manifest and
the small runtime agree on how hotspot clicks navigate, and it emits a graph
report that identifies terminal, unreachable, and cyclic screens for manual QA.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict, deque
from pathlib import Path
from typing import Any


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
                }
            )
    return edges


def verify_runtime_click_semantics(app_js: str) -> None:
    required_snippets = (
        "if (hotspot.targetSlide) {",
        "button.dataset.target = screenId(hotspot.targetSlide);",
        "event.stopPropagation();",
        "handleHotspotAction(hotspot);",
        "navigateTo(screenId(hotspot.targetSlide));",
    )
    for snippet in required_snippets:
        if snippet not in app_js:
            fail(f"runtime hotspot click snippet is missing: {snippet}")

    stage_click_match = re.search(
        r"stage\.addEventListener\(\"click\",\s*\(\)\s*=>\s*\{(?P<body>.*?)\}\);",
        app_js,
        flags=re.DOTALL,
    )
    if not stage_click_match:
        fail("stage background click handler is missing")
    stage_click_body = stage_click_match.group("body")
    if "navigateTo(" in stage_click_body:
        fail("blank-stage click handler must not navigate")
    if "advanceAnimation();" not in stage_click_body:
        fail("blank-stage click handler no longer advances queued animations")


def verify_edges(edges: list[dict[str, Any]], screen_ids: set[str]) -> None:
    missing_targets = [edge for edge in edges if edge["target"] not in screen_ids]
    if missing_targets:
        sample = ", ".join(edge["hotspotId"] or "unknown" for edge in missing_targets[:5])
        fail(f"hotspot targets missing screens: {sample}")

    invalid_sources = [edge for edge in edges if edge["source"] not in screen_ids]
    if invalid_sources:
        sample = ", ".join(edge["hotspotId"] or "unknown" for edge in invalid_sources[:5])
        fail(f"hotspot sources missing screens: {sample}")

    zero_area = []
    for edge in edges:
        bounds = edge.get("bounds") or {}
        if bounds.get("width", 0) <= 0 or bounds.get("height", 0) <= 0:
            zero_area.append(edge)
    if zero_area:
        sample = ", ".join(edge["hotspotId"] or "unknown" for edge in zero_area[:5])
        fail(f"enabled hotspots with zero area: {sample}")


def graph_summary(manifest: dict[str, Any], edges: list[dict[str, Any]]) -> dict[str, Any]:
    screens = manifest.get("screens", [])
    screen_ids = {screen["id"] for screen in screens}
    graph: dict[str, list[str]] = {screen_id_value: [] for screen_id_value in screen_ids}
    reverse_graph: dict[str, list[str]] = {screen_id_value: [] for screen_id_value in screen_ids}
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

    terminals = sorted(screen_id_value for screen_id_value, targets in graph.items() if not targets)
    unreachable = sorted(screen_ids - reachable)
    inbound_zero = sorted(screen_id_value for screen_id_value, sources in reverse_graph.items() if not sources)
    cyclic_nodes = sorted(nodes_in_cycles(graph))

    return {
        "screens": len(screen_ids),
        "edges": len(edges),
        "startScreen": start_screen,
        "reachableFromStart": len(reachable),
        "unreachableScreens": unreachable,
        "terminalScreens": terminals,
        "screensWithoutInboundEdges": inbound_zero,
        "cyclicScreens": cyclic_nodes,
    }


def nodes_in_cycles(graph: dict[str, list[str]]) -> set[str]:
    index = 0
    stack: list[str] = []
    on_stack: set[str] = set()
    indices: dict[str, int] = {}
    lowlinks: dict[str, int] = {}
    cyclic: set[str] = set()

    def strongconnect(node: str) -> None:
        nonlocal index
        indices[node] = index
        lowlinks[node] = index
        index += 1
        stack.append(node)
        on_stack.add(node)

        for target in graph.get(node, []):
            if target not in indices:
                strongconnect(target)
                lowlinks[node] = min(lowlinks[node], lowlinks[target])
            elif target in on_stack:
                lowlinks[node] = min(lowlinks[node], indices[target])

        if lowlinks[node] == indices[node]:
            component: list[str] = []
            while True:
                member = stack.pop()
                on_stack.remove(member)
                component.append(member)
                if member == node:
                    break
            if len(component) > 1:
                cyclic.update(component)
            elif component and component[0] in graph.get(component[0], []):
                cyclic.add(component[0])

    for node in graph:
        if node not in indices:
            strongconnect(node)
    return cyclic


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

    edges = enabled_hotspot_edges(manifest)
    verify_edges(edges, screen_ids)

    summary = graph_summary(manifest, edges)
    if summary["screens"] != 201:
        fail(f"expected 201 screens, found {summary['screens']}")
    if summary["edges"] != 194:
        fail(f"expected 194 enabled hotspot edges, found {summary['edges']}")

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(
            {
                "format": "goblins-rpg3-runtime-traversal-v1",
                "summary": {
                    "screens": summary["screens"],
                    "edges": summary["edges"],
                    "startScreen": summary["startScreen"],
                    "reachableFromStart": summary["reachableFromStart"],
                    "unreachableCount": len(summary["unreachableScreens"]),
                    "terminalCount": len(summary["terminalScreens"]),
                    "screensWithoutInboundEdgesCount": len(summary["screensWithoutInboundEdges"]),
                    "cyclicScreenCount": len(summary["cyclicScreens"]),
                },
                "unreachableScreens": summary["unreachableScreens"],
                "terminalScreens": summary["terminalScreens"],
                "screensWithoutInboundEdges": summary["screensWithoutInboundEdges"],
                "cyclicScreens": summary["cyclicScreens"],
                "edges": edges,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print(
        "runtime traversal verification passed: "
        f"{summary['edges']} edges, "
        f"{len(summary['unreachableScreens'])} unreachable screens reported, "
        f"{len(summary['cyclicScreens'])} cyclic screens reported"
    )


if __name__ == "__main__":
    main()
