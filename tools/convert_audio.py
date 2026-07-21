"""Convert source audio into browser-friendly assets.

WMA and extracted WAV files are transcoded directly with ffmpeg. MIDI files are
first rendered to sampled WAV with the repo-local deterministic synth in
``tools/render_midi.py`` and then transcoded to MP3/Opus.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

from render_midi import render_midi


WMA_CONVERSIONS = (
    ("mp3", ("-c:a", "libmp3lame", "-b:a", "128k")),
    ("opus", ("-c:a", "libopus", "-b:a", "96k")),
)

WAV_CONVERSIONS = WMA_CONVERSIONS
MIDI_CONVERSIONS = WMA_CONVERSIONS


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


def source_kind(source: Path) -> str:
    if source.suffix.lower() in {".mid", ".midi"}:
        return "linked_midi"
    if source.suffix.lower() == ".wma":
        return "linked_audio"
    if embedded_sound_id(source) is not None:
        return "embedded_powerpoint_sound"
    return "unknown"


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
            "sourceKind": source_kind(source),
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
            rendered_wav = args.output / f"{source.stem}.rendered.wav"
            synth_metadata = render_midi(source, rendered_wav)
            entry["midiRender"] = {
                **synth_metadata,
                "path": rendered_wav.as_posix(),
                "bytes": rendered_wav.stat().st_size,
                "sha256": sha256(rendered_wav),
            }
            for output_type, codec_args in MIDI_CONVERSIONS:
                output = args.output / f"{source.stem}.{output_type}"
                run_ffmpeg(ffmpeg, rendered_wav, output, codec_args)
                entry["outputs"].append(output_record(source, output, output_type))
            entry["status"] = "converted"
        else:
            entry["status"] = "unsupported_source_type"
        manifest.append(entry)

    manifest_path = args.output / "audio_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"Wrote {manifest_path} for {len(manifest)} source files")


if __name__ == "__main__":
    main()
