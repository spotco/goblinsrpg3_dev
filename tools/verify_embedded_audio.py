"""Regression checks for extracted and converted embedded PowerPoint sounds."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--embedded", type=Path, default=Path("generated/embedded-audio/embedded_audio_manifest.json"))
    parser.add_argument("--audio", type=Path, default=Path("generated/audio/audio_manifest.json"))
    args = parser.parse_args()

    embedded = json.loads(args.embedded.read_text(encoding="utf-8"))
    audio = json.loads(args.audio.read_text(encoding="utf-8"))
    assert len(embedded) == 5
    assert [item["embeddedSoundId"] for item in embedded] == [1, 2, 5, 7, 8]
    for item in embedded:
        path = Path(item["path"])
        assert path.exists(), path
        assert path.stat().st_size == item["bytes"], path
        assert path.read_bytes().startswith(b"RIFF"), path

    converted_embedded = [item for item in audio if item.get("embeddedSoundId") is not None]
    assert len(audio) == 8
    assert len(converted_embedded) == 5
    midi_entries = [item for item in audio if item["source"].endswith(".mid")]
    assert len(midi_entries) == 1
    midi_entry = midi_entries[0]
    assert midi_entry["status"] == "converted"
    assert midi_entry["midiRender"]["synth"] == "goblins-python-additive-v1"
    rendered_wav = Path(midi_entry["midiRender"]["path"])
    assert rendered_wav.exists(), rendered_wav
    assert rendered_wav.stat().st_size == midi_entry["midiRender"]["bytes"], rendered_wav
    assert len(midi_entry["outputs"]) == 2
    for output in midi_entry["outputs"]:
        path = Path(output["path"])
        assert path.exists(), path
        assert path.stat().st_size == output["bytes"], path
    assert [item["embeddedSoundId"] for item in converted_embedded] == [1, 2, 5, 7, 8]
    for item in converted_embedded:
        assert item["status"] == "converted"
        assert len(item["outputs"]) == 2
        for output in item["outputs"]:
            path = Path(output["path"])
            assert path.exists(), path
            assert path.stat().st_size == output["bytes"], path
    print("embedded audio verification passed")


if __name__ == "__main__":
    main()
