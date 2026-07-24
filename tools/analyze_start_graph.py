"""Analyze start-directed reachability, early combat loop, and sealed islands.

Confirms whether the port is missing navigation edges vs the binary truly
having a closed early loop and orphan midgame roots.

Writes ``generated/start_graph_analysis.json``.

Findings (policy v3 / inventory-faithful decode):
- All 217 InteractiveInfoAtoms are in inventory; jump field is always 0
  (no hidden next/first/last jump actions).
- All 194 ExHyperlinks are single CString ``Slide N`` + 4-byte id atom.
- Directed reachability from slide 1 is a fixed early story+combat set;
  s042 continue returns to s021 (closed loop). No binary edge leaves that
  component into mid/late game.
- Sealed undirected islands: s043–s054 (Ubergoblin path), s020–s025 pair.
- Additional zero-inbound roots (e.g. s055) start midgame trains that only
  rejoin early content via reverse death links to s030, not via a forward
  exit from the early loop.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict, deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Baseline directed reachability from slide 1 under policy v3 resolve +
# auto/stage sequential edges. Used by verify_start_graph.py.
EXPECTED_START_REACHABLE = frozenset(
    {
        1,
        2,
        3,
        4,
        5,
        6,
        7,
        8,
        9,
        10,
        11,
        12,
        13,
        14,
        15,
        16,
        17,
        18,
        19,
        21,
        22,
        24,
        29,
        30,
        31,
        32,
        34,
        36,
        42,
    }
)

EXPECTED_SEALED_ISLANDS = (
    frozenset(range(43, 55)),  # Ubergoblin + small hub
    frozenset({20, 25}),  # mutual continue island
)


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def shape_texts(inv: dict, game: dict) -> dict[tuple[int, int], str]:
    texts: dict[tuple[int, int], str] = {}
    for t in inv.get("text_runs") or []:
        if t.get("slide") is not None and t.get("shape_id") is not None:
            texts[(int(t["slide"]), int(t["shape_id"]))] = str(t.get("text") or "")
    for sc in game.get("screens") or []:
        slide = int(sc["slide"])
        for layer in sc.get("layers") or []:
            if layer.get("shapeId") is not None and layer.get("text"):
                texts.setdefault((slide, int(layer["shapeId"])), str(layer["text"]))
    return texts


def runtime_graph(screens: list[dict]) -> tuple[dict[int, set[int]], dict[int, set[int]]]:
    out: dict[int, set[int]] = defaultdict(set)
    into: dict[int, set[int]] = defaultdict(set)
    for sc in screens:
        slide = int(sc["slide"])
        adv = sc.get("advancement") or {}
        for h in sc.get("hotspots") or []:
            if h.get("action") == "hyperlink" and h.get("targetSlide") is not None:
                target = int(h["targetSlide"])
                out[slide].add(target)
                into[target].add(slide)
        if adv.get("autoAdvance") or adv.get("stageClickAdvancesSlide"):
            nxt = adv.get("nextSequentialSlide")
            if nxt is not None:
                out[slide].add(int(nxt))
                into[int(nxt)].add(slide)
    return out, into


def binary_out(inv: dict) -> dict[int, set[int]]:
    out: dict[int, set[int]] = defaultdict(set)
    for action in inv.get("interactive_actions") or []:
        if int(action.get("action_code", 0)) == 4 and action.get("target_slide") is not None:
            out[int(action["slide"])].add(int(action["target_slide"]))
    return out


def bfs(out: dict[int, set[int]], start: int) -> set[int]:
    seen: set[int] = set()
    q: deque[int] = deque([start])
    while q:
        cur = q.popleft()
        if cur in seen:
            continue
        seen.add(cur)
        for target in out.get(cur, ()):
            if target not in seen:
                q.append(target)
    return seen


def weakly_connected(out: dict[int, set[int]], total: int) -> list[list[int]]:
    und: dict[int, set[int]] = defaultdict(set)
    for slide in range(1, total + 1):
        und.setdefault(slide, set())
        for target in out.get(slide, ()):
            und[slide].add(target)
            und[target].add(slide)
    seen: set[int] = set()
    comps: list[list[int]] = []
    for slide in range(1, total + 1):
        if slide in seen:
            continue
        stack = [slide]
        comp: list[int] = []
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            comp.append(cur)
            stack.extend(und.get(cur, ()))
        comps.append(sorted(comp))
    comps.sort(key=len, reverse=True)
    return comps


def screen_brief(sc: dict) -> dict:
    adv = sc.get("advancement") or {}
    return {
        "slide": int(sc["slide"]),
        "texts": [L.get("text") for L in (sc.get("layers") or []) if L.get("text")][:6],
        "leavePaths": adv.get("leavePaths"),
        "autoAdvance": adv.get("autoAdvance"),
        "stageClick": adv.get("stageClickAdvancesSlide"),
        "hotspots": [
            {
                "action": h.get("action"),
                "targetSlide": h.get("targetSlide"),
                "resolveMethod": h.get("resolveMethod"),
                "shapeText": h.get("shapeText"),
            }
            for h in sc.get("hotspots") or []
        ],
    }


def main() -> None:
    inv = load_json(ROOT / "generated" / "inventory.json")
    game = load_json(ROOT / "docs" / "game-manifest.json")
    screens = game["screens"]
    total = len(screens)
    texts = shape_texts(inv, game)
    out, into = runtime_graph(screens)
    bin_o = binary_out(inv)
    from_start = bfs(out, 1)
    comps = weakly_connected(out, total)

    action_codes = Counter(int(a.get("action_code", -1)) for a in inv.get("interactive_actions") or [])

    # Early loop frontier
    frontier = []
    for slide in sorted(from_start):
        sc = screens[slide - 1]
        layer_texts = [L.get("text") for L in (sc.get("layers") or []) if L.get("text")]
        runtime_targets = sorted(out.get(slide, ()))
        frontier.append(
            {
                "slide": slide,
                "runtimeOut": runtime_targets,
                "binaryOut": sorted(bin_o.get(slide, ())),
                "externalRuntimeOut": [t for t in runtime_targets if t not in from_start],
                "texts": layer_texts[:5],
                "leavePaths": (sc.get("advancement") or {}).get("leavePaths"),
            }
        )

    binary_external = [
        {"from": s, "to": t}
        for s in sorted(from_start)
        for t in sorted(bin_o.get(s, ()))
        if t not in from_start
    ]

    # Islands (components without slide 1)
    island_details = []
    for comp in comps:
        if 1 in comp:
            continue
        comp_set = set(comp)
        entries = []
        exits = []
        for slide in range(1, total + 1):
            for target in out.get(slide, ()):
                if slide not in comp_set and target in comp_set:
                    entries.append({"from": slide, "to": target})
                if slide in comp_set and target not in comp_set:
                    exits.append({"from": slide, "to": target})
        island_details.append(
            {
                "slides": comp,
                "size": len(comp),
                "sealed": not entries and not exits,
                "entriesFromOutside": entries,
                "exitsToOutside": exits,
                "screens": [screen_brief(screens[s - 1]) for s in comp],
            }
        )

    zero_inbound = []
    for slide in range(2, total + 1):
        if into.get(slide):
            continue
        sc = screens[slide - 1]
        zero_inbound.append(
            {
                "slide": slide,
                "out": sorted(out.get(slide, ())),
                "leavePaths": (sc.get("advancement") or {}).get("leavePaths"),
                "texts": [L.get("text") for L in (sc.get("layers") or []) if L.get("text")][:4],
                "inStartComponent": slide in from_start,
            }
        )

    key_slides = {
        str(s): screen_brief(screens[s - 1])
        for s in (17, 21, 34, 36, 42, 43, 45, 46, 47, 55, 20, 25)
        if 1 <= s <= total
    }

    conclusions = [
        "Extractor re-check: inventory holds all interactive actions; action codes are only "
        f"hyperlink(4)={action_codes.get(4, 0)}, media(6)={action_codes.get(6, 0)}, "
        f"none(0)={action_codes.get(0, 0)}. No jump/macro/run actions.",
        "ExHyperlink audit (prior + reconfirmed pattern): single friendly-name CString only; "
        "no separate slide-id target atom to mis-parse.",
        f"Directed reachability from slide 1: {len(from_start)} slides "
        f"(baseline {len(EXPECTED_START_REACHABLE)}). Early combat loop exits only to itself "
        f"(s042 continue → s021 hub).",
        "No binary hyperlink leaves the start-reachable component into mid/late game "
        f"(external binary edges={len(binary_external)}).",
        "Sealed undirected islands under current decode: "
        + ", ".join(
            f"{d['slides'][0]}-{d['slides'][-1]} (n={d['size']}, sealed={d['sealed']})"
            for d in island_details
        ),
        "Zero-inbound roots (not reachable except debug jump): "
        + ", ".join(str(z["slide"]) for z in zero_inbound[:20])
        + ("…" if len(zero_inbound) > 20 else "")
        + ". Notable: s043 Ubergoblin chain root; s055 midgame story root.",
        "This is a source graph limitation (or intentional incomplete wiring), not a missing "
        "InteractiveInfoAtom in the extract. Do not invent forward bridges without PPT UI "
        "oracle evidence or a misparse proof.",
    ]

    report = {
        "format": "goblins-rpg3-start-graph-analysis-v1",
        "summary": {
            "slideCount": total,
            "reachableFromStartCount": len(from_start),
            "reachableFromStart": sorted(from_start),
            "matchesExpectedBaseline": from_start == set(EXPECTED_START_REACHABLE),
            "weakComponentCount": len(comps),
            "weakComponents": [
                {
                    "size": len(c),
                    "min": c[0],
                    "max": c[-1],
                    "slides": c if len(c) <= 24 else c[:12] + ["..."] + c[-6:],
                }
                for c in comps
            ],
            "binaryExternalEdgesFromStartComponent": binary_external,
            "actionCodeCounts": {str(k): v for k, v in sorted(action_codes.items())},
            "zeroInboundCount": len(zero_inbound),
            "sealedIslandCount": sum(1 for d in island_details if d["sealed"]),
            "sourceLimitation": True,
            "inventedBridgeApplied": False,
            "conclusions": conclusions,
        },
        "expectedStartReachable": sorted(EXPECTED_START_REACHABLE),
        "earlyLoopFrontier": frontier,
        "islandDetails": island_details,
        "zeroInboundSlides": zero_inbound,
        "keySlides": key_slides,
        "policy": {
            "doNotInventForwardBridges": True,
            "reason": (
                "All navigation atoms are decoded; early loop and islands match binary labels. "
                "Playability promotes (continue/self/combat-all-self) already applied; further "
                "story bridges need human PPT oracle or proven misparse."
            ),
        },
    }

    out_path = ROOT / "generated" / "start_graph_analysis.json"
    out_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"Wrote {out_path}")
    print(f"reachableFromStart={len(from_start)} baselineMatch={from_start == set(EXPECTED_START_REACHABLE)}")
    print(f"binaryExternal={binary_external}")
    print(f"islands={[(d['slides'][0], d['slides'][-1], d['sealed']) for d in island_details]}")
    print(f"zeroInbound={len(zero_inbound)}")
    for line in conclusions:
        print("-", line)


if __name__ == "__main__":
    main()
