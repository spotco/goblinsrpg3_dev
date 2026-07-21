"""Extract a JS-ready PP10 animation timing-tree manifest.

PowerPoint 2002/2003 stores complex animation timing trees in slide
programmable tag binary blobs. This decoder keeps the parent/child hierarchy
needed by a browser scheduler while also normalizing the atom data we currently
understand: time nodes, trigger conditions, modifiers, sequence data, animate
behavior settings, keyframe times, variants, and visual targets.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import olefile

from audit_timing_tree import (
    TIMING_RECORD_NAMES,
    parse_time_animate_behavior_atom,
    parse_time_animation_value_atom,
    parse_time_condition_atom,
    parse_time_modifier_atom,
    parse_time_node_atom,
    parse_time_sequence_data_atom,
    parse_time_variant,
    parse_visual_shape_atom,
)
from extract_ppt import RECORD_HEADER, iter_records, iter_records_with_context, record_payload


BEHAVIOR_CONTAINER_TYPES = {
    61739: "animate",
    61741: "effect",
    61742: "motion",
    61744: "scale",
    61745: "set",
    61746: "command",
}

BEHAVIOR_ATOM_TYPES = {
    61748: "animate",
    61750: "effect",
    61751: "motion",
    61753: "scale",
    61754: "set",
    61755: "command",
}


def parse_record_tree(data: bytes, start: int = 0, end: int | None = None, depth: int = 0) -> list[dict[str, object]]:
    end = len(data) if end is None else end
    offset = start
    records: list[dict[str, object]] = []
    while offset + RECORD_HEADER.size <= end:
        ver_instance, record_type, record_length = RECORD_HEADER.unpack_from(data, offset)
        record_end = offset + RECORD_HEADER.size + record_length
        if record_end > end:
            break
        version = ver_instance & 0xF
        record: dict[str, object] = {
            "offset": offset,
            "depth": depth,
            "version": version,
            "instance": ver_instance >> 4,
            "type": record_type,
            "name": TIMING_RECORD_NAMES.get(record_type, str(record_type)),
            "length": record_length,
            "children": [],
        }
        if version == 0xF:
            record["children"] = parse_record_tree(data, offset + RECORD_HEADER.size, record_end, depth + 1)
        records.append(record)
        offset = record_end
    return records


def payload_for(blob: bytes, record: dict[str, object]) -> bytes:
    start = int(record["offset"]) + RECORD_HEADER.size
    return blob[start : start + int(record["length"])]


def iter_descendants(record: dict[str, object], stop_at_time_nodes: bool = False):
    for child in record.get("children", []):
        if stop_at_time_nodes and child["type"] == 61764:
            continue
        yield child
        yield from iter_descendants(child, stop_at_time_nodes=stop_at_time_nodes)


def parse_known_atom(blob: bytes, record: dict[str, object]) -> dict[str, object] | None:
    payload = payload_for(blob, record)
    rec_type = int(record["type"])
    if rec_type == 11003:
        return parse_visual_shape_atom(payload)
    if rec_type == 61735:
        return parse_time_node_atom(payload)
    if rec_type == 61736:
        return parse_time_condition_atom(payload)
    if rec_type == 61737:
        return parse_time_modifier_atom(payload)
    if rec_type == 61748:
        return parse_time_animate_behavior_atom(payload)
    if rec_type == 61761:
        return parse_time_sequence_data_atom(payload)
    if rec_type == 61762:
        return parse_time_variant(payload)
    if rec_type == 61763:
        return parse_time_animation_value_atom(payload)
    return None


def compact_atom(blob: bytes, record: dict[str, object]) -> dict[str, object]:
    parsed = parse_known_atom(blob, record)
    result = {
        "type": record["type"],
        "name": record["name"],
        "instance": record["instance"],
        "offset": record["offset"],
        "length": record["length"],
    }
    if parsed is not None:
        result["parsed"] = parsed
    else:
        payload = payload_for(blob, record)
        if len(payload) <= 64:
            result["payloadHex"] = payload.hex()
        else:
            result["payloadPreviewHex"] = payload[:64].hex()
            result["payloadBytes"] = len(payload)
    return result


def collect_atoms(
    blob: bytes,
    record: dict[str, object],
    wanted_types: set[int],
    stop_at_time_nodes: bool = True,
) -> list[dict[str, object]]:
    atoms = []
    for descendant in iter_descendants(record, stop_at_time_nodes=stop_at_time_nodes):
        if int(descendant["type"]) in wanted_types:
            atoms.append(compact_atom(blob, descendant))
    return atoms


def parse_behavior(blob: bytes, record: dict[str, object]) -> dict[str, object]:
    behavior_kind = BEHAVIOR_CONTAINER_TYPES.get(int(record["type"]), str(record["type"]))
    atom_types = set(BEHAVIOR_ATOM_TYPES)
    atoms = collect_atoms(blob, record, atom_types, stop_at_time_nodes=True)
    targets = collect_atoms(blob, record, {11003}, stop_at_time_nodes=True)
    variants = collect_atoms(blob, record, {61762}, stop_at_time_nodes=True)
    keyframes = collect_atoms(blob, record, {61763}, stop_at_time_nodes=True)
    return {
        "kind": behavior_kind,
        "containerType": record["type"],
        "containerName": record["name"],
        "offset": record["offset"],
        "atoms": atoms,
        "targets": normalize_targets(targets),
        "variants": variants,
        "keyframes": keyframes,
    }


def normalize_targets(target_atoms: list[dict[str, object]]) -> list[dict[str, object]]:
    targets = []
    for atom in target_atoms:
        parsed = atom.get("parsed")
        if not isinstance(parsed, dict):
            continue
        reference_type = int(parsed.get("referenceType", 0))
        target = {
            "targetId": parsed.get("targetId"),
            "referenceType": reference_type,
            "visualElementType": parsed.get("visualElementType"),
            "atomOffset": atom.get("offset"),
        }
        if reference_type == 1:
            target["kind"] = "shape"
            target["shapeId"] = parsed.get("targetId")
        elif reference_type == 2:
            target["kind"] = "sound"
            target["soundId"] = parsed.get("targetId")
        else:
            target["kind"] = "unknown"
        targets.append(target)
    return targets


def parse_time_node_container(blob: bytes, record: dict[str, object], slide: int, next_id: list[int]) -> dict[str, object]:
    node_id = next_id[0]
    next_id[0] += 1
    direct_children = record.get("children", [])
    time_node_atoms = [
        compact_atom(blob, child)
        for child in direct_children
        if int(child["type"]) == 61735
    ]
    condition_atoms = collect_atoms(blob, record, {61736}, stop_at_time_nodes=True)
    modifier_atoms = collect_atoms(blob, record, {61737}, stop_at_time_nodes=True)
    sequence_atoms = collect_atoms(blob, record, {61761}, stop_at_time_nodes=True)
    target_atoms = collect_atoms(blob, record, {11003}, stop_at_time_nodes=True)
    variant_atoms = collect_atoms(blob, record, {61762}, stop_at_time_nodes=True)
    keyframe_atoms = collect_atoms(blob, record, {61763}, stop_at_time_nodes=True)
    behavior_containers = [
        parse_behavior(blob, descendant)
        for descendant in iter_descendants(record, stop_at_time_nodes=True)
        if int(descendant["type"]) in BEHAVIOR_CONTAINER_TYPES
    ]
    child_nodes = [
        parse_time_node_container(blob, child, slide, next_id)
        for child in direct_children
        if int(child["type"]) == 61764
    ]
    return {
        "id": f"s{slide:03d}-tn{node_id:04d}",
        "slide": slide,
        "recordOffset": record["offset"],
        "timeNode": time_node_atoms[0] if time_node_atoms else None,
        "conditions": condition_atoms,
        "modifiers": modifier_atoms,
        "sequence": sequence_atoms[0] if sequence_atoms else None,
        "targets": normalize_targets(target_atoms),
        "behaviors": behavior_containers,
        "variants": variant_atoms,
        "keyframes": keyframe_atoms,
        "children": child_nodes,
    }


def flatten_nodes(nodes: list[dict[str, object]]) -> list[dict[str, object]]:
    flat = []
    for node in nodes:
        flat.append(node)
        flat.extend(flatten_nodes(node.get("children", [])))
    return flat


def direct_time_node_containers(records: list[dict[str, object]]) -> list[dict[str, object]]:
    return [record for record in records if int(record["type"]) == 61764]


def load_known_shapes(poi_audit: Path) -> set[tuple[int, int]]:
    known = set()
    for line in poi_audit.read_text(encoding="utf-8-sig").splitlines():
        parts = line.split("\t")
        if parts and parts[0] == "SHAPE":
            known.add((int(parts[1]), int(parts[3])))
    return known


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--poi-audit", type=Path, default=Path("generated/poi_audit.tsv"))
    parser.add_argument("--output", type=Path, default=Path("generated/animations.json"))
    args = parser.parse_args()

    known_shapes = load_known_shapes(args.poi_audit)
    slides = []
    record_counts: Counter[int] = Counter()
    condition_events: Counter[int] = Counter()
    modifier_types: Counter[int] = Counter()
    animate_calc_modes: Counter[int] = Counter()
    behavior_kinds: Counter[str] = Counter()
    shape_targets = set()
    sound_targets = set()
    unresolved_shape_targets = []
    total_nodes = 0

    with olefile.OleFileIO(args.source) as ole:
        ppt = ole.openstream("PowerPoint Document").read()
        for record in iter_records_with_context(ppt):
            if record["type"] != 5003 or record["length"] <= 32 or not record["slide_order"]:
                continue
            blob = record_payload(ppt, {key: record[key] for key in ("offset", "length")})
            flat = list(iter_records(blob))
            flat_types = Counter(item["type"] for item in flat)
            if 61764 not in flat_types:
                continue

            slide = int(record["slide_order"])
            tree = parse_record_tree(blob)
            next_id = [1]
            roots = [
                parse_time_node_container(blob, node, slide, next_id)
                for node in direct_time_node_containers(tree)
            ]
            flat_nodes = flatten_nodes(roots)
            total_nodes += len(flat_nodes)
            for rec_type, count in flat_types.items():
                record_counts[int(rec_type)] += count
            for node in flat_nodes:
                for condition in node.get("conditions", []):
                    parsed = condition.get("parsed", {})
                    if isinstance(parsed, dict):
                        condition_events[int(parsed.get("triggerEvent", -1))] += 1
                for modifier in node.get("modifiers", []):
                    parsed = modifier.get("parsed", {})
                    if isinstance(parsed, dict):
                        modifier_types[int(parsed.get("modifierType", -1))] += 1
                for behavior in node.get("behaviors", []):
                    behavior_kinds[str(behavior["kind"])] += 1
                    for atom in behavior.get("atoms", []):
                        if atom.get("type") == 61748 and isinstance(atom.get("parsed"), dict):
                            animate_calc_modes[int(atom["parsed"].get("calcMode", -1))] += 1
                for target in node.get("targets", []):
                    if target.get("kind") == "shape":
                        shape_id = int(target["shapeId"])
                        shape_targets.add((slide, shape_id))
                        if (slide, shape_id) not in known_shapes:
                            unresolved_shape_targets.append({"slide": slide, "shapeId": shape_id})
                    elif target.get("kind") == "sound":
                        sound_targets.add((slide, int(target["soundId"])))

            slides.append(
                {
                    "slide": slide,
                    "sourceRecordOffset": record["offset"],
                    "recordCounts": {
                        TIMING_RECORD_NAMES.get(rec_type, str(rec_type)): count
                        for rec_type, count in sorted(flat_types.items())
                    },
                    "rootTimeNodes": roots,
                }
            )

    report = {
        "format": "goblins-rpg3-animation-manifest-v1",
        "source": args.source.name,
        "slides": slides,
        "summary": {
            "slidesWithAnimations": len(slides),
            "timeNodeContainers": total_nodes,
            "recordCounts": {
                TIMING_RECORD_NAMES.get(rec_type, str(rec_type)): count
                for rec_type, count in sorted(record_counts.items())
            },
            "conditionEvents": dict(sorted(condition_events.items())),
            "modifierTypes": dict(sorted(modifier_types.items())),
            "animateCalcModes": dict(sorted(animate_calc_modes.items())),
            "behaviorKinds": dict(sorted(behavior_kinds.items())),
            "shapeTargets": len(shape_targets),
            "soundTargets": len(sound_targets),
            "unresolvedShapeTargets": unresolved_shape_targets,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(
        f"Wrote {args.output} with {len(slides)} animated slides, "
        f"{total_nodes} time nodes, {len(shape_targets)} shape targets"
    )


if __name__ == "__main__":
    main()
