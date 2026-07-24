"""Phase 3: subgraph walks from every chapter/island/root seed.

Writes:
  generated/chapter_walks.json
  generated/chapter_entry_map.json  (enriched; also rebuilt from offline suite)
  docs/chapter-entries.json         (runtime debug menu; slim)

Exit criteria: every catalog seed walk is leave-able (no stuck); islands documented.
"""

from __future__ import annotations

import json
from collections import defaultdict, deque
from pathlib import Path

from analyze_start_graph import EXPECTED_SEALED_ISLANDS, EXPECTED_START_REACHABLE
from playability_graph import bfs_reachable, build_inbound, build_outbound, edge_choices, load_screens, screen_texts

ROOT = Path(__file__).resolve().parents[1]

# Primary chapter seeds (title + major roots + island entries + hub orphans).
PRIMARY_SEEDS = (
    1,
    20,
    43,
    52,  # orphaned inside Ubergoblin island (only self-inbound)
    55,
    66,
    70,
    119,
    148,
    166,
)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def outbound_for_walks(screens: list[dict]) -> dict[int, set[int]]:
    """Include non-self hyperlinks even if residual/non-clickable for graph reachability.

    Residual selfs are not edges. Non-clickable residual selfs must not block other
    leave paths; clickable nav hyperlinks and sequential advances do.
    """
    out: dict[int, set[int]] = defaultdict(set)
    for screen in screens:
        slide = int(screen["slide"])
        adv = screen.get("advancement") or {}
        for h in screen.get("hotspots") or []:
            if h.get("action") != "hyperlink" or h.get("targetSlide") is None:
                continue
            target = int(h["targetSlide"])
            if target == slide:
                continue
            # Real navigation edge (clickable or not — e.g. future flags)
            out[slide].add(target)
        if adv.get("autoAdvance") or adv.get("stageClickAdvancesSlide"):
            nxt = adv.get("nextSequentialSlide")
            if nxt is not None:
                out[slide].add(int(nxt))
    return out


def classify_walk(
    *,
    seed: int,
    reachable: set[int],
    screens_by: dict[int, dict],
    outbound: dict[int, set[int]],
) -> dict:
    stuck = []
    terminals = []
    leave_ok = []
    for slide in sorted(reachable):
        screen = screens_by[slide]
        adv = screen.get("advancement") or {}
        leave = list(adv.get("leavePaths") or [])
        outs = sorted(outbound.get(slide, ()))
        if adv.get("stuckReason") or (not leave and not outs):
            stuck.append({"slide": slide, "reason": adv.get("stuckReason") or "no_leave_no_out"})
        else:
            leave_ok.append(slide)
        if adv.get("deathTerminal") or "restart_only" in leave:
            terminals.append(
                {
                    "slide": slide,
                    "terminalKind": adv.get("terminalKind"),
                    "leavePaths": leave,
                }
            )

    # Cycle detection: any edge back into reachable with lower id re-entry sample
    cycles = []
    for slide in reachable:
        for target in outbound.get(slide, ()):
            if target in reachable and target in outbound.get(target, set()) and target != slide:
                edge = tuple(sorted((slide, target)))
                if edge not in [(c["a"], c["b"]) for c in cycles]:
                    cycles.append({"a": edge[0], "b": edge[1]})
            if target in reachable and target < slide and slide - target > 5:
                pass

    reentries = [
        {"from": s, "to": t}
        for s in sorted(reachable)
        for t in outbound.get(s, ())
        if t in reachable and t < s
    ][:15]

    outcome = "ok_leaveable"
    if stuck:
        outcome = "has_stuck"
    elif terminals:
        outcome = "reaches_terminal"
    elif cycles or reentries:
        outcome = "loop_or_hub"
    else:
        outcome = "open_chain"

    return {
        "seed": seed,
        "reachableCount": len(reachable),
        "reachableSlides": sorted(reachable),
        "stuck": stuck,
        "leaveableCount": len(leave_ok),
        "terminals": terminals,
        "reentryEdgesSample": reentries,
        "cyclePairsSample": cycles[:10],
        "outcome": outcome,
        "ok": len(stuck) == 0,
        "entryHint": f"?debug=1&slide={seed}",
        "titleSnippet": (screen_texts(screens_by[seed])[:1] or [f"Slide {seed}"])[0]
        if seed in screens_by
        else f"Slide {seed}",
    }


