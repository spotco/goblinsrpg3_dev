"""Generate an extracted gameplay-behavior review report.

This report is intentionally based on extracted action records, not subjective
playthrough notes. It classifies every PowerPoint action record into the browser
runtime behavior currently supported by the generated manifest.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path("docs/game-manifest.json"))
    parser.add_argument("--output", type=Path, default=Path("generated/gameplay_behavior_review.json"))
    args = parser.parse_args()

    manifest = load_json(args.manifest)
    media_bindings = {binding["id"]: binding for binding in manifest.get("mediaBindings", [])}
    actions = []
    for screen in manifest.get("screens", []):
        for hotspot in screen.get("hotspots", []):
            binding = media_bindings.get(hotspot.get("mediaBindingId"))
            actions.append(
                {
                    "id": hotspot["id"],
                    "screen": screen["id"],
                    "slide": screen["slide"],
                    "shapeId": hotspot.get("shapeId"),
                    "action": hotspot.get("action"),
                    "actionCode": hotspot.get("actionCode"),
                    "targetSlide": hotspot.get("targetSlide"),
                    "clickable": bool(hotspot.get("clickable")),
                    "enabledNavigation": bool(hotspot.get("enabled")),
                    "behaviorStatus": hotspot.get("behaviorStatus"),
                    "mediaBindingId": hotspot.get("mediaBindingId"),
                    "mediaStatus": hotspot.get("mediaStatus"),
                    "mediaAudioCueId": binding.get("audioCueId") if binding else None,
                    "bounds": hotspot.get("bounds"),
                    "reviewStatus": "implemented_from_extracted_data"
                    if hotspot.get("behaviorStatus") in {"navigation", "clickable_media", "explicit_noop", "mapped_media_zero_area"}
                    else "requires_manual_or_reference_resolution",
                    "notes": "",
                }
            )

    action_counts = Counter(action["action"] for action in actions)
    behavior_counts = Counter(action["behaviorStatus"] for action in actions)
    report = {
        "format": "goblins-rpg3-gameplay-behavior-review-v1",
        "source": {"gameManifest": args.manifest.as_posix()},
        "summary": {
            "actions": len(actions),
            "navigationActions": action_counts.get("hyperlink", 0),
            "mediaActions": action_counts.get("media", 0),
            "explicitNoopActions": action_counts.get("none", 0),
            "clickableActions": sum(1 for action in actions if action["clickable"]),
            "clickableNavigationActions": sum(1 for action in actions if action["enabledNavigation"]),
            "clickableMediaActions": behavior_counts.get("clickable_media", 0),
            "mappedMediaZeroAreaActions": behavior_counts.get("mapped_media_zero_area", 0),
            "unresolvedMediaActions": behavior_counts.get("unresolved_media", 0),
            "behaviorStatusCounts": dict(sorted(behavior_counts.items())),
        },
        "actions": actions,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"Wrote {args.output} with {len(actions)} gameplay actions")


if __name__ == "__main__":
    main()
