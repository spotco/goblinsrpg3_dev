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
