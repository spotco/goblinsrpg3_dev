"""Extract inventory and bitmap assets from a PowerPoint 97-2003 .pps file.

This deliberately keeps the MS-PPT record parser small and transparent. It
does not render slides or claim to interpret every record; it creates a stable
inventory that later extraction/rendering steps can consume.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import struct
from collections import Counter
from pathlib import Path
from typing import Iterator

import olefile
from PIL import Image


RECORD_HEADER = struct.Struct("<HHI")
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
PNG_BLIP = 0xF01E  # OfficeArtFBSE/PNG blip record
DIB_BLIP = 0xF01F  # OfficeArtDIB blip record
SLIDE = 1006
SLIDE_ATOM = 1007
INTERACTIVE_INFO_ATOM = 4083
EX_HYPERLINK = 4055
EX_HYPERLINK_ATOM = 4051
SOUND = 2022
SOUND_DATA = 2023
TEXT_CHARS = 4000
TEXT_BYTES = 4008
OFFICEART_SP_CONTAINER = 0xF004
OFFICEART_SP = 0xF00A
OFFICEART_CLIENT_ANCHOR = 0xF010
SLIDE_LIST_WITH_TEXT = 4080
SLIDE_PERSIST_ATOM = 1011
CSTRING = 4026

# PowerPoint DocSummary hyperlink destinations use "slideId,staleNum,Slide staleNum".
# ExHyperlink CString labels are often STALE after slides are reordered; modern PPT
# and pptx re-export resolve by slideId via SlideListWithText presentation order.
DOCSUM_HLINK_RE = re.compile(
    rb"(?:[\x30-\x39]\x00)+,\x00(?:[\x30-\x39]\x00)+,\x00"
    rb"S\x00l\x00i\x00d\x00e\x00 \x00(?:[\x30-\x39]\x00)+"
)


def iter_records(
    data: bytes, start: int = 0, end: int | None = None, depth: int = 0
) -> Iterator[dict[str, int]]:
    """Yield valid records and recurse into records whose version is 0xF."""

    end = len(data) if end is None else end
    offset = start
    while offset + RECORD_HEADER.size <= end:
        ver_instance, record_type, record_length = RECORD_HEADER.unpack_from(data, offset)
        record_end = offset + RECORD_HEADER.size + record_length
        if record_end > end:
            return
        record = {
            "offset": offset,
            "depth": depth,
            "version": ver_instance & 0xF,
            "instance": ver_instance >> 4,
            "type": record_type,
            "length": record_length,
        }
        yield record
        if record["version"] == 0xF:
            yield from iter_records(data, offset + RECORD_HEADER.size, record_end, depth + 1)
        offset = record_end


def record_payload(data: bytes, record: dict[str, int]) -> bytes:
    start = record["offset"] + RECORD_HEADER.size
    return data[start : start + record["length"]]


def iter_records_with_context(
    data: bytes,
    start: int = 0,
    end: int | None = None,
    depth: int = 0,
    slide_state: dict[str, int] | None = None,
    shape_context: dict[str, object] | None = None,
) -> Iterator[dict[str, object]]:
    """Walk records while retaining the containing slide and shape bounds."""

    end = len(data) if end is None else end
    slide_state = {"order": 0} if slide_state is None else slide_state
    active_shape_context = shape_context
    offset = start
    while offset + RECORD_HEADER.size <= end:
        ver_instance, record_type, record_length = RECORD_HEADER.unpack_from(data, offset)
        record_end = offset + RECORD_HEADER.size + record_length
        if record_end > end:
            return
        record: dict[str, object] = {
            "offset": offset,
            "depth": depth,
            "version": ver_instance & 0xF,
            "instance": ver_instance >> 4,
            "type": record_type,
            "length": record_length,
            "slide_order": slide_state["order"] or None,
            "shape_id": active_shape_context.get("shape_id") if active_shape_context else None,
            "bounds": active_shape_context.get("bounds") if active_shape_context else None,
        }
        if depth == 0 and record_type == SLIDE:
            slide_state["order"] += 1
            record["slide_order"] = slide_state["order"]
        next_shape_context = active_shape_context
        if record_type == OFFICEART_SP_CONTAINER:
            next_shape_context = {"shape_id": None, "bounds": None}
        elif record_type == OFFICEART_SP and active_shape_context is not None:
            payload = record_payload(data, {key: record[key] for key in ("offset", "length")})
            if len(payload) >= 4:
                next_shape_context = dict(active_shape_context)
                next_shape_context["shape_id"] = struct.unpack_from("<I", payload)[0]
        elif record_type == OFFICEART_CLIENT_ANCHOR and active_shape_context is not None:
            payload = record_payload(data, {key: record[key] for key in ("offset", "length")})
            if len(payload) >= 8:
                next_shape_context = dict(active_shape_context)
                next_shape_context["bounds"] = list(struct.unpack_from("<hhhh", payload))
        if record_type in (OFFICEART_SP, OFFICEART_CLIENT_ANCHOR):
            active_shape_context = next_shape_context
        yield record
        if (ver_instance & 0xF) == 0xF:
            yield from iter_records_with_context(
                data,
                offset + RECORD_HEADER.size,
                record_end,
                depth + 1,
                slide_state,
                next_shape_context,
            )
        offset = record_end


def png_end(data: bytes, start: int) -> int:
    end_marker = b"IEND\xaeB`\x82"
    end = data.find(end_marker, start)
    if end < 0:
        raise ValueError("PNG payload has no IEND marker")
    return end + len(end_marker)


def dib_to_bmp(dib: bytes) -> bytes:
    """Add a BITMAPFILEHEADER to the DIB payload stored by OfficeArt."""

    if len(dib) < 40:
        raise ValueError("DIB payload is shorter than BITMAPINFOHEADER")
    header_size, _width, _height, _planes, bpp, _compression, _image_size, _xppm, _yppm, colors_used, _important = struct.unpack_from(
        "<IiiHHIIiiII", dib
    )
    if header_size < 40:
        raise ValueError(f"Unsupported DIB header size: {header_size}")
    palette_entries = colors_used or (1 << bpp if bpp <= 8 else 0)
    pixel_offset = 14 + header_size + palette_entries * 4
    file_size = 14 + len(dib)
    return b"BM" + struct.pack("<IHHI", file_size, 0, 0, pixel_offset) + dib


def extract_pictures(pictures: bytes, output_dir: Path) -> list[dict[str, object]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    assets: list[dict[str, object]] = []
    index = 0
    for record in iter_records(pictures):
        if record["depth"] != 0 or record["type"] not in (PNG_BLIP, DIB_BLIP):
            continue
        payload = record_payload(pictures, record)
        # OfficeArt bitmap payloads begin with a 16-byte UID and a one-byte
        # compression flag. Searching for the signature is robust to the
        # optional OfficeArt fields present in old files.
        if record["type"] == PNG_BLIP:
            start = payload.find(PNG_SIGNATURE)
            if start < 0:
                raise ValueError(f"PNG blip at {record['offset']} has no PNG signature")
            raw = payload[start : png_end(payload, start)]
            image = Image.open(io.BytesIO(raw))
            image.verify()
            suffix = "png"
            output = output_dir / f"asset-{index:03d}.png"
            output.write_bytes(raw)
        else:
            dib = payload[17:]
            bmp = dib_to_bmp(dib)
            image = Image.open(io.BytesIO(bmp))
            output = output_dir / f"asset-{index:03d}.png"
            image.convert("RGBA").save(output, format="PNG")
            suffix = "dib->png"
        # Re-open the written file so metadata describes the browser asset.
        with Image.open(output) as checked:
            width, height = checked.size
            mode = checked.mode
        assets.append(
            {
                "id": f"asset-{index:03d}",
                "source_record_offset": record["offset"],
                "source_record_type": record["type"],
                "encoding": suffix,
                "path": output.as_posix(),
                "width": width,
                "height": height,
                "mode": mode,
                "bytes": output.stat().st_size,
                "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
            }
        )
        index += 1
    return assets



def build_slide_id_to_presentation_order(ppt: bytes, records: list[dict[str, int]]) -> dict[int, int]:
    """Map SlidePersistAtom.slideId -> 1-based presentation order (SlideListWithText inst 0)."""

    mapping: dict[int, int] = {}
    for container in records:
        if container["type"] != SLIDE_LIST_WITH_TEXT or container["instance"] != 0:
            continue
        start = container["offset"] + RECORD_HEADER.size
        end = start + container["length"]
        order = 0
        for record in records:
            if record["type"] != SLIDE_PERSIST_ATOM:
                continue
            if not (start <= record["offset"] < end):
                continue
            payload = ppt[
                record["offset"] + RECORD_HEADER.size : record["offset"] + RECORD_HEADER.size + record["length"]
            ]
            if len(payload) < 20:
                continue
            _psr_id, _reserved, _num_texts, slide_id, _flags = struct.unpack_from("<iiiii", payload)
            order += 1
            mapping[slide_id] = order
        break
    return mapping


def parse_docsum_hyperlink_destinations(ole: olefile.OleFileIO) -> list[dict[str, object]]:
    """Ordered DocSummary destinations: slideId + stale friendly Slide N label."""

    try:
        docsum = ole.openstream(["\x05DocumentSummaryInformation"]).read()
    except OSError:
        return []
    destinations: list[dict[str, object]] = []
    for match in DOCSUM_HLINK_RE.finditer(docsum):
        raw = match.group().decode("utf-16-le")
        parts = raw.split(",", 2)
        if len(parts) != 3:
            continue
        try:
            slide_id = int(parts[0])
            stale_num = int(parts[1])
        except ValueError:
            continue
        label = parts[2]
        destinations.append(
            {
                "slideId": slide_id,
                "staleSlideNumber": stale_num,
                "label": label,
                "raw": raw,
            }
        )
    return destinations


def resolve_hyperlink_targets(
    hyperlinks_ordered: list[dict[str, object]],
    docsum_destinations: list[dict[str, object]],
    slide_id_to_order: dict[int, int],
) -> None:
    """Mutate hyperlink dicts with slideId-resolved target_slide (PPT-faithful)."""

    if len(docsum_destinations) != len(hyperlinks_ordered):
        # Fall back to stale label numbers if DocSummary is missing/mismatched.
        for link in hyperlinks_ordered:
            match = re.fullmatch(r"Slide (\d+)", str(link.get("label") or ""))
            link["target_slide"] = int(match.group(1)) if match else None
            link["resolveMethod"] = "friendly_label_fallback"
            link["labelStale"] = False
        return

    stale_count = 0
    for link, dest in zip(hyperlinks_ordered, docsum_destinations):
        label = str(link.get("label") or "")
        if dest["label"] != label:
            # Keep pairing by order (both tables are append-ordered); note mismatch.
            link["docsumLabelMismatch"] = dest["label"]
        slide_id = int(dest["slideId"])
        resolved = slide_id_to_order.get(slide_id)
        stale_num = int(dest["staleSlideNumber"])
        label_match = re.fullmatch(r"Slide (\d+)", label)
        label_num = int(label_match.group(1)) if label_match else stale_num
        link["slideId"] = slide_id
        link["labelSlideNumber"] = label_num
        link["target_slide"] = resolved
        link["resolveMethod"] = "docsum_slide_id"
        link["labelStale"] = bool(resolved is not None and resolved != label_num)
        if link["labelStale"]:
            stale_count += 1
    # stash summary on first link for callers; also return via side channel below
    if hyperlinks_ordered:
        hyperlinks_ordered[0]["_staleLabelCount"] = stale_count


def stream_inventory(ole: olefile.OleFileIO) -> list[dict[str, object]]:
    streams = []
    for parts in ole.listdir(streams=True, storages=False):
        path = "/".join(parts)
        streams.append({"path": path, "bytes": ole.get_size(parts)})
    return streams


def build_inventory(source: Path, output_dir: Path) -> dict[str, object]:
    source_bytes = source.read_bytes()
    with olefile.OleFileIO(source) as ole:
        ppt = ole.openstream("PowerPoint Document").read()
        pictures = ole.openstream("Pictures").read()
        records = list(iter_records(ppt))
        contextual_records = list(iter_records_with_context(ppt))
        counts = Counter(record["type"] for record in records)
        slides = [
            {key: record[key] for key in ("offset", "length", "depth", "instance")}
            for record in records
            if record["type"] == SLIDE and record["depth"] == 0
        ]
        actions = [
            {
                **{key: record[key] for key in ("offset", "length", "depth", "instance")},
                "type": record["type"],
                "payload_hex": record_payload(ppt, record).hex(),
            }
            for record in records
            if record["type"] in (INTERACTIVE_INFO_ATOM, EX_HYPERLINK, EX_HYPERLINK_ATOM)
        ]
        sounds = [
            {key: record[key] for key in ("offset", "length", "depth", "instance", "type")}
            for record in records
            if record["type"] in (SOUND, SOUND_DATA)
        ]
        # ExHyperlink containers are append-ordered; DocSummary destinations pair 1:1.
        hyperlinks_ordered: list[dict[str, object]] = []
        for event in contextual_records:
            if event["type"] != EX_HYPERLINK:
                continue
            payload_start = int(event["offset"]) + RECORD_HEADER.size
            payload_end = payload_start + int(event["length"])
            link_id = None
            label = ""
            child = payload_start
            while child + RECORD_HEADER.size <= payload_end:
                _vi, child_type, child_length = RECORD_HEADER.unpack_from(ppt, child)
                child_payload = ppt[child + RECORD_HEADER.size : child + RECORD_HEADER.size + child_length]
                if child_type == EX_HYPERLINK_ATOM and len(child_payload) >= 4:
                    link_id = struct.unpack_from("<I", child_payload)[0]
                elif child_type == CSTRING:
                    label = child_payload.decode("utf-16le", "ignore")
                child += RECORD_HEADER.size + child_length
            if link_id is not None:
                hyperlinks_ordered.append(
                    {
                        "id": link_id,
                        "label": label,
                        "record_offset": event["offset"],
                    }
                )
        slide_id_to_order = build_slide_id_to_presentation_order(ppt, records)
        docsum_destinations = parse_docsum_hyperlink_destinations(ole)
        resolve_hyperlink_targets(hyperlinks_ordered, docsum_destinations, slide_id_to_order)
        hyperlinks: dict[int, dict[str, object]] = {
            int(link["id"]): link for link in hyperlinks_ordered
        }
        stale_label_count = sum(1 for link in hyperlinks_ordered if link.get("labelStale"))
        objects = []
        text_runs = []
        interactive_actions = []
        for event in contextual_records:
            if event["type"] == OFFICEART_SP:
                payload = record_payload(ppt, {key: event[key] for key in ("offset", "length")})
                if len(payload) >= 4:
                    objects.append(
                        {
                            "slide": event["slide_order"],
                            "shape_id": struct.unpack_from("<I", payload)[0],
                            "bounds": event["bounds"],
                            "record_offset": event["offset"],
                        }
                    )
            if event["type"] in (TEXT_CHARS, TEXT_BYTES):
                payload = record_payload(ppt, {key: event[key] for key in ("offset", "length")})
                text = (
                    payload.decode("utf-16le", "replace")
                    if event["type"] == TEXT_CHARS
                    else payload.decode("cp1252", "replace")
                )
                text_runs.append(
                    {
                        "slide": event["slide_order"],
                        "shape_id": event["shape_id"],
                        "bounds": event["bounds"],
                        "record_offset": event["offset"],
                        "encoding": "utf-16le" if event["type"] == TEXT_CHARS else "cp1252",
                        "text": text,
                    }
                )
            if event["type"] != INTERACTIVE_INFO_ATOM:
                continue
            payload = record_payload(ppt, {key: event[key] for key in ("offset", "length")})
            if len(payload) < 12:
                continue
            sound_ref, hyperlink_id = struct.unpack_from("<II", payload)
            action_code = payload[8]
            target = hyperlinks.get(hyperlink_id)
            label = target["label"] if target else None
            # Prefer DocSummary slideId → presentation order (stale "Slide N" labels lie).
            if target and target.get("target_slide") is not None:
                target_slide = int(target["target_slide"])
                resolve_method = target.get("resolveMethod")
            else:
                match = re.fullmatch(r"Slide (\d+)", label or "")
                target_slide = int(match.group(1)) if match else None
                resolve_method = "friendly_label_fallback" if match else None
            interactive_actions.append(
                {
                    "record_offset": event["offset"],
                    "slide": event["slide_order"],
                    "shape_id": event["shape_id"],
                    "bounds": event["bounds"],
                    "sound_ref": sound_ref,
                    "hyperlink_id": hyperlink_id,
                    "target_label": label,
                    "target_slide": target_slide,
                    "target_slide_id": target.get("slideId") if target else None,
                    "label_slide_number": target.get("labelSlideNumber") if target else None,
                    "label_stale": bool(target.get("labelStale")) if target else False,
                    "resolve_method": resolve_method,
                    "action_code": action_code,
                    "flags_hex": payload[12:].hex(),
                }
            )
        navigation_edges = [
            action
            for action in interactive_actions
            if action["target_slide"] is not None
        ]
        assets = extract_pictures(pictures, output_dir / "assets")
        source_audio = [
            {"path": name, "bytes": (source.parent / name).stat().st_size}
            for name in ("titlesong.wma", "rocksong.wma", "Ffvictory.mid")
            if (source.parent / name).exists()
        ]
        inventory = {
            "format": "goblins-rpg3-powerpoint-inventory-v1",
            "source": {
                "path": source.name,
                "bytes": len(source_bytes),
                "sha256": hashlib.sha256(source_bytes).hexdigest(),
            },
            "presentation": {"width": 5760, "height": 4320, "aspect": "4:3"},
            "streams": stream_inventory(ole),
            "record_count": len(records),
            "record_type_counts": {str(key): value for key, value in sorted(counts.items())},
            "slides": slides,
            "actions": actions,
            "hyperlinks": sorted(
                ({k: v for k, v in link.items() if not str(k).startswith("_")} for link in hyperlinks.values()),
                key=lambda item: int(item["id"]),
            ),
            "objects": objects,
            "text_runs": text_runs,
            "interactive_actions": interactive_actions,
            "navigation_edges": navigation_edges,
            "hyperlink_resolution": {
                "method": "docsum_slide_id",
                "slideIdMapSize": len(slide_id_to_order),
                "docsumDestinationCount": len(docsum_destinations),
                "exHyperlinkCount": len(hyperlinks_ordered),
                "staleFriendlyLabelCount": stale_label_count,
                "note": (
                    "ExHyperlink CString 'Slide N' is a stale friendly name. "
                    "Targets resolve via DocumentSummaryInformation "
                    "'slideId,N,Slide N' paired 1:1 with ExHyperlink order, "
                    "mapped through SlideListWithText slideId → presentation order."
                ),
            },
            "sounds": sounds,
            "embedded_assets": assets,
            "source_audio": source_audio,
        }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "inventory.json").write_text(
        json.dumps(inventory, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
    )
    return inventory


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Path to a PowerPoint 97-2003 .pps/.ppt")
    parser.add_argument(
        "--output", type=Path, default=Path("generated"), help="Output directory (default: generated)"
    )
    args = parser.parse_args()
    inventory = build_inventory(args.source, args.output)
    print(
        f"Extracted {len(inventory['slides'])} slides, "
        f"{len(inventory['actions'])} action records, and "
        f"{len(inventory['embedded_assets'])} image assets to {args.output}"
    )


if __name__ == "__main__":
    main()
