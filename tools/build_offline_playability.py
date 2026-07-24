"""Build offline playability reports (path walk, chapter map, promote audit).

Writes:
  generated/path_walk_report.json
  generated/chapter_entry_map.json
  generated/promote_audit.json

Phase 1 of PLAN.md (offline “is it a game?” proof).
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

from analyze_start_graph import EXPECTED_SEALED_ISLANDS, EXPECTED_START_REACHABLE
from playability_graph import (
    bfs_reachable,
    build_inbound,
    build_outbound,
    edge_choices,
    load_screens,
    screen_texts,
)

ROOT = Path(__file__).resolve().parents[1]

# Major seeds for chapter walks (zero-inbound / island roots + hubs).
DEFAULT_CHAPTER_SEEDS = (
    1,  # title / Tier A
    20,  # sealed pair entry-ish
    43,  # Ubergoblin island
    55,  # midgame story
    66,
    70,
    119,
    148,
    166,
)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def build_path_walk(
    screens: list[dict],
    outbound: dict[int, set[int]],
    seeds: list[int],
) -> dict:
    by_slide = {int(s["slide"]): s for s in screens}
    total = len(screens)
    walks = []

    for seed in seeds:
        if seed not in by_slide:
            continue
        reachable = bfs_reachable(outbound, seed)
        nodes = []
        endings = []
        for slide in sorted(reachable):
            screen = by_slide[slide]
            adv = screen.get("advancement") or {}
            choices = edge_choices(screen, outbound)
            node = {
                "slide": slide,
                "leavePaths": adv.get("leavePaths"),
                "modes": adv.get("modes"),
                "stuckReason": adv.get("stuckReason"),
                "deathTerminal": bool(adv.get("deathTerminal")),
                "texts": screen_texts(screen)[:4],
                "choices": choices,
                "outbound": sorted(outbound.get(slide, ())),
            }
            nodes.append(node)
            if adv.get("deathTerminal") or "restart_only" in (adv.get("leavePaths") or []):
                endings.append({"slide": slide, "kind": "death_or_restart"})
            elif adv.get("stuckReason"):
                endings.append({"slide": slide, "kind": "stuck", "reason": adv.get("stuckReason")})
            elif not outbound.get(slide) and not adv.get("leavePaths"):
                endings.append({"slide": slide, "kind": "no_outbound"})

        # Detect simple loop edges (target also reachable and returns)
        loop_edges = []
        for slide in reachable:
            for target in outbound.get(slide, ()):
                if target in reachable and slide in outbound.get(target, ()):
                    loop_edges.append({"from": slide, "to": target})
                # one-way re-entry into earlier combat hub
                if target < slide and target in reachable:
                    pass
        # Notable re-entry
        reentries = [
            {"from": s, "to": t}
            for s in reachable
            for t in outbound.get(s, ())
            if t in reachable and t in EXPECTED_START_REACHABLE and s in EXPECTED_START_REACHABLE
            and s > 30
            and t <= 25
        ]

        walks.append(
            {
                "seed": seed,
                "reachableCount": len(reachable),
                "reachableSlides": sorted(reachable),
                "endings": endings,
                "reentryEdgesSample": reentries[:20],
                "nodes": nodes,
            }
        )

    # Tier A derived summary from seed 1
    seed1 = next((w for w in walks if w["seed"] == 1), None)
    tier_a = {
        "seed": 1,
        "reachableCount": seed1["reachableCount"] if seed1 else 0,
        "matchesStartBaseline": (
            set(seed1["reachableSlides"]) == set(EXPECTED_START_REACHABLE) if seed1 else False
        ),
        "includesStoryBeats": bool(
            seed1 and {1, 2, 3, 8, 9}.issubset(set(seed1["reachableSlides"]))
        ),
        "includesVillage": bool(seed1 and 9 in seed1["reachableSlides"] and 10 in seed1["reachableSlides"]),
        "includesCombat": bool(seed1 and 15 in seed1["reachableSlides"]),
        "deathReachable": bool(seed1 and 30 in seed1["reachableSlides"]),
        "loopEdge042to021": bool(seed1 and 21 in outbound.get(42, set())),
        "startBaselineSize": len(EXPECTED_START_REACHABLE),
    }

    return {
        "format": "goblins-rpg3-path-walk-report-v1",
        "slideCount": total,
        "tierA": tier_a,
        "seeds": seeds,
        "walks": walks,
    }


def build_chapter_map(
    screens: list[dict],
    outbound: dict[int, set[int]],
    inbound: dict[int, set[int]],
) -> dict:
    by_slide = {int(s["slide"]): s for s in screens}
    total = len(screens)

    zero_inbound = []
    for slide in range(1, total + 1):
        if slide == 1:
            continue
        if inbound.get(slide):
            continue
        screen = by_slide[slide]
        adv = screen.get("advancement") or {}
        reachable = bfs_reachable(outbound, slide)
        zero_inbound.append(
            {
                "slide": slide,
                "entryHint": f"?debug=1&slide={slide}",
                "texts": screen_texts(screen)[:4],
                "leavePaths": adv.get("leavePaths"),
                "outbound": sorted(outbound.get(slide, ())),
                "subgraphSize": len(reachable),
                "subgraphSample": sorted(reachable)[:24],
                "kind": "zero_inbound_root",
            }
        )

    islands = []
    for island in EXPECTED_SEALED_ISLANDS:
        slides = sorted(island)
        entry = slides[0]
        # Prefer zero-inbound inside island as entry
        for s in slides:
            if not inbound.get(s) or inbound.get(s, set()).issubset(island):
                if not inbound.get(s):
                    entry = s
                    break
        screen = by_slide[entry]
        reachable = bfs_reachable(outbound, entry)
        islands.append(
            {
                "slides": slides,
                "size": len(slides),
                "suggestedEntry": entry,
                "entryHint": f"?debug=1&slide={entry}",
                "texts": screen_texts(screen)[:4],
                "subgraphSizeFromEntry": len(reachable),
                "kind": "sealed_island",
            }
        )

    # Major chapters = zero-inbound with subgraph size >= 3, plus islands, plus title
    chapters = [
        {
            "id": "tier-a-title",
            "title": "Title / early story + combat loop",
            "entrySlide": 1,
            "entryHint": "?debug=1&slide=1 (or default start)",
            "subgraphSize": len(EXPECTED_START_REACHABLE),
            "notes": "Closed loop re-enters via s042→s021; death at s030",
        }
    ]
    for island in islands:
        chapters.append(
            {
                "id": f"island-{island['suggestedEntry']}",
                "title": (island["texts"][0] if island["texts"] else f"Island {island['slides'][0]}-{island['slides'][-1]}"),
                "entrySlide": island["suggestedEntry"],
                "entryHint": island["entryHint"],
                "subgraphSize": island["subgraphSizeFromEntry"],
                "slides": island["slides"],
                "notes": "Sealed undirected island under current graph",
            }
        )
    for root in zero_inbound:
        if root["slide"] in {i["suggestedEntry"] for i in islands}:
            continue
        if root["subgraphSize"] < 2 and root["slide"] not in DEFAULT_CHAPTER_SEEDS:
            continue
        snippet = root["texts"][0] if root["texts"] else f"Slide {root['slide']}"
        chapters.append(
            {
                "id": f"root-{root['slide']}",
                "title": str(snippet)[:80],
                "entrySlide": root["slide"],
                "entryHint": root["entryHint"],
                "subgraphSize": root["subgraphSize"],
                "notes": "Zero-inbound root",
            }
        )

    return {
        "format": "goblins-rpg3-chapter-entry-map-v1",
        "summary": {
            "zeroInboundCount": len(zero_inbound),
            "sealedIslandCount": len(islands),
            "chapterCount": len(chapters),
        },
        "chapters": chapters,
        "zeroInboundRoots": zero_inbound,
        "sealedIslands": islands,
    }


def build_promote_audit(screens: list[dict]) -> dict:
    promotes = []
    residual_selfs = []
    method_counts: dict[str, int] = defaultdict(int)

    for screen in screens:
        slide = int(screen["slide"])
        for hotspot in screen.get("hotspots") or []:
            method = hotspot.get("resolveMethod")
            if not method:
                continue
            method_counts[str(method)] += 1
            entry = {
                "slide": slide,
                "hotspotId": hotspot.get("id"),
                "shapeId": hotspot.get("shapeId"),
                "shapeText": hotspot.get("shapeText"),
                "resolveMethod": method,
                "originalTargetSlide": hotspot.get("originalTargetSlide"),
                "targetSlide": hotspot.get("targetSlide"),
                "binarySelfLink": bool(hotspot.get("binarySelfLink")),
                "resolveRationale": hotspot.get("resolveRationale"),
            }
            if method in (
                "self_continue_to_next",
                "sole_image_self_to_next",
                "combat_all_self_to_next_outcome",
                "noop_continue_to_next",
                "noop_mirror_sibling_hyperlink",
            ) or (
                hotspot.get("binarySelfLink")
                and hotspot.get("targetSlide") is not None
                and int(hotspot["targetSlide"]) != slide
            ):
                promotes.append(entry)
            if (
                hotspot.get("action") == "hyperlink"
                and hotspot.get("targetSlide") is not None
                and int(hotspot["targetSlide"]) == slide
            ):
                residual_selfs.append(entry)

    return {
        "format": "goblins-rpg3-promote-audit-v1",
        "summary": {
            "promoteCount": len(promotes),
            "residualSelfCount": len(residual_selfs),
            "resolveMethodCounts": dict(sorted(method_counts.items())),
        },
        "promotes": promotes,
        "residualSelfHyperlinks": residual_selfs,
    }


def evaluate_clickable_contract(screens: list[dict]) -> dict:
    """Return violations and documented residuals for clickable hotspots."""
    violations = []
    ok = []
    residuals = []

    for screen in screens:
        slide = int(screen["slide"])
        for hotspot in screen.get("hotspots") or []:
            action = hotspot.get("action")
            status = hotspot.get("behaviorStatus")
            target = hotspot.get("targetSlide")
            method = hotspot.get("resolveMethod")
            hid = hotspot.get("id")

            # Documented residual selfs must be non-clickable when accepted.
            if (
                hotspot.get("residualStatus") == "accepted_source_self"
                or status == "documented_residual_self"
            ):
                entry = {
                    "slide": slide,
                    "hotspotId": hid,
                    "reason": "documented_residual_self",
                    "resolveMethod": method,
                    "shapeText": hotspot.get("shapeText"),
                    "residualKind": hotspot.get("residualKind"),
                    "clickable": bool(hotspot.get("clickable")),
                }
                residuals.append(entry)
                if hotspot.get("clickable"):
                    violations.append(
                        {
                            "slide": slide,
                            "hotspotId": hid,
                            "reason": "residual_self_still_clickable",
                            "resolveMethod": method,
                        }
                    )
                continue

            if not hotspot.get("clickable"):
                continue

            if action == "hyperlink" and target is not None:
                t = int(target)
                if t == slide:
                    violations.append(
                        {
                            "slide": slide,
                            "hotspotId": hid,
                            "reason": "clickable_self_hyperlink",
                            "resolveMethod": method,
                        }
                    )
                else:
                    ok.append({"slide": slide, "hotspotId": hid, "kind": "navigation", "target": t})
                continue

            if action == "media":
                if status == "clickable_media":
                    ok.append({"slide": slide, "hotspotId": hid, "kind": "media"})
                elif status in ("unresolved_media", "missing_media_binding", "mapped_media_zero_area"):
                    violations.append(
                        {
                            "slide": slide,
                            "hotspotId": hid,
                            "reason": f"clickable_bad_media:{status}",
                        }
                    )
                else:
                    violations.append(
                        {
                            "slide": slide,
                            "hotspotId": hid,
                            "reason": f"clickable_media_unexpected:{status}",
                        }
                    )
                continue

            # Other clickable actions
            violations.append(
                {
                    "slide": slide,
                    "hotspotId": hid,
                    "reason": f"clickable_unknown_action:{action}:{status}",
                }
            )

    # Residual explicit_noop with empty shape text (decorative hitboxes).
    residual_noops = []
    for screen in screens:
        slide = int(screen["slide"])
        for hotspot in screen.get("hotspots") or []:
            if hotspot.get("behaviorStatus") != "explicit_noop":
                continue
            residual_noops.append(
                {
                    "slide": slide,
                    "hotspotId": hotspot.get("id"),
                    "shapeId": hotspot.get("shapeId"),
                    "shapeText": hotspot.get("shapeText"),
                    "note": "binary action=none without continue/combat label (decorative)",
                }
            )

    # Labeled continue still only stage-click (should be empty after Phase 2.1)
    orphan_continues = []
    continue_re = re.compile(r"click\s*here|continue", re.I)
    for screen in screens:
        slide = int(screen["slide"])
        adv = screen.get("advancement") or {}
        texts = screen_texts(screen)
        if not any(continue_re.search(t or "") for t in texts):
            continue
        has_nav = any(
            h.get("action") == "hyperlink"
            and h.get("targetSlide") is not None
            and int(h["targetSlide"]) != slide
            for h in screen.get("hotspots") or []
        )
        if not has_nav and adv.get("stageClickResolveMethod") == "continue_text_stage_click":
            orphan_continues.append({"slide": slide, "note": "continue text only via stage-click fallback"})

    return {
        "format": "goblins-rpg3-clickable-contract-v1",
        "summary": {
            "okCount": len(ok),
            "violationCount": len(violations),
            "residualSelfCount": len(residuals),
            "residualExplicitNoopCount": len(residual_noops),
            "orphanContinueStageClickCount": len(orphan_continues),
            "passed": len(violations) == 0,
        },
        "violations": violations,
        "residualSelfHyperlinks": residuals,
        "residualExplicitNoops": residual_noops,
        "orphanContinueStageClicks": orphan_continues,
        "okSample": ok[:20],
    }


def build_all(
    *,
    game_manifest: Path | None = None,
    out_dir: Path | None = None,
    seeds: list[int] | None = None,
) -> dict:
    game_manifest = game_manifest or (ROOT / "docs" / "game-manifest.json")
    out_dir = out_dir or (ROOT / "generated")
    seed_list = list(seeds) if seeds is not None else list(DEFAULT_CHAPTER_SEEDS)

    game = load_json(game_manifest)
    screens = load_screens(game)
    outbound = build_outbound(screens)
    inbound = build_inbound(outbound)

    path_report = build_path_walk(screens, outbound, seed_list)
    chapter_map = build_chapter_map(screens, outbound, inbound)
    promote_audit = build_promote_audit(screens)
    clickable = evaluate_clickable_contract(screens)

    out_dir.mkdir(parents=True, exist_ok=True)
    payloads = {
        "path_walk_report.json": path_report,
        "chapter_entry_map.json": chapter_map,
        "promote_audit.json": promote_audit,
        "clickable_contract.json": clickable,
    }
    for name, payload in payloads.items():
        out = out_dir / name
        out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8", newline="\n")
        print(f"Wrote {out}")

    # Phase 2.3 combat matrix + Phase 2.7–2.9 media/death + Phase 3 chapter walks
    try:
        from build_combat_option_matrix import main as build_combat_matrix

        build_combat_matrix()
    except Exception as exc:  # pragma: no cover
        print(f"combat matrix skipped: {exc}")
    try:
        from build_media_death_report import main as build_media_death

        build_media_death()
    except Exception as exc:  # pragma: no cover
        print(f"media/death report skipped: {exc}")
    try:
        from build_chapter_walks import main as build_chapter_walks

        build_chapter_walks()
    except Exception as exc:  # pragma: no cover
        print(f"chapter walks skipped: {exc}")
    try:
        from build_fidelity_reports import main as build_fidelity

        build_fidelity()
    except Exception as exc:  # pragma: no cover
        print(f"fidelity reports skipped: {exc}")

    tier = path_report["tierA"]
    print(
        f"TierA reachable={tier['reachableCount']} baselineMatch={tier['matchesStartBaseline']} "
        f"death={tier['deathReachable']} loop042to021={tier['loopEdge042to021']}"
    )
    print(
        f"chapters={chapter_map['summary']['chapterCount']} "
        f"promotes={promote_audit['summary']['promoteCount']} "
        f"clickable_ok={clickable['summary']['passed']} "
        f"violations={clickable['summary']['violationCount']}"
    )
    return {
        "path_walk_report": path_report,
        "chapter_entry_map": chapter_map,
        "promote_audit": promote_audit,
        "clickable_contract": clickable,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-manifest", type=Path, default=ROOT / "docs" / "game-manifest.json")
    parser.add_argument("--out-dir", type=Path, default=ROOT / "generated")
    parser.add_argument(
        "--seeds",
        type=str,
        default=",".join(str(s) for s in DEFAULT_CHAPTER_SEEDS),
        help="Comma-separated seed slides for path walks",
    )
    args = parser.parse_args()
    seeds = [int(x.strip()) for x in args.seeds.split(",") if x.strip()]
    build_all(game_manifest=args.game_manifest, out_dir=args.out_dir, seeds=seeds)


if __name__ == "__main__":
    main()