def island_integrity(
    screens_by: dict[int, dict],
    outbound: dict[int, set[int]],
    inbound: dict[int, set[int]],
) -> list[dict]:
    reports = []
    for island in EXPECTED_SEALED_ISLANDS:
        slides = sorted(island)
        # Suggested entries: zero external inbound within island
        entries = []
        for s in slides:
            external_in = [x for x in inbound.get(s, ()) if x not in island]
            if not external_in:
                # Prefer non-self-only
                entries.append(s)
        # Prefer lowest non-self-only entry
        primary = slides[0]
        for s in entries:
            if s not in outbound.get(s, set()) or any(t != s for t in outbound.get(s, ())):
                primary = s
                break
        walk = classify_walk(
            seed=primary,
            reachable=bfs_reachable(outbound, primary),
            screens_by=screens_by,
            outbound=outbound,
        )
        # Unreachable island members from primary
        missing = sorted(set(slides) - set(walk["reachableSlides"]))
        orphan_entries = []
        for m in missing:
            orphan_entries.append(
                {
                    "slide": m,
                    "entryHint": f"?debug=1&slide={m}",
                    "reason": "not_directed_reachable_from_island_primary",
                    "walkOk": classify_walk(
                        seed=m,
                        reachable=bfs_reachable(outbound, m),
                        screens_by=screens_by,
                        outbound=outbound,
                    )["ok"],
                }
            )
        reports.append(
            {
                "slides": slides,
                "primaryEntry": primary,
                "entryHint": f"?debug=1&slide={primary}",
                "walkFromPrimary": walk,
                "unreachableFromPrimary": missing,
                "orphanEntries": orphan_entries,
                "ok": walk["ok"] and all(o["walkOk"] for o in orphan_entries),
            }
        )
    return reports


def build_chapters(
    walks: list[dict],
    islands: list[dict],
    zero_inbound: list[dict],
) -> list[dict]:
    chapters = [
        {
            "id": "tier-a-title",
            "title": "Title / early story + combat loop",
            "entrySlide": 1,
            "entryHint": "?debug=1&slide=1",
            "subgraphSize": len(EXPECTED_START_REACHABLE),
            "outcome": next((w["outcome"] for w in walks if w["seed"] == 1), None),
            "ok": next((w["ok"] for w in walks if w["seed"] == 1), False),
            "notes": "Closed loop re-enters via s042→s021; death at s030",
            "priority": 0,
        }
    ]
    for isl in islands:
        w = isl["walkFromPrimary"]
        chapters.append(
            {
                "id": f"island-{isl['primaryEntry']}",
                "title": str(w.get("titleSnippet") or f"Island {isl['slides'][0]}-{isl['slides'][-1]}")[:80],
                "entrySlide": isl["primaryEntry"],
                "entryHint": isl["entryHint"],
                "subgraphSize": w["reachableCount"],
                "slides": isl["slides"],
                "outcome": w["outcome"],
                "ok": isl["ok"],
                "unreachableFromPrimary": isl["unreachableFromPrimary"],
                "orphanEntries": isl["orphanEntries"],
                "notes": "Sealed undirected island; use orphanEntries if hub nodes missing from primary walk",
                "priority": 1,
            }
        )
        for orphan in isl.get("orphanEntries") or []:
            chapters.append(
                {
                    "id": f"island-orphan-{orphan['slide']}",
                    "title": f"Island orphan s{orphan['slide']:03d}",
                    "entrySlide": orphan["slide"],
                    "entryHint": orphan["entryHint"],
                    "subgraphSize": None,
                    "outcome": "orphan_entry",
                    "ok": orphan["walkOk"],
                    "notes": orphan["reason"],
                    "priority": 2,
                }
            )

    seen = {c["entrySlide"] for c in chapters}
    for w in walks:
        if w["seed"] in seen:
            # update title chapter already handled
            continue
        if w["seed"] == 1:
            continue
        chapters.append(
            {
                "id": f"root-{w['seed']}",
                "title": str(w.get("titleSnippet") or f"Slide {w['seed']}")[:80],
                "entrySlide": w["seed"],
                "entryHint": w["entryHint"],
                "subgraphSize": w["reachableCount"],
                "outcome": w["outcome"],
                "ok": w["ok"],
                "terminals": [t["slide"] for t in w.get("terminals") or []],
                "notes": "Zero-inbound or primary catalog seed",
                "priority": 3 if w["reachableCount"] >= 10 else 4,
            }
        )
        seen.add(w["seed"])

    # Include remaining large zero-inbound roots not already walked
    for z in zero_inbound:
        if z["slide"] in seen:
            continue
        if z.get("subgraphSize", 0) < 3:
            continue
        chapters.append(
            {
                "id": f"root-{z['slide']}",
                "title": (z.get("texts") or [f"Slide {z['slide']}"])[0][:80]
                if z.get("texts")
                else f"Slide {z['slide']}",
                "entrySlide": z["slide"],
                "entryHint": z.get("entryHint") or f"?debug=1&slide={z['slide']}",
                "subgraphSize": z.get("subgraphSize"),
                "notes": "Zero-inbound root (catalog)",
                "priority": 4,
            }
        )

    chapters.sort(key=lambda c: (c.get("priority", 9), c.get("entrySlide") or 0))
    return chapters


