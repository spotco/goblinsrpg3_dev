"""Audit PowerPoint 10 timing-tree records inside slide programmable tags.

The older AnimationInfoAtom records are not enough for complex PowerPoint
animations. PowerPoint 2002/2003 stores richer effects in PP10 slide binary
tag extensions inside RT_ProgTags/RT_ProgBinaryTag/RT_BinaryTagDataBlob.
This audit confirms which timing-tree records are present and whether visual
elements refer back to known slide shapes.
"""

from __future__ import annotations

import argparse
import json
import struct
from collections import Counter, defaultdict
from pathlib import Path

import olefile

from extract_ppt import iter_records, iter_records_with_context, record_payload


TIMING_RECORD_NAMES = {
    11003: "RT_VisualShapeAtom",
    11008: "RT_HashCodeAtom",
    11010: "RT_BuildList",
    11011: "RT_BuildAtom",
    11016: "RT_ParaBuild",
    11017: "RT_ParaBuildAtom",
    12011: "RT_SlideTime10Atom",
    61733: "RT_TimeConditionContainer",
    61735: "RT_TimeNode",
    61736: "RT_TimeCondition",
    61737: "RT_TimeModifier",
    61738: "RT_TimeBehaviorContainer",
    61739: "RT_TimeAnimateBehaviorContainer",
    61741: "RT_TimeEffectBehaviorContainer",
    61742: "RT_TimeMotionBehaviorContainer",
    61744: "RT_TimeScaleBehaviorContainer",
    61745: "RT_TimeSetBehaviorContainer",
    61746: "RT_TimeCommandBehaviorContainer",
    61747: "RT_TimeBehavior",
    61748: "RT_TimeAnimateBehavior",
    61750: "RT_TimeEffectBehavior",
    61751: "RT_TimeMotionBehavior",
    61753: "RT_TimeScaleBehavior",
    61754: "RT_TimeSetBehavior",
    61755: "RT_TimeCommandBehavior",
    61756: "RT_TimeClientVisualElement",
    61757: "RT_TimePropertyList",
    61758: "RT_TimeVariantList",
    61759: "RT_TimeAnimationValueList",
    61760: "RT_TimeIterateData",
    61761: "RT_TimeSequenceData",
    61762: "RT_TimeVariant",
    61763: "RT_TimeAnimationValue",
    61764: "RT_TimeExtTimeNodeContainer",
    61765: "RT_TimeSubEffectContainer",
}


def parse_visual_shape_atom(payload: bytes) -> dict[str, int] | None:
    # VisualShapeAtom stores the shape id in the third DWORD for the shape
    # animation cases observed in PP10 timing trees. The first two DWORDs are
    # visual-element metadata, not the slide shape id.
    if len(payload) < 12:
        return None
    return {
        "targetId": struct.unpack_from("<I", payload, 8)[0],
        "visualElementType": struct.unpack_from("<I", payload, 0)[0],
        "referenceType": struct.unpack_from("<I", payload, 4)[0],
    }


def parse_time_node_atom(payload: bytes) -> dict[str, object] | None:
    if len(payload) < 32:
        return None
    flags = struct.unpack_from("<I", payload, 28)[0]
    return {
        "restart": struct.unpack_from("<I", payload, 4)[0],
        "nodeType": struct.unpack_from("<I", payload, 8)[0],
        "fill": struct.unpack_from("<I", payload, 12)[0],
        "durationMs": struct.unpack_from("<i", payload, 24)[0],
        "flags": flags,
        "usesFill": bool(flags & 0x01),
        "usesRestart": bool(flags & 0x02),
        "usesGroupingType": bool(flags & 0x08),
        "usesDuration": bool(flags & 0x10),
    }


def parse_time_condition_atom(payload: bytes) -> dict[str, int] | None:
    if len(payload) < 16:
        return None
    trigger_object, trigger_event, target_id, delay = struct.unpack_from("<IIIi", payload)
    return {
        "triggerObject": trigger_object,
        "triggerEvent": trigger_event,
        "targetId": target_id,
        "delayMs": delay,
    }


