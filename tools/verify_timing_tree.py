"""Regression checks for extracted PP10 animation timing-tree data."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def as_count_map(items: list[dict[str, object]]) -> dict[int, int]:
    return {int(item["value"]): int(item["count"]) for item in items}


def record_count(report: dict[str, object], rec_type: int) -> int:
    for item in report["recordCounts"]:
        if int(item["type"]) == rec_type:
            return int(item["count"])
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", nargs="?", type=Path, default=Path("generated/timing_tree_audit.json"))
    args = parser.parse_args()

    report = json.loads(args.report.read_text(encoding="utf-8"))
    assert report["source"] == "goblins3 v.1.0 LAUNCH.pps"
    assert report["binaryTagBlobsWithTimingTrees"] == 197
    assert report["slidesWithTimingTrees"] == 197

    visual_targets = report["visualTargetReferences"]
    assert visual_targets["count"] == 1022
    assert visual_targets["shapeReferenceCount"] == 1015
    assert visual_targets["soundReferenceCount"] == 7
    assert visual_targets["unresolvedShapeReferenceCount"] == 0

    assert report["visualShapeReferences"]["count"] == 1015
    assert report["visualShapeReferences"]["unresolvedCount"] == 0

    assert record_count(report, 61764) == 2407  # RT_TimeExtTimeNodeContainer
    assert record_count(report, 61735) == 2533  # RT_TimeNode
    assert record_count(report, 61736) == 2093  # RT_TimeCondition
    assert record_count(report, 61737) == 478  # RT_TimeModifier
    assert record_count(report, 61761) == 135  # RT_TimeSequenceData
    assert record_count(report, 61762) == 6078  # RT_TimeVariant

    condition_events = as_count_map(report["conditionSummary"]["triggerEvents"])
    assert condition_events == {0: 1538, 1: 130, 3: 7, 4: 108, 9: 146, 10: 146, 11: 18}

    modifier_types = as_count_map(report["modifierSummary"]["modifierTypes"])
    assert modifier_types == {0: 12, 3: 229, 4: 227, 5: 10}

    animate_calc_modes = as_count_map(report["animateBehaviorSummary"]["calcModes"])
    assert animate_calc_modes == {1: 18}
    animate_value_types = as_count_map(report["animateBehaviorSummary"]["valueTypes"])
    assert animate_value_types == {1: 18}

    animation_value_times = as_count_map(report["animationValueSummary"]["times"])
    assert animation_value_times == {0: 16, 500: 3, 1000: 16}

    sequence_next_actions = as_count_map(report["sequenceSummary"]["nextActions"])
    assert sequence_next_actions == {1: 135}

    variant_strings = {item["value"]: int(item["count"]) for item in report["variantSummary"]["strings"]}
    for required in ("style.visibility", "visible", "fade", "ppt_x", "ppt_y", "#ppt_x", "#ppt_y"):
        assert required in variant_strings, required

    print("timing tree verification passed")


if __name__ == "__main__":
    main()
