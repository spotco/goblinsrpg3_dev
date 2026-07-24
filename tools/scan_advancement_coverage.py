"""Deck-wide scan: leave paths, residual selfs, reachability, policy coverage.

Writes generated/advancement_coverage_scan.json for plan residual tracking.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict, deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def build_runtime_out(screens: list[dict]) -> dict[int, set[int]]:
    outbound: dict[int, set[int]] = defaultdict(set)
    for sc in screens:
        slide = int(sc["slide"])
        adv = sc.get("advancement") or {}
        for h in sc.get("hotspots") or []:
            if h.get("action") == "hyperlink" and h.get("targetSlide") is not None:
                outbound[slide].add(int(h["targetSlide"]))
        if adv.get("autoAdvance") or adv.get("stageClickAdvancesSlide"):
            nxt = adv.get("nextSequentialSlide")
            if nxt is not None:
                outbound[slide].add(int(nxt))
    return outbound


def bfs(outbound: dict[int, set[int]], start: int) -> set[int]:
    seen: set[int] = set()
    q: deque[int] = deque([start])
    while q:
        cur = q.popleft()
        if cur in seen:
            continue
        seen.add(cur)
        for t in outbound.get(cur, ()):
            if t not in seen:
                q.append(t)
    return seen


def weakly_connected_components(outbound: dict[int, set[int]], total: int) -> list[list[int]]:
    undirected: dict[int, set[int]] = defaultdict(set)
    for s in range(1, total + 1):
        undirected.setdefault(s, set())
        for t in outbound.get(s, ()):
            undirected[s].add(t)
            undirected[t].add(s)
    seen: set[int] = set()
    comps: list[list[int]] = []
    for s in range(1, total + 1):
        if s in seen:
            continue
        stack = [s]
        comp: list[int] = []
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            comp.append(cur)
            stack.extend(undirected.get(cur, ()))
        comps.append(sorted(comp))
    comps.sort(key=len, reverse=True)
    return comps


def main() -> None:
    game = load_json(ROOT / "docs" / "game-manifest.json")
    model_path = ROOT / "generated" / "advancement_model.json"
    model = load_json(model_path) if model_path.exists() else {}

    screens = game.get("screens") or []
    total = len(screens)
    outbound = build_runtime_out(screens)

    leave_methods: Counter[str] = Counter()
    stuck = []
    death_terminals = []
    runtime_selfs = []
    resolve_methods: Counter[str] = Counter()
    stage_click_methods: Counter[str] = Counter()

    for sc in screens:
        slide = int(sc["slide"])
        adv = sc.get("advancement") or {}
        for path in adv.get("leavePaths") or []:
            leave_methods[path] += 1
        if adv.get("stuckReason"):
            stuck.append({"slide": slide, "reason": adv["stuckReason"], "modes": adv.get("modes")})
        if adv.get("deathTerminal"):
            death_terminals.append(slide)
        if adv.get("stageClickResolveMethod"):
            stage_click_methods[str(adv["stageClickResolveMethod"])] += 1

        for h in sc.get("hotspots") or []:
            method = h.get("resolveMethod")
            if method:
                resolve_methods[str(method)] += 1
            if h.get("action") == "hyperlink" and h.get("targetSlide") is not None:
                t = int(h["targetSlide"])
                if t == slide:
                    runtime_selfs.append(
                        {
                            "slide": slide,
                            "shapeId": h.get("shapeId"),
                            "shapeText": h.get("shapeText"),
                            "resolveMethod": h.get("resolveMethod"),
                        }
                    )

    from_start = bfs(outbound, 1)
    unreachable = sorted(set(range(1, total + 1)) - from_start)
    components = weakly_connected_components(outbound, total)

    # Linear sequential islands (only connected by auto/stage next, no hyperlink entry)
    sequential_only_entry = []
    for slide in range(2, total + 1):
        prev = screens[slide - 2]
        prev_adv = prev.get("advancement") or {}
        hyper_in = any(
            h.get("action") == "hyperlink" and h.get("targetSlide") == slide
            for sc in screens
            for h in sc.get("hotspots") or []
        )
        seq_in = bool(
            prev_adv.get("nextSequentialSlide") == slide
            and (prev_adv.get("autoAdvance") or prev_adv.get("stageClickAdvancesSlide"))
        )
        if seq_in and not hyper_in and slide not in from_start:
            sequential_only_entry.append(slide)

    # Early→mid gap: any edge from start-reachable set to unreachable?
    bridge_edges = []
    for s in sorted(from_start):
        for t in sorted(outbound.get(s, ())):
            if t not in from_start:
                bridge_edges.append({"from": s, "to": t})

    start_analysis_path = ROOT / "generated" / "start_graph_analysis.json"
    start_analysis = load_json(start_analysis_path) if start_analysis_path.exists() else {}

    report = {
        "format": "goblins-rpg3-advancement-coverage-scan-v1",
        "advancementPolicyVersion": (game.get("advancementPolicy") or {}).get("version"),
        "summary": {
            "slideCount": total,
            "stuckCount": len(stuck),
            "stuckSlides": stuck,
            "deathTerminalSlides": death_terminals,
            "runtimeSelfHyperlinkCount": len(runtime_selfs),
            "reachableFromStartCount": len(from_start),
            "unreachableFromStartCount": len(unreachable),
            "weakComponentCount": len(components),
            "largestWeakComponentSize": len(components[0]) if components else 0,
            "leavePathCounts": dict(leave_methods),
            "resolveMethodCounts": dict(resolve_methods),
            "stageClickResolveMethodCounts": dict(stage_click_methods),
            "modelStuckCount": (model.get("summary") or {}).get("stuckSlideCount"),
            "bridgeEdgesFromStartComponent": len(bridge_edges),
            "startGraphSourceLimitation": (start_analysis.get("summary") or {}).get("sourceLimitation"),
            "startGraphZeroInboundCount": (start_analysis.get("summary") or {}).get("zeroInboundCount"),
        },
        "stuckSlides": stuck,
        "deathTerminalSlides": death_terminals,
        "runtimeSelfHyperlinks": runtime_selfs,
        "reachableFromStart": sorted(from_start),
        "unreachableFromStartSample": unreachable[:40],
        "weakComponentsTop": [
            {"size": len(c), "slidesSample": c[:20], "min": c[0], "max": c[-1]} for c in components[:12]
        ],
        "bridgeEdgesFromStartComponent": bridge_edges,
        "sequentialOnlyEntryUnreachableSample": sequential_only_entry[:30],
        "notes": [
            "Leave-path coverage (stuckCount==0) means every slide has a decoded leave method under policy v3.",
            "Reachability from slide 1 uses post-resolve hyperlinks + auto/stage sequential next.",
            "Death terminals leave via restart_only (not graph edges to other story slides).",
            "Runtime selfs that remain are partial combat no-ops or image selfs with other leave paths.",
            "If reachableFromStart << slideCount and bridgeEdges is empty, mid/late content is a separate "
            "component (missing extract edge, or original PPT island). That is residual graph work, not stuck leave.",
        ],
        "leavePathCoverageOk": len(stuck) == 0,
        "startGraphFullyConnected": len(unreachable) == 0,
    }

    out = ROOT / "generated" / "advancement_coverage_scan.json"
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"Wrote {out}")
    print(
        f"stuck={report['summary']['stuckCount']} "
        f"reachableFromStart={report['summary']['reachableFromStartCount']}/{total} "
        f"weakComponents={report['summary']['weakComponentCount']} "
        f"runtimeSelfs={report['summary']['runtimeSelfHyperlinkCount']}"
    )
    print(f"resolveMethods={report['summary']['resolveMethodCounts']}")
    print(f"leavePathCoverageOk={report['leavePathCoverageOk']}")
    print(f"startGraphFullyConnected={report['startGraphFullyConnected']}")
    if stuck:
        print("STUCK:", stuck)
    if runtime_selfs:
        print("runtime selfs:")
        for item in runtime_selfs:
            print(f"  s{item['slide']:03d} {item.get('shapeText')!r} {item.get('resolveMethod')}")
    print("top weak components:")
    for c in report["weakComponentsTop"][:6]:
        print(f"  size={c['size']} range={c['min']}-{c['max']} sample={c['slidesSample'][:12]}")


if __name__ == "__main__":
    main()
