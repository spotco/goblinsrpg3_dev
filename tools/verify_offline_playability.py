"""Verify offline playability suite (Phase 1 PLAN): path walk, Tier A, catalogs, clickable."""

from __future__ import annotations

import json
from pathlib import Path

from analyze_start_graph import EXPECTED_START_REACHABLE
from build_offline_playability import build_all


def fail(message: str) -> None:
    raise SystemExit(message)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    generated = root / "generated"

    # Rebuild all offline reports so verify is self-contained.
    build_all()

    path_report = load_json(generated / "path_walk_report.json")
    chapters = load_json(generated / "chapter_entry_map.json")
    promotes = load_json(generated / "promote_audit.json")
    clickable = load_json(generated / "clickable_contract.json")
    game = load_json(root / "docs" / "game-manifest.json")

    if path_report.get("format") != "goblins-rpg3-path-walk-report-v1":
        fail("path_walk_report format unexpected")

    tier = path_report.get("tierA") or {}
    if not tier.get("matchesStartBaseline"):
        fail(
            f"Tier A reachability does not match EXPECTED_START_REACHABLE "
            f"(count={tier.get('reachableCount')}, "
            f"expected={len(EXPECTED_START_REACHABLE)})"
        )
    if tier.get("reachableCount") != len(EXPECTED_START_REACHABLE):
        fail(f"Tier A reachableCount {tier.get('reachableCount')} != {len(EXPECTED_START_REACHABLE)}")
    if not tier.get("includesStoryBeats"):
        fail("Tier A missing story beats (1–3, 8–9)")
    if not tier.get("includesVillage"):
        fail("Tier A missing village slides 9–10")
    if not tier.get("includesCombat"):
        fail("Tier A missing combat slide 15")
    if not tier.get("deathReachable"):
        fail("Tier A: death slide 30 not reachable from title")
    if not tier.get("loopEdge042to022"):
        fail("Tier A: expected edge s042 → s022 (1-goblin menu; slideId-resolved)")

    # Seed-1 walk exists and has no stuck endings
    walk1 = next((w for w in path_report.get("walks") or [] if w.get("seed") == 1), None)
    if not walk1:
        fail("path walk missing seed 1")
    stuck_endings = [e for e in walk1.get("endings") or [] if e.get("kind") == "stuck"]
    if stuck_endings:
        fail(f"Tier A walk has stuck endings: {stuck_endings}")

    # Chapter map
    if chapters.get("format") != "goblins-rpg3-chapter-entry-map-v1":
        fail("chapter_entry_map format unexpected")
    if chapters.get("summary", {}).get("chapterCount", 0) < 3:
        fail("chapter map should list title + islands/roots")
    entries = {c.get("entrySlide") for c in chapters.get("chapters") or []}
    for required in (1, 43, 55):
        if required not in entries:
            # 43/55 may be under islands or roots
            all_entries = set(entries)
            for island in chapters.get("sealedIslands") or []:
                all_entries.add(island.get("suggestedEntry"))
            for root in chapters.get("zeroInboundRoots") or []:
                all_entries.add(root.get("slide"))
            if required not in all_entries and required != 1:
                fail(f"chapter map missing entry for slide {required}")
    if 1 not in entries:
        fail("chapter map missing tier-a title entry")

    # Promote audit: known promotes present
    if promotes.get("format") != "goblins-rpg3-promote-audit-v1":
        fail("promote_audit format unexpected")
    methods = {p.get("resolveMethod") for p in promotes.get("promotes") or []}
    if "noop_continue_to_next" not in methods:
        fail("promote audit missing method noop_continue_to_next")
    # noop_mirror_sibling_hyperlink is only for *different-shape* leftover
    # InteractiveInfo. Same-shape click+none pairs stay explicit_noop (the
    # real DocSum hyperlink is the only clickable button).
    # Self-link promotes (self_continue / combat_all_self / sole_image_self) are no longer
    # required: DocSummary slideId resolve yields the real targets (e.g. s046→47, s002→3).

    # Clickable contract
    if not clickable.get("summary", {}).get("passed"):
        viol = clickable.get("violations") or []
        fail(f"clickable contract failed: {viol[:5]}")

    # Phase 2.1: damage interstitials use labeled continue hotspot, not stage-only
    for slide in (155, 158, 163):
        screen = game["screens"][slide - 1]
        cont = [
            h
            for h in screen.get("hotspots") or []
            if h.get("resolveMethod") == "noop_continue_to_next"
            and h.get("targetSlide") == slide + 1
        ]
        if not cont:
            fail(f"slide {slide} expected noop_continue_to_next → {slide + 1}")
        if screen["advancement"].get("stuckReason"):
            fail(f"slide {slide} should not be stuck")

    # Phase 2.2: combat options that used to be action=none leftovers now
    # navigate via the same-shape DocSum hyperlink (one clickable button).
    for slide, text, target in (
        (150, "-limit", 167),
        (156, "-attack", 157),
        (159, "-attack", 160),
        (164, "-attack", 165),
    ):
        screen = game["screens"][slide - 1]
        hits = [
            h
            for h in screen.get("hotspots") or []
            if h.get("action") == "hyperlink"
            and h.get("clickable")
            and str(h.get("shapeText") or "").lower().replace(" ", "") == text.lower()
            and h.get("targetSlide") == target
        ]
        if not hits:
            fail(f"slide {slide} expected clickable {text!r} → {target}")
        clickable_same_shape = [
            h for h in hits if h.get("shapeId") is not None
        ]
        shape_ids = {h.get("shapeId") for h in clickable_same_shape}
        for sid in shape_ids:
            n = sum(1 for h in clickable_same_shape if h.get("shapeId") == sid)
            if n != 1:
                fail(f"slide {slide} {text!r} shape {sid} has {n} clickable hotspots")

    # Phase 2.4–2.5: former "residual selfs" were stale ExHyperlink labels.
    # After DocSummary slideId resolve they navigate (no accepted_source_self).
    former_self_fixtures = [
        (15, "-flee", 17),
        (27, "-flee", 28),
        (39, "-attack", 40),
    ]
    for slide, text, target in former_self_fixtures:
        screen = game["screens"][slide - 1]
        hits = [
            h
            for h in screen.get("hotspots") or []
            if h.get("action") == "hyperlink"
            and str(h.get("shapeText") or "").lower().replace(" ", "")
            == text.lower().replace(" ", "")
            and h.get("targetSlide") == target
            and h.get("clickable")
        ]
        if not hits:
            fail(f"slide {slide} {text!r} must navigate →{target} after slideId resolve")
        if not (screen.get("advancement") or {}).get("leavePaths"):
            fail(f"slide {slide} lost leave paths")

    # Hub image slides also leave via slideId-native hyperlinks (not residual self).
    for slide in (50, 52):
        screen = game["screens"][slide - 1]
        nav = [
            h
            for h in screen.get("hotspots") or []
            if h.get("clickable") and h.get("targetSlide") and h.get("targetSlide") != slide
        ]
        if not nav:
            fail(f"hub slide {slide} expected outbound hyperlinks after slideId resolve")

    # Game manifest still 201 screens
    if len(game.get("screens") or []) != 201:
        fail("expected 201 screens")

    # Combat matrix if present
    matrix_path = generated / "combat_option_matrix.json"
    if matrix_path.exists():
        matrix = load_json(matrix_path)
        if matrix.get("format") not in (
            "goblins-rpg3-combat-option-matrix-v1",
            "goblins-rpg3-combat-option-matrix-v2",
        ):
            fail("combat_option_matrix format unexpected")
        if matrix.get("summary", {}).get("noopOptions", 1) != 0:
            fail(
                f"combat matrix still has noop options: "
                f"{matrix.get('summary', {}).get('noopOptions')}"
            )
        if matrix.get("summary", {}).get("mismatchCount", 0):
            fail(f"combat matrix web/docsum/pptx mismatches: {matrix.get('mismatches')}")

    # Phase 2.7–2.9 media + death residuals
    for slide in (54, 96, 193):
        screen = game["screens"][slide - 1]
        media = [
            h
            for h in screen.get("hotspots") or []
            if h.get("residualStatus") == "accepted_unresolved_media"
            or h.get("behaviorStatus") == "documented_unresolved_media"
        ]
        if not media:
            fail(f"slide {slide} expected documented unresolved media residual")
        if any(h.get("clickable") for h in media):
            fail(f"slide {slide} unresolved media must not be clickable")

    s104 = game["screens"][103]
    zero = [
        h
        for h in s104.get("hotspots") or []
        if h.get("residualStatus") == "accepted_zero_area_media"
        or h.get("behaviorStatus") == "documented_zero_area_media"
    ]
    if not zero:
        fail("slide 104 expected documented zero-area media residual")
    if any(h.get("clickable") for h in zero):
        fail("slide 104 zero-area media must not be clickable")

    for slide, kind in ((30, "death"), (197, "death"), (200, "end_card")):
        adv = game["screens"][slide - 1].get("advancement") or {}
        if not adv.get("deathTerminal"):
            fail(f"slide {slide} should be deathTerminal")
        if adv.get("terminalKind") != kind:
            fail(f"slide {slide} terminalKind {adv.get('terminalKind')} != {kind}")
        if not adv.get("terminalNotes"):
            fail(f"slide {slide} missing terminalNotes")
        if kind == "death" and "restart_only" not in (adv.get("leavePaths") or []):
            fail(f"slide {slide} death should list restart_only")
        if kind == "end_card" and "non_self_hyperlink" not in (adv.get("leavePaths") or []):
            fail(f"slide {slide} end card should keep hyperlink leave")

    media_report = generated / "media_death_residuals.json"
    if media_report.exists():
        md = load_json(media_report)
        if md.get("format") != "goblins-rpg3-media-death-residuals-v1":
            fail("media_death_residuals format unexpected")
        if md.get("summary", {}).get("mediaResidualHotspotCount", 0) < 4:
            fail("media residual report under-populated")

    # Phase 3: chapter walks + island integrity + runtime menu
    walks_path = generated / "chapter_walks.json"
    if not walks_path.exists():
        fail("chapter_walks.json missing — run build_chapter_walks / offline playability")
    walks = load_json(walks_path)
    if walks.get("format") != "goblins-rpg3-chapter-walks-v1":
        fail("chapter_walks format unexpected")
    if not walks.get("summary", {}).get("allOk"):
        fail(f"chapter walks failed seeds: {walks.get('summary', {}).get('failedSeeds')}")
    for seed in (1, 20, 43, 55, 119):
        w = next((x for x in walks.get("walks") or [] if x.get("seed") == seed), None)
        if not w or not w.get("ok"):
            fail(f"primary chapter seed {seed} walk missing or not ok")
    # Island 43 primary leaveable; orphan 52 if present ok
    islands = walks.get("islands") or []
    # After slideId resolve, undirected graph is one component (no sealed islands).
    if len(islands) != 0:
        fail(f"expected 0 sealed island reports after slideId resolve, got {len(islands)}")
    for isl in islands:
        if not isl.get("ok"):
            fail(f"island {isl.get('slides')} integrity failed")
    if not chapters.get("summary", {}).get("walksAllOk", True) and chapters.get("summary", {}).get(
        "walksAllOk"
    ) is False:
        fail("chapter_entry_map walksAllOk false")
    menu_path = root / "docs" / "chapter-entries.json"
    if not menu_path.exists():
        fail("docs/chapter-entries.json missing for debug chapter menu")
    menu = load_json(menu_path)
    if not (menu.get("entries") or []):
        fail("chapter-entries menu empty")
    menu_slides = {e.get("slide") for e in menu.get("entries") or []}
    for required in (1, 43, 55):
        if required not in menu_slides:
            fail(f"debug chapter menu missing slide {required}")

    print("offline playability verification passed")
    print(
        f"  TierA={tier['reachableCount']} slides "
        f"death={tier['deathReachable']} loop042→022={tier['loopEdge042to022']}"
    )
    print(
        f"  chapters={chapters['summary']['chapterCount']} "
        f"promotes={promotes['summary']['promoteCount']} "
        f"residualSelfs={promotes['summary']['residualSelfCount']} "
        f"clickableViolations=0"
    )
    print(
        f"  chapterWalks seeds={walks['summary']['seedCount']} "
        f"allOk={walks['summary']['allOk']} menuEntries={len(menu.get('entries') or [])}"
    )


if __name__ == "__main__":
    main()
