"""Verify generated gameplay action behavior semantics."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


def fail(message: str) -> None:
    raise SystemExit(message)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path("docs/game-manifest.json"))
    parser.add_argument("--report", type=Path, default=Path("generated/gameplay_behavior_review.json"))
    parser.add_argument("--app", type=Path, default=Path("docs/app.js"))
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    report = json.loads(args.report.read_text(encoding="utf-8"))
    app_js = args.app.read_text(encoding="utf-8")
    hotspots = [hotspot for screen in manifest.get("screens", []) for hotspot in screen.get("hotspots", [])]
    action_counts = Counter(hotspot.get("action") for hotspot in hotspots)
    behavior_counts = Counter(hotspot.get("behaviorStatus") for hotspot in hotspots)

    # Inventory has 217 interactive actions: 194 hyperlink + 12 none + 11 media.
    # Port may promote labeled action=none → hyperlink (noop_continue / noop_mirror).
    if len(hotspots) != 217:
        fail(f"expected 217 hotspots, found {len(hotspots)}")
    if action_counts.get("media") != 11:
        fail(f"expected 11 media actions, found {action_counts.get('media')}")
    hyperlink_n = action_counts.get("hyperlink", 0)
    none_n = action_counts.get("none", 0)
    if hyperlink_n + none_n != 206:
        fail(f"expected hyperlink+none == 206, got {hyperlink_n}+{none_n}")
    if hyperlink_n < 194:
        fail(f"hyperlink count regressed below binary 194: {hyperlink_n}")
    if none_n > 12:
        fail(f"none count above binary 12: {none_n}")

    if behavior_counts.get("clickable_media") != 7:
        fail(f"expected 7 clickable_media, found {behavior_counts.get('clickable_media')}")
    # Unresolved media documented as documented_unresolved_media (Phase 2.7)
    unresolved_n = behavior_counts.get("unresolved_media", 0) + behavior_counts.get(
        "documented_unresolved_media", 0
    )
    if unresolved_n != 3:
        fail(f"expected 3 unresolved media hotspots, found {unresolved_n}")
    zero_area_n = behavior_counts.get("mapped_media_zero_area", 0) + behavior_counts.get(
        "documented_zero_area_media", 0
    )
    if zero_area_n != 1:
        fail(f"expected 1 zero-area media hotspot, found {zero_area_n}")
    residual_behavior = behavior_counts.get("documented_residual_self", 0) + behavior_counts.get(
        "documented_residual_self_only_leave", 0
    )
    nav_n = behavior_counts.get("navigation", 0)
    if nav_n + residual_behavior != hyperlink_n:
        fail(
            f"navigation({nav_n})+residual_self({residual_behavior}) != hyperlink({hyperlink_n})"
        )
    if behavior_counts.get("explicit_noop", 0) != none_n:
        fail(f"explicit_noop {behavior_counts.get('explicit_noop')} != none {none_n}")

    clickable = [hotspot for hotspot in hotspots if hotspot.get("clickable")]
    clickable_media = [hotspot for hotspot in clickable if hotspot.get("action") == "media"]
    residual_selfs = [
        h for h in hotspots if h.get("residualStatus") == "accepted_source_self"
    ]
    residual_clickable = [h for h in residual_selfs if h.get("clickable")]
    if residual_clickable:
        fail(
            f"accepted residual selfs must be non-clickable when slide has leave paths: "
            f"{[(h.get('id'), h.get('slide')) for h in residual_clickable[:5]]}"
        )
    # Navigable hyperlinks (non-self or promoted) + clickable media
    clickable_nav = [
        h
        for h in clickable
        if h.get("action") == "hyperlink"
        and h.get("targetSlide") is not None
        and int(h["targetSlide"]) != int(
            # slide id from hotspot id sNNN-...
            str(h.get("id") or "s000").split("-")[0][1:] or 0
        )
    ]
    # Prefer counting via residual: all clickable hyperlinks should not be residual self
    clickable_self = [
        h
        for h in clickable
        if h.get("action") == "hyperlink"
        and h.get("targetSlide") is not None
        and h.get("residualStatus") == "accepted_source_self"
    ]
    if clickable_self:
        fail("clickable residual selfs present")
    if len(clickable_media) != 7:
        fail(f"expected 7 clickable media actions, found {len(clickable_media)}")
    if any(hotspot.get("clickable") for hotspot in hotspots if hotspot.get("action") == "none"):
        fail("explicit no-op actions must not be clickable")
    if any(
        hotspot.get("clickable")
        for hotspot in hotspots
        if hotspot.get("behaviorStatus")
        in ("unresolved_media", "documented_unresolved_media", "documented_zero_area_media")
    ):
        fail("unresolved/zero-area media actions must not be clickable")
    if len(residual_selfs) < 5:
        fail(f"expected >=5 accepted residual selfs (combat+image), found {len(residual_selfs)}")

    # Promoted noops must keep provenance
    promoted_noops = [
        h
        for h in hotspots
        if h.get("resolveMethod") in ("noop_continue_to_next", "noop_mirror_sibling_hyperlink")
    ]
    if len(promoted_noops) < 3:
        fail(f"expected noop promotes (continue/mirror), found {len(promoted_noops)}")
    for h in promoted_noops:
        if h.get("action") != "hyperlink" or not h.get("targetSlide"):
            fail(f"promoted noop not navigable: {h.get('id')}")
        if h.get("binaryActionCode") not in (0, None) and h.get("actionCode") != 0:
            # actionCode stays 0 from binary; binaryActionCode may be set
            pass
        if int(h.get("actionCode", -1)) != 0 and h.get("binaryActionCode") != 0:
            fail(f"promoted noop should retain binary actionCode 0: {h.get('id')}")

    summary = report.get("summary", {})
    if summary.get("actions") != 217:
        fail("gameplay behavior review summary actions != 217")
    if summary.get("clickableActions") != len(clickable):
        fail("gameplay behavior review clickableActions out of date — re-run generate_gameplay_behavior_review.py")

    for snippet in (
        "function handleHotspotAction",
        "function mediaBindingForHotspot",
        'hotspot.action === "media"',
        "playAudioSource(binding.audioSource",
        "hotspot.clickable",
    ):
        if snippet not in app_js:
            fail(f"runtime gameplay behavior snippet is missing: {snippet}")

    print("gameplay behavior verification passed")
    print(
        f"  hyperlink={hyperlink_n} none={none_n} media=11 "
        f"clickable={len(clickable)} residualSelfs={len(residual_selfs)} "
        f"noopPromotes={len(promoted_noops)}"
    )


if __name__ == "__main__":
    main()
