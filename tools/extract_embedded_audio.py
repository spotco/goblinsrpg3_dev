"""Extract embedded PowerPoint sound records as WAV files."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

import olefile

from extract_ppt import iter_records, record_payload


SOUND_CONTAINER = 2022
SOUND_DATA = 2023
UNICODE_STRING = 4026


def safe_stem(value: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-._")
    return stem or "embedded"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def decode_utf16(payload: bytes) -> str:
    return payload.decode("utf-16le", "replace").rstrip("\x00")


def extract_sound_container(payload: bytes) -> tuple[dict[str, object], bytes] | None:
    name = None
    extension = None
    sound_id = None
    wave_data = None
    for child in iter_records(payload):
        child_payload = record_payload(payload, child)
        if child["type"] == UNICODE_STRING:
            text = decode_utf16(child_payload)
            if child["instance"] == 0:
                name = text
            elif child["instance"] == 1:
                extension = text
            elif child["instance"] == 2:
                try:
                    sound_id = int(text)
                except ValueError:
                    sound_id = None
        elif child["type"] == SOUND_DATA:
            wave_data = child_payload
    if wave_data is None:
        return None
    metadata = {
        "name": name or "embedded",
        "extension": extension or ".WAV",
        "embeddedSoundId": sound_id,
        "bytes": len(wave_data),
        "sha256": sha256(wave_data),
    }
    return metadata, wave_data


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, default=Path("generated/embedded-audio"))
    args = parser.parse_args()

    args.output.mkdir(parents=True, exist_ok=True)
    entries = []
    with olefile.OleFileIO(args.source) as ole:
        ppt = ole.openstream("PowerPoint Document").read()
        index = 0
        for record in iter_records(ppt):
            if record["type"] != SOUND_CONTAINER:
                continue
            extracted = extract_sound_container(record_payload(ppt, record))
            if extracted is None:
                continue
            metadata, wave_data = extracted
            sound_id = metadata["embeddedSoundId"]
            id_part = f"{int(sound_id):03d}" if sound_id is not None else f"index-{index:03d}"
            output = args.output / f"sound-{id_part}-{safe_stem(Path(str(metadata['name'])).stem)}.wav"
            output.write_bytes(wave_data)
            entries.append(
                {
                    "index": index,
                    "sourceRecordOffset": record["offset"],
                    "path": output.as_posix(),
                    **metadata,
                }
            )
            index += 1

    manifest_path = args.output / "embedded_audio_manifest.json"
    manifest_path.write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"Wrote {manifest_path} with {len(entries)} embedded sounds")


if __name__ == "__main__":
    main()
