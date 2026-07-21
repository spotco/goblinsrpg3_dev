"""Verify representative animation-player feature coverage.

This is a browserless contract test. It ties together:

* decoded PP10 timing-tree evidence in ``docs/animation-manifest.json``;
* audio/navigation data in ``docs/game-manifest.json``; and
* the JavaScript runtime hooks in ``docs/app.js``.

It does not prove pixel-perfect PowerPoint playback. It prevents regressions
where a decoded timing feature remains present in the manifest but the browser
runtime no longer has the corresponding first-pass support.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def fail(message: str) -> None:
    raise SystemExit(message)


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def require_snippets(app_js: str, feature: str, snippets: tuple[str, ...]) -> None:
    missing = [snippet for snippet in snippets if snippet not in app_js]
    if missing:
        fail(f"{feature} runtime support is missing snippets: {missing}")


def collect_variant_strings(animation_manifest: dict[str, Any]) -> set[str]:
    strings: set[str] = set()
    stack = []
    for slide in animation_manifest.get("slides", []):
        stack.extend(slide.get("rootTimeNodes", []))
    while stack:
        node = stack.pop()
        for variant in node.get("variants", []):
            parsed = variant.get("parsed") or {}
            if isinstance(parsed.get("stringValue"), str):
                strings.add(parsed["stringValue"])
        for behavior in node.get("behaviors", []):
            for variant in behavior.get("variants", []):
                parsed = variant.get("parsed") or {}
                if isinstance(parsed.get("stringValue"), str):
                    strings.add(parsed["stringValue"])
        stack.extend(node.get("children", []))
    return strings


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--animation-manifest", type=Path, default=Path("docs/animation-manifest.json"))
    parser.add_argument("--game-manifest", type=Path, default=Path("docs/game-manifest.json"))
    parser.add_argument("--app", type=Path, default=Path("docs/app.js"))
    parser.add_argument("--report", type=Path, default=Path("generated/animation_player_contract.json"))
    args = parser.parse_args()

    animation_manifest = load_json(args.animation_manifest)
    game_manifest = load_json(args.game_manifest)
    app_js = args.app.read_text(encoding="utf-8")
    styles_css = args.app.with_name("styles.css").read_text(encoding="utf-8")
    summary = animation_manifest.get("summary", {})
    condition_events = {int(key): int(value) for key, value in summary.get("conditionEvents", {}).items()}
    modifier_types = {int(key): int(value) for key, value in summary.get("modifierTypes", {}).items()}
    behavior_kinds = summary.get("behaviorKinds", {})
    variant_strings = collect_variant_strings(animation_manifest)

    mapped_media_bindings = [
        binding for binding in game_manifest.get("mediaBindings", []) if binding.get("status") == "mapped"
    ]
    transition_types = {
        int(screen.get("transition", {}).get("effectType", 0))
        for screen in game_manifest.get("screens", [])
        if screen.get("transition", {}).get("effectType", 0)
    }

    feature_checks = [
        {
            "feature": "linear interpolation",
            "manifestEvidence": {"animateCalcModes": summary.get("animateCalcModes", {})},
            "present": summary.get("animateCalcModes", {}).get("1") == 18,
            "snippets": (
                "function evaluatePowerPointFormula",
                "function applyAnimateBehavior",
                "function setMetric",
                "transitionList([\"left\", \"top\"], timing)",
            ),
        },
        {
            "feature": "acceleration/deceleration modifiers",
            "manifestEvidence": {"modifierTypes": {key: modifier_types.get(key, 0) for key in (3, 4, 5)}},
            "present": modifier_types.get(3, 0) > 0 and modifier_types.get(4, 0) > 0,
            "snippets": ("function modifierStrength", "ease-in", "ease-out", "autoReverse", "holdFill"),
        },
        {
            "feature": "parallel/sequential child scheduling",
            "manifestEvidence": {
                "timeSequenceData": summary.get("recordCounts", {}).get("RT_TimeSequenceData"),
                "timeNodeContainers": summary.get("timeNodeContainers"),
            },
            "present": int(summary.get("recordCounts", {}).get("RT_TimeSequenceData", 0)) == 135,
            "snippets": (
                "function scheduleChildNodes",
                "function nodeChildrenRunOnClick",
                "function nodeRunsSequentialChildren",
                "function subtreeDuration",
                "runAnimationNode(child, startDelay + childDelay",
            ),
        },
        {
            "feature": "chained start/end triggers",
            "manifestEvidence": {"conditionEvents": {key: condition_events.get(key, 0) for key in (3, 4)}},
            "present": condition_events.get(3, 0) > 0 and condition_events.get(4, 0) > 0,
            "snippets": (
                "function registerAnimationTriggerWaits",
                "function emitAnimationTrigger",
                "emitAnimationTrigger(3, node)",
                "emitAnimationTrigger(4, node)",
            ),
        },
        {
            "feature": "OnNext/OnPrev sequence traversal",
            "manifestEvidence": {
                "conditionEvents": {key: condition_events.get(key, 0) for key in (9, 10)},
                "timeSequenceData": summary.get("recordCounts", {}).get("RT_TimeSequenceData"),
            },
            "present": condition_events.get(9, 0) > 0 and condition_events.get(10, 0) > 0,
            "snippets": ("function nodeWaitsForClick", "state.animationQueue.push(node)", "function advanceAnimation"),
        },
        {
            "feature": "visibility changes",
            "manifestEvidence": {
                "variantStrings": sorted(variant_strings.intersection({"style.visibility", "visible", "hidden"})),
                "setBehaviors": behavior_kinds.get("set"),
            },
            "present": "style.visibility" in variant_strings and "visible" in variant_strings,
            "snippets": ("function applySetBehavior", "style.visibility", "element.style.visibility = visibility"),
        },
        {
            "feature": "motion paths",
            "manifestEvidence": {"motionBehaviors": behavior_kinds.get("motion")},
            "present": int(behavior_kinds.get("motion", 0)) > 0,
            "snippets": ("function motionEndpoint", "function applyMotionBehavior", "element.style.transform"),
        },
        {
            "feature": "scale behaviors",
            "manifestEvidence": {"scaleBehaviors": behavior_kinds.get("scale")},
            "present": int(behavior_kinds.get("scale", 0)) == 3,
            "snippets": ("function applyScaleBehavior", "function scaleTargetFromBehavior", "behavior.kind === \"scale\""),
        },
        {
            "feature": "slide transition effects",
            "manifestEvidence": {"transitionEffectTypes": sorted(transition_types)},
            "present": transition_types == {3, 11, 21, 22, 23, 27},
            "snippets": (
                "function transitionEffectClass",
                "function transitionDirectionClass",
                "`transition-effect-${effectType}`",
            ),
            "styleSnippets": (
                "transition-effect-22",
                "transition-effect-23",
                "slide-wipe-horizontal",
                "slide-wipe-vertical",
                "slide-push-in",
                "slide-dissolve-in",
            ),
        },
        {
            "feature": "sound commands",
            "manifestEvidence": {
                "commandBehaviors": behavior_kinds.get("command"),
                "mappedMediaBindings": len(mapped_media_bindings),
            },
            "present": int(behavior_kinds.get("command", 0)) > 0 and len(mapped_media_bindings) == 8,
            "snippets": ("function applyCommandBehavior", "function playAudioSource", "flushPendingAudioCommands"),
        },
    ]

    for check in feature_checks:
        if not check["present"]:
            fail(f"{check['feature']} manifest evidence is missing or changed: {check['manifestEvidence']}")
        require_snippets(app_js, check["feature"], check["snippets"])
        if check.get("styleSnippets"):
            require_snippets(styles_css, check["feature"], check["styleSnippets"])

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(
            {
                "format": "goblins-rpg3-animation-player-contract-v1",
                "summary": {
                    "features": len(feature_checks),
                    "allPassed": True,
                    "timeNodeContainers": summary.get("timeNodeContainers"),
                    "mappedMediaBindings": len(mapped_media_bindings),
                },
                "features": [
                    {
                        "feature": check["feature"],
                        "manifestEvidence": check["manifestEvidence"],
                        "runtimeSnippets": list(check["snippets"]),
                        "styleSnippets": list(check.get("styleSnippets", [])),
                    }
                    for check in feature_checks
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"animation player contract verification passed: {len(feature_checks)} features")


if __name__ == "__main__":
    main()