def parse_time_modifier_atom(payload: bytes) -> dict[str, object] | None:
    if len(payload) < 8:
        return None
    mod_type, raw_value = struct.unpack_from("<II", payload)
    float_value = struct.unpack_from("<f", payload, 4)[0]
    return {
        "modifierType": mod_type,
        "rawValue": raw_value,
        "floatValue": float_value,
    }


def parse_time_animate_behavior_atom(payload: bytes) -> dict[str, object] | None:
    if len(payload) < 12:
        return None
    calc_mode, flags, value_type = struct.unpack_from("<III", payload)
    return {
        "calcMode": calc_mode,
        "flags": flags,
        "valueType": value_type,
        "usesBy": bool(flags & 0x01),
        "usesFrom": bool(flags & 0x02),
        "usesTo": bool(flags & 0x04),
        "usesCalcMode": bool(flags & 0x08),
        "usesAnimationValues": bool(flags & 0x10),
        "usesValueType": bool(flags & 0x20),
    }


def parse_time_animation_value_atom(payload: bytes) -> dict[str, object] | None:
    if len(payload) < 4:
        return None
    return {"time": struct.unpack_from("<i", payload)[0]}


def parse_time_sequence_data_atom(payload: bytes) -> dict[str, object] | None:
    if len(payload) < 20:
        return None
    concurrency, next_action, previous_action, _reserved, flags = struct.unpack_from("<IIIII", payload)
    return {
        "concurrency": concurrency,
        "nextAction": next_action,
        "previousAction": previous_action,
        "flags": flags,
        "usesConcurrency": bool(flags & 0x01),
        "usesNextAction": bool(flags & 0x02),
        "usesPreviousAction": bool(flags & 0x04),
    }


def parse_time_variant(payload: bytes) -> dict[str, object] | None:
    if not payload:
        return None
    variant_type = payload[0]
    result: dict[str, object] = {"variantType": variant_type}
    value = payload[1:]
    if variant_type == 0 and len(value) >= 1:
        result["boolValue"] = bool(value[0])
    elif variant_type == 1 and len(value) >= 4:
        result["intValue"] = struct.unpack_from("<i", value)[0]
    elif variant_type == 2 and len(value) >= 4:
        result["floatValue"] = struct.unpack_from("<f", value)[0]
    elif variant_type == 3:
        result["stringValue"] = value.decode("utf-16le", "ignore").rstrip("\x00")
    return result


def counter_items(counter: Counter) -> list[dict[str, object]]:
    return [{"value": key, "count": count} for key, count in sorted(counter.items())]


