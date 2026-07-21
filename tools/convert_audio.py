"""Convert source audio into browser-friendly assets.

WMA can be transcoded directly with ffmpeg. MIDI needs synthesis through a
soundfont or external synth before it becomes browser-playable audio, so this
tool records MIDI files as unresolved instead of producing a misleading file.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path


WMA_CONVERSIONS = (
    ("mp3", ("-c:a", "libmp3lame", "-b:a", "128k")),
    ("opus", ("-c:a", "libopus", "-b:a", "96k")),
)

WAV_CONVERSIONS = WMA_CONVERSIONS


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_ffmpeg(ffmpeg: str, source: Path, output: Path, codec_args: tuple[str, ...]) -> None:
    command = [
        ffmpeg,
        "-hide_banner",
        "-y",
        "-i",
        str(source),
        "-vn",
        *codec_args,
        str(output),
    ]
    subprocess.run(command, check=True)


def output_record(source: Path, output: Path, audio_type: str) -> dict[str, object]:
    return {
        "type": audio_type,
        "path": output.as_posix(),
        "bytes": output.stat().st_size,
        "sha256": sha256(output),
    }


def embedded_sound_id(source: Path) -> int | None:
    match = source.name.lower().split("-")
    if len(match) >= 2 and match[0] == "sound":
        try:
            return int(match[1])
        except ValueError:
            return None
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("generated/audio"))
    parser.add_argument(
        "--source",
        type=Path,
        action="append",
        dest="sources",
        default=None,
        help="Audio source to convert. Defaults to all root-level WMA/MID files.",
    )
    args = parser.parse_args()

    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise SystemExit("ffmpeg was not found on PATH")

    sources = args.sources
    if sources is None:
        sources = (
            sorted(Path(".").glob("*.wma"))
            + sorted(Path(".").glob("*.mid"))
            + sorted(Path("generated/embedded-audio").glob("*.wav"))
        )

    args.output.mkdir(parents=True, exist_ok=True)
    manifest: list[dict[str, object]] = []
    for source in sources:
        entry: dict[str, object] = {
            "source": source.as_posix(),
            "source_bytes": source.stat().st_size,
            "source_sha256": sha256(source),
            "outputs": [],
        }
        embedded_id = embedded_sound_id(source)
        if embedded_id is not None:
            entry["embeddedSoundId"] = embedded_id
        suffix = source.suffix.lower()
        if suffix == ".wma":
            for output_type, codec_args in WMA_CONVERSIONS:
                output = args.output / f"{source.stem}.{output_type}"
                run_ffmpeg(ffmpeg, source, output, codec_args)
                entry["outputs"].append(output_record(source, output, output_type))
            entry["status"] = "converted"
        elif suffix == ".wav":
            for output_type, codec_args in WAV_CONVERSIONS:
                output = args.output / f"{source.stem}.{output_type}"
                run_ffmpeg(ffmpeg, source, output, codec_args)
                entry["outputs"].append(output_record(source, output, output_type))
            entry["status"] = "converted"
        elif suffix in {".mid", ".midi"}:
            entry["status"] = "needs_midi_synthesis"
            entry["note"] = (
                "MIDI is a score, not sampled audio. Render it with a soundfont "
                "or synth, then add the rendered file to the web manifest."
            )
        else:
            entry["status"] = "unsupported_source_type"
        manifest.append(entry)

    manifest_path = args.output / "audio_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"Wrote {manifest_path} for {len(manifest)} source files")


if __name__ == "__main__":
    main()
