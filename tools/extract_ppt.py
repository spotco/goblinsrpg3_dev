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
            "sounds": sounds,
            "embedded_assets": assets,
            "source_audio": source_audio,
        }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "inventory.json").write_text(
        json.dumps(inventory, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
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
