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

    if action_counts != {"hyperlink": 194, "none": 12, "media": 11}:
        fail(f"unexpected action counts: {action_counts}")
    expected_behaviors = {
        "navigation": 194,
        "explicit_noop": 12,
        "clickable_media": 7,
        "mapped_media_zero_area": 1,
        "unresolved_media": 3,
    }
    if behavior_counts != expected_behaviors:
        fail(f"unexpected behavior counts: {behavior_counts}")

    clickable = [hotspot for hotspot in hotspots if hotspot.get("clickable")]
    clickable_media = [hotspot for hotspot in clickable if hotspot.get("action") == "media"]
    if len(clickable) != 201:
        fail(f"expected 201 clickable runtime actions, found {len(clickable)}")
    if len(clickable_media) != 7:
        fail(f"expected 7 clickable media actions, found {len(clickable_media)}")
    if any(hotspot.get("clickable") for hotspot in hotspots if hotspot.get("action") == "none"):
        fail("explicit no-op actions must not be clickable")
    if any(hotspot.get("clickable") for hotspot in hotspots if hotspot.get("behaviorStatus") == "unresolved_media"):
        fail("unresolved media actions must not be clickable")

    summary = report.get("summary", {})
    if summary.get("actions") != 217 or summary.get("clickableActions") != 201:
        fail("gameplay behavior review summary is inconsistent")

    for snippet in (
        "function handleHotspotAction",
        "function mediaBindingForHotspot",
        "hotspot.action === \"media\"",
        "playAudioSource(binding.audioSource",
        "hotspot.clickable",
    ):
        if snippet not in app_js:
            fail(f"runtime gameplay behavior snippet is missing: {snippet}")

    print("gameplay behavior verification passed")


if __name__ == "__main__":
    main()