def sample_append(items: list[dict[str, object]], item: dict[str, object], limit: int = 30) -> None:
    if len(items) < limit:
        items.append(item)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--poi-audit", type=Path, default=Path("generated/poi_audit.tsv"))
    parser.add_argument("--output", type=Path, default=Path("generated/timing_tree_audit.json"))
    args = parser.parse_args()

    known_shapes = set()
    if args.poi_audit.exists():
        for line in args.poi_audit.read_text(encoding="utf-8-sig").splitlines():
            parts = line.split("\t")
            if parts and parts[0] == "SHAPE":
                known_shapes.add((int(parts[1]), int(parts[3])))

    slide_counts: dict[int, Counter[int]] = defaultdict(Counter)
    all_counts: Counter[int] = Counter()
    visual_shape_refs = []
    time_node_types: Counter[int] = Counter()
    time_node_durations: Counter[int] = Counter()
    condition_objects: Counter[int] = Counter()
    condition_events: Counter[int] = Counter()
    condition_delays: Counter[int] = Counter()
    modifier_types: Counter[int] = Counter()
    modifier_values: Counter[str] = Counter()
    animate_calc_modes: Counter[int] = Counter()
    animate_value_types: Counter[int] = Counter()
    animation_value_times: Counter[int] = Counter()
    sequence_concurrency: Counter[int] = Counter()
    sequence_next_actions: Counter[int] = Counter()
    sequence_previous_actions: Counter[int] = Counter()
    variant_types: Counter[int] = Counter()
    variant_instances: Counter[int] = Counter()
    variant_strings: Counter[str] = Counter()
    time_node_samples: list[dict[str, object]] = []
    condition_samples: list[dict[str, object]] = []
    modifier_samples: list[dict[str, object]] = []
    animate_behavior_samples: list[dict[str, object]] = []
    animation_value_samples: list[dict[str, object]] = []
    sequence_samples: list[dict[str, object]] = []
    variant_string_samples: list[dict[str, object]] = []
    binary_tag_blobs = 0
    with olefile.OleFileIO(args.source) as ole:
        ppt = ole.openstream("PowerPoint Document").read()
        for record in iter_records_with_context(ppt):
            if record["type"] != 5003 or record["length"] <= 32:
                continue
            payload = record_payload(ppt, {key: record[key] for key in ("offset", "length")})
            nested_records = list(iter_records(payload))
            nested_types = Counter(item["type"] for item in nested_records)
            # Ignore hyperlink extension blobs; timing blobs have TimeExtTimeNode.
            if 61764 not in nested_types:
                continue
            binary_tag_blobs += 1
            slide = record["slide_order"]
            for nested in nested_records:
                rec_type = nested["type"]
                all_counts[rec_type] += 1
                if slide:
                    slide_counts[int(slide)][rec_type] += 1
                if rec_type == 11003 and slide:
                    shape_ref = parse_visual_shape_atom(record_payload(payload, nested))
                    if shape_ref is not None:
                        visual_shape_refs.append(
                            {
                                "slide": int(slide),
                                "targetId": shape_ref["targetId"],
                                "shapeId": shape_ref["targetId"] if shape_ref["referenceType"] == 1 else None,
                                "visualElementType": shape_ref["visualElementType"],
                                "referenceType": shape_ref["referenceType"],
                                "knownShape": (
                                    (int(slide), shape_ref["targetId"]) in known_shapes
                                    if shape_ref["referenceType"] == 1
                                    else None
                                ),
                                "recordOffset": record["offset"],
                            }
                        )
                elif rec_type == 61735:
                    parsed = parse_time_node_atom(record_payload(payload, nested))
                    if parsed is not None:
                        time_node_types[int(parsed["nodeType"])] += 1
                        time_node_durations[int(parsed["durationMs"])] += 1
                        sample_append(time_node_samples, {"slide": slide, **parsed})
                elif rec_type == 61736:
                    parsed = parse_time_condition_atom(record_payload(payload, nested))
                    if parsed is not None:
                        condition_objects[parsed["triggerObject"]] += 1
                        condition_events[parsed["triggerEvent"]] += 1
                        condition_delays[parsed["delayMs"]] += 1
                        sample_append(condition_samples, {"slide": slide, **parsed})
                elif rec_type == 61737:
                    parsed = parse_time_modifier_atom(record_payload(payload, nested))
                    if parsed is not None:
                        modifier_types[int(parsed["modifierType"])] += 1
                        modifier_values[f'{parsed["modifierType"]}:{parsed["rawValue"]:08x}'] += 1
                        sample_append(modifier_samples, {"slide": slide, **parsed})
                elif rec_type == 61748:
                    parsed = parse_time_animate_behavior_atom(record_payload(payload, nested))
                    if parsed is not None:
                        animate_calc_modes[int(parsed["calcMode"])] += 1
                        animate_value_types[int(parsed["valueType"])] += 1
                        sample_append(animate_behavior_samples, {"slide": slide, **parsed})
                elif rec_type == 61761:
                    parsed = parse_time_sequence_data_atom(record_payload(payload, nested))
                    if parsed is not None:
                        sequence_concurrency[int(parsed["concurrency"])] += 1
                        sequence_next_actions[int(parsed["nextAction"])] += 1
                        sequence_previous_actions[int(parsed["previousAction"])] += 1
                        sample_append(sequence_samples, {"slide": slide, **parsed})
                elif rec_type == 61762:
                    parsed = parse_time_variant(record_payload(payload, nested))
                    if parsed is not None:
                        variant_types[int(parsed["variantType"])] += 1
                        variant_instances[int(nested["instance"])] += 1
                        string_value = parsed.get("stringValue")
                        if isinstance(string_value, str) and string_value:
                            variant_strings[string_value] += 1
                            sample_append(
                                variant_string_samples,
                                {"slide": slide, "instance": nested["instance"], "stringValue": string_value},
                            )
                elif rec_type == 61763:
                    parsed = parse_time_animation_value_atom(record_payload(payload, nested))
                    if parsed is not None:
                        animation_value_times[int(parsed["time"])] += 1
                        sample_append(animation_value_samples, {"slide": slide, **parsed})

    shape_refs = [item for item in visual_shape_refs if item["referenceType"] == 1]
    sound_refs = [item for item in visual_shape_refs if item["referenceType"] == 2]
    unresolved_refs = [item for item in shape_refs if not item["knownShape"]]
    report = {
        "format": "goblins-rpg3-timing-tree-audit-v1",
        "source": args.source.name,
        "binaryTagBlobsWithTimingTrees": binary_tag_blobs,
        "recordCounts": [
            {"type": rec_type, "name": TIMING_RECORD_NAMES.get(rec_type, "UNKNOWN"), "count": count}
            for rec_type, count in sorted(all_counts.items())
        ],
        "slidesWithTimingTrees": len(slide_counts),
        "slideCounts": {
            str(slide): {
                TIMING_RECORD_NAMES.get(rec_type, str(rec_type)): count
                for rec_type, count in sorted(counts.items())
            }
            for slide, counts in sorted(slide_counts.items())
        },
        "visualShapeReferences": {
            "count": len(shape_refs),
            "unresolvedCount": len(unresolved_refs),
            "unresolvedSample": unresolved_refs[:20],
        },
        "visualTargetReferences": {
            "count": len(visual_shape_refs),
            "shapeReferenceCount": len(shape_refs),
            "soundReferenceCount": len(sound_refs),
            "unresolvedShapeReferenceCount": len(unresolved_refs),
            "unresolvedShapeReferenceSample": unresolved_refs[:20],
        },
        "animationTargets": {
            "shapeTargetsBySlide": {
                str(slide): sorted(
                    {
                        int(item["shapeId"])
                        for item in shape_refs
                        if int(item["slide"]) == slide and item["shapeId"] is not None
                    }
                )
                for slide in sorted({int(item["slide"]) for item in shape_refs})
            },
            "soundTargets": sorted(
                {
                    f'{int(item["slide"])}:{int(item["targetId"])}'
                    for item in sound_refs
                }
            ),
        },
        "timeNodeSummary": {
            "nodeTypes": counter_items(time_node_types),
            "durationMs": counter_items(time_node_durations),
            "sample": time_node_samples,
        },
        "conditionSummary": {
            "triggerObjects": counter_items(condition_objects),
            "triggerEvents": counter_items(condition_events),
            "delayMs": counter_items(condition_delays),
            "sample": condition_samples,
        },
        "modifierSummary": {
            "modifierTypes": counter_items(modifier_types),
            "modifierValues": counter_items(modifier_values),
            "sample": modifier_samples,
        },
        "animateBehaviorSummary": {
            "calcModes": counter_items(animate_calc_modes),
            "valueTypes": counter_items(animate_value_types),
            "sample": animate_behavior_samples,
        },
        "animationValueSummary": {
            "times": counter_items(animation_value_times),
            "sample": animation_value_samples,
        },
        "sequenceSummary": {
            "concurrency": counter_items(sequence_concurrency),
            "nextActions": counter_items(sequence_next_actions),
            "previousActions": counter_items(sequence_previous_actions),
            "sample": sequence_samples,
        },
        "variantSummary": {
            "variantTypes": counter_items(variant_types),
            "recordInstances": counter_items(variant_instances),
            "strings": counter_items(variant_strings),
            "stringSample": variant_string_samples,
        },
    }
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(
        f"Wrote {args.output} with {binary_tag_blobs} timing blobs, "
        f"{len(visual_shape_refs)} visual target refs, {len(unresolved_refs)} unresolved shape refs"
    )


if __name__ == "__main__":
    main()