def main() -> None:
    game = load_json(ROOT / "docs" / "game-manifest.json")
    screens = load_screens(game)
    screens_by = {int(s["slide"]): s for s in screens}
    outbound = outbound_for_walks(screens)
    inbound = build_inbound(outbound)

    # Seeds: primary + all zero-inbound + island primaries
    zero_inbound = []
    for slide in range(2, len(screens) + 1):
        if inbound.get(slide):
            continue
        reachable = bfs_reachable(outbound, slide)
        zero_inbound.append(
            {
                "slide": slide,
                "entryHint": f"?debug=1&slide={slide}",
                "texts": screen_texts(screens_by[slide])[:3],
                "leavePaths": (screens_by[slide].get("advancement") or {}).get("leavePaths"),
                "subgraphSize": len(reachable),
            }
        )

    seeds = sorted(set(PRIMARY_SEEDS) | {z["slide"] for z in zero_inbound if z["subgraphSize"] >= 2})
    walks = []
    for seed in seeds:
        if seed not in screens_by:
            continue
        reachable = bfs_reachable(outbound, seed)
        walks.append(
            classify_walk(
                seed=seed,
                reachable=reachable,
                screens_by=screens_by,
                outbound=outbound,
            )
        )

    islands = island_integrity(screens_by, outbound, inbound)
    chapters = build_chapters(walks, islands, zero_inbound)

    all_ok = all(w["ok"] for w in walks) and all(i["ok"] for i in islands)
    failed = [w["seed"] for w in walks if not w["ok"]] + [
        i["primaryEntry"] for i in islands if not i["ok"]
    ]

    walks_report = {
        "format": "goblins-rpg3-chapter-walks-v1",
        "summary": {
            "seedCount": len(walks),
            "allOk": all_ok,
            "failedSeeds": failed,
            "islandCount": len(islands),
            "primarySeedCount": len(PRIMARY_SEEDS),
        },
        "primarySeeds": list(PRIMARY_SEEDS),
        "walks": walks,
        "islands": islands,
    }

    chapter_map = {
        "format": "goblins-rpg3-chapter-entry-map-v1",
        "summary": {
            "zeroInboundCount": len(zero_inbound),
            "sealedIslandCount": len(islands),
            "chapterCount": len(chapters),
            "walksAllOk": all_ok,
        },
        "chapters": chapters,
        "zeroInboundRoots": zero_inbound,
        "sealedIslands": islands,
        "tierB": {
            "mode": "chapter_select",
            "titleDirectedReachable": len(EXPECTED_START_REACHABLE),
            "note": (
                "Title path is closed early loop (29 slides). Full deck is playable "
                "via chapter entry points below — not invented title→midgame bridges."
            ),
        },
    }

    # Slim runtime menu (top chapters only)
    menu = {
        "format": "goblins-rpg3-chapter-entries-runtime-v1",
        "title": "Debug chapters",
        "entries": [
            {
                "id": c["id"],
                "label": f"s{c['entrySlide']:03d} · {c['title']}"[:60],
                "slide": c["entrySlide"],
                "hint": c.get("entryHint"),
                "ok": c.get("ok", True),
            }
            for c in chapters
            if c.get("priority", 9) <= 3 or (c.get("subgraphSize") or 0) >= 15
        ][:24],
    }

    out_dir = ROOT / "generated"
    docs = ROOT / "docs"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "chapter_walks.json").write_text(
        json.dumps(walks_report, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    (out_dir / "chapter_entry_map.json").write_text(
        json.dumps(chapter_map, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    (docs / "chapter-entries.json").write_text(
        json.dumps(menu, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(f"Wrote {out_dir / 'chapter_walks.json'}")
    print(f"Wrote {out_dir / 'chapter_entry_map.json'}")
    print(f"Wrote {docs / 'chapter-entries.json'} ({len(menu['entries'])} menu entries)")
    print(f"allOk={all_ok} seeds={len(walks)} failed={failed}")
    for w in walks:
        if w["seed"] in PRIMARY_SEEDS:
            print(
                f"  seed {w['seed']:3d} n={w['reachableCount']:3d} "
                f"outcome={w['outcome']:16s} ok={w['ok']} terminals={[t['slide'] for t in w['terminals']]}"
            )


if __name__ == "__main__":
    main()
