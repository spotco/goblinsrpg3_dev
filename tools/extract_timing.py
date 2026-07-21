"""Extract slide transitions and legacy shape animation atoms.

Apache POI exposes PowerPoint 97-2003 slide transitions directly, but in this
file the 4081 animation atoms live inside OfficeArt client-data streams that
POI does not surface through HSLF's high-level slide model. This parser walks
the raw PowerPoint records and keeps the slide/shape context that the browser
runtime needs.
"""

from __future__ import annotations

import argparse
import json
import struct
from collections import Counter
from pathlib import Path

import olefile

from extract_ppt import iter_records_with_context, record_payload


SS_SLIDE_INFO_ATOM = 1017
ANIMATION_INFO_ATOM = 4081

TRANSITION_FLAG_BITS = {
    0x0001: "manualAdvance",
    0x0004: "hidden",
    0x0010: "sound",
    0x0040: "loopSound",
    0x0100: "stopSound",
    0x0400: "autoAdvance",
    0x1000: "cursorVisible",
}

ANIMATION_FLAG_BITS = {
    0x0001: "reverse",
    0x0004: "automatic",
    0x0010: "sound",
    0x0040: "stopSound",
    0x0100: "play",
    0x0400: "synchronous",
    0x1000: "hide",
    0x4000: "animateBackground",
}


def flags(mask: int, table: dict[int, str]) -> list[str]:
    return [name for bit, name in table.items() if mask & bit]


def parse_transition(payload: bytes) -> dict[str, object]:
    if len(payload) < 16:
        raise ValueError("SSSlideInfoAtom payload is shorter than 16 bytes")
    slide_time, sound_ref = struct.unpack_from("<II", payload, 0)
    direction = payload[8]
    effect_type = payload[9]
    transition_flags = struct.unpack_from("<H", payload, 10)[0]
    speed = payload[12]
    return {
        "slideTimeMs": slide_time,
        "soundRef": sound_ref,
        "effectDirection": direction,
        "effectType": effect_type,
        "flags": transition_flags,
        "flagNames": flags(transition_flags, TRANSITION_FLAG_BITS),
        "speed": speed,
        "rawHex": payload.hex(),
    }


def parse_animation(payload: bytes) -> dict[str, object]:
    if len(payload) < 28:
        raise ValueError("AnimationInfoAtom payload is shorter than 28 bytes")
    dim_color, mask, sound_ref, delay_time, order_id = struct.unpack_from("<IIIII", payload, 0)
    # POI's AnimationInfoAtom reads slideCount from offset 18, which overlaps
    # orderID. Preserve that value exactly for compatibility/audit purposes.
    slide_count = struct.unpack_from("<I", payload, 18)[0]
    return {
        "dimColor": dim_color,
        "mask": mask,
        "flagNames": flags(mask, ANIMATION_FLAG_BITS),
        "soundRef": sound_ref,
        "delayTimeMs": delay_time,
        "orderId": order_id,
        "slideCount": slide_count,
        "rawHex": payload.hex(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, default=Path("generated/timing_manifest.json"))
    args = parser.parse_args()

    transitions = []
    animations = []
    with olefile.OleFileIO(args.source) as ole:
        ppt = ole.openstream("PowerPoint Document").read()
        for record in iter_records_with_context(ppt):
            payload = record_payload(ppt, {key: record[key] for key in ("offset", "length")})
            if record["type"] == SS_SLIDE_INFO_ATOM and record["slide_order"]:
                transitions.append(
                    {
                        "slide": record["slide_order"],
                        "recordOffset": record["offset"],
                        **parse_transition(payload),
                    }
                )
            elif record["type"] == ANIMATION_INFO_ATOM and record["slide_order"]:
                animations.append(
                    {
                        "slide": record["slide_order"],
                        "shapeId": record["shape_id"],
                        "bounds": record["bounds"],
                        "recordOffset": record["offset"],
                        **parse_animation(payload),
                    }
                )

    manifest = {
        "format": "goblins-rpg3-timing-v1",
        "source": args.source.name,
        "transitions": transitions,
        "animations": animations,
        "summary": {
            "transitionCount": len(transitions),
            "animationCount": len(animations),
            "transitionEffects": dict(sorted(Counter(item["effectType"] for item in transitions).items())),
            "animationMasks": dict(sorted(Counter(item["mask"] for item in animations).items())),
            "animationDelays": dict(sorted(Counter(item["delayTimeMs"] for item in animations).items())),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"Wrote {args.output} with {len(transitions)} transitions and {len(animations)} animations")


if __name__ == "__main__":
    main()
