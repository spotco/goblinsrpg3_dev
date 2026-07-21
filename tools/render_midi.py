"""Render a Standard MIDI file to a sampled WAV file.

This is a deterministic fallback synth for the project.  It avoids a system
FluidSynth/Timidity dependency and does not require a soundfont, which keeps the
GitHub Pages build reproducible from the files in this repo.  It is intentionally
small: enough General MIDI semantics for the bundled victory fanfare, not a
replacement for a high-quality soundfont renderer.
"""

from __future__ import annotations

import argparse
import math
import struct
import wave
from dataclasses import dataclass
from pathlib import Path


DEFAULT_SAMPLE_RATE = 44_100
MAX_POLYPHONY = 96


@dataclass(frozen=True)
class MidiEvent:
    tick: int
    order: int
    kind: str
    channel: int = 0
    note: int = 0
    velocity: int = 0
    value: int = 0
    tempo: int = 500_000


@dataclass
class ActiveNote:
    note: int
    channel: int
    velocity: int
    start: float
    end: float | None = None
    program: int = 0
    volume: float = 1.0
    pan: float = 0.5


class MidiReader:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.offset = 0

    def read(self, size: int) -> bytes:
        chunk = self.data[self.offset : self.offset + size]
        if len(chunk) != size:
            raise ValueError("Unexpected end of MIDI data")
        self.offset += size
        return chunk

    def read_u16(self) -> int:
        return struct.unpack(">H", self.read(2))[0]

    def read_u32(self) -> int:
        return struct.unpack(">I", self.read(4))[0]

    def read_varlen(self) -> int:
        value = 0
        for _ in range(4):
            byte = self.read(1)[0]
            value = (value << 7) | (byte & 0x7F)
            if not byte & 0x80:
                return value
        return value


def parse_track(track_data: bytes, order_start: int) -> tuple[list[MidiEvent], int]:
    reader = MidiReader(track_data)
    tick = 0
    running_status: int | None = None
    order = order_start
    events: list[MidiEvent] = []
    while reader.offset < len(track_data):
        tick += reader.read_varlen()
        status_or_data = reader.read(1)[0]
        if status_or_data & 0x80:
            status = status_or_data
            if status < 0xF0:
                running_status = status
        else:
            if running_status is None:
                raise ValueError("MIDI running status used before status byte")
            status = running_status
            reader.offset -= 1

        if status == 0xFF:
            meta_type = reader.read(1)[0]
            length = reader.read_varlen()
            payload = reader.read(length)
            if meta_type == 0x51 and length == 3:
                tempo = int.from_bytes(payload, byteorder="big")
                events.append(MidiEvent(tick=tick, order=order, kind="tempo", tempo=tempo))
                order += 1
            elif meta_type == 0x2F:
                break
            continue
        if status in (0xF0, 0xF7):
            reader.read(reader.read_varlen())
            continue

        event_type = status & 0xF0
        channel = status & 0x0F
        if event_type in (0x80, 0x90):
            note = reader.read(1)[0]
            velocity = reader.read(1)[0]
            kind = "note_off" if event_type == 0x80 or velocity == 0 else "note_on"
            events.append(MidiEvent(tick=tick, order=order, kind=kind, channel=channel, note=note, velocity=velocity))
            order += 1
        elif event_type == 0xC0:
            events.append(MidiEvent(tick=tick, order=order, kind="program", channel=channel, value=reader.read(1)[0]))
            order += 1
        elif event_type == 0xB0:
            controller = reader.read(1)[0]
            value = reader.read(1)[0]
            if controller in (7, 10):
                kind = "volume" if controller == 7 else "pan"
                events.append(MidiEvent(tick=tick, order=order, kind=kind, channel=channel, value=value))
                order += 1
        elif event_type in (0xA0, 0xE0):
            reader.read(2)
        elif event_type == 0xD0:
            reader.read(1)
        else:
            raise ValueError(f"Unsupported MIDI status byte 0x{status:02x}")
    return events, order


def parse_midi(path: Path) -> tuple[int, list[MidiEvent]]:
    reader = MidiReader(path.read_bytes())
    if reader.read(4) != b"MThd":
        raise ValueError(f"{path} is not a Standard MIDI file")
    header_length = reader.read_u32()
    header = MidiReader(reader.read(header_length))
    midi_format = header.read_u16()
    track_count = header.read_u16()
    division = header.read_u16()
    if midi_format not in (0, 1):
        raise ValueError(f"Unsupported MIDI format {midi_format}")
    if division & 0x8000:
        raise ValueError("SMPTE-time MIDI files are not supported")
    events: list[MidiEvent] = []
    order = 0
    for _ in range(track_count):
        if reader.read(4) != b"MTrk":
            raise ValueError("Expected MTrk chunk")
        length = reader.read_u32()
        track_events, order = parse_track(reader.read(length), order)
        events.extend(track_events)
    return division, sorted(events, key=lambda event: (event.tick, event.order))


def event_seconds(events: list[MidiEvent], ticks_per_beat: int) -> dict[tuple[int, int], float]:
    tempo = 500_000
    last_tick = 0
    seconds = 0.0
    result: dict[tuple[int, int], float] = {}
    for event in events:
        seconds += ((event.tick - last_tick) * tempo) / (ticks_per_beat * 1_000_000)
        last_tick = event.tick
        result[(event.tick, event.order)] = seconds
        if event.kind == "tempo":
            tempo = event.tempo
    return result


def notes_from_events(events: list[MidiEvent], ticks_per_beat: int) -> list[ActiveNote]:
    seconds_by_event = event_seconds(events, ticks_per_beat)
    programs = [0] * 16
    volumes = [1.0] * 16
    pans = [0.5] * 16
    active: dict[tuple[int, int], list[ActiveNote]] = {}
    notes: list[ActiveNote] = []
    for event in events:
        seconds = seconds_by_event[(event.tick, event.order)]
        if event.kind == "program":
            programs[event.channel] = event.value
        elif event.kind == "volume":
            volumes[event.channel] = max(0.0, min(event.value / 127.0, 1.0))
        elif event.kind == "pan":
            pans[event.channel] = max(0.0, min(event.value / 127.0, 1.0))
        elif event.kind == "note_on":
            note = ActiveNote(
                note=event.note,
                channel=event.channel,
                velocity=event.velocity,
                start=seconds,
                program=programs[event.channel],
                volume=volumes[event.channel],
                pan=pans[event.channel],
            )
            active.setdefault((event.channel, event.note), []).append(note)
            notes.append(note)
        elif event.kind == "note_off":
            stack = active.get((event.channel, event.note), [])
            if stack:
                stack.pop().end = seconds

    final_time = max(seconds_by_event.values(), default=0.0)
    for stack in active.values():
        for note in stack:
            note.end = final_time
    return sorted(notes, key=lambda note: note.start)


def midi_frequency(note: int) -> float:
    return 440.0 * (2 ** ((note - 69) / 12))


def instrument_mix(program: int, phase: float) -> float:
    # Small deterministic timbre palette.  Trumpet/brass-like programs get more
    # harmonic content, which suits the bundled victory fanfare.
    if 56 <= program <= 63:
        return (
            math.sin(phase)
            + 0.38 * math.sin(phase * 2)
            + 0.18 * math.sin(phase * 3)
            + 0.08 * math.sin(phase * 5)
        ) / 1.64
    if 40 <= program <= 47:
        return (math.sin(phase) + 0.22 * math.sin(phase * 2) + 0.12 * math.sin(phase * 4)) / 1.34
    return (math.sin(phase) + 0.16 * math.sin(phase * 2)) / 1.16


def envelope(age: float, release_age: float | None, duration: float) -> float:
    attack = min(0.012, max(duration * 0.08, 0.002))
    decay = 0.08
    sustain = 0.72
    release = 0.16
    if release_age is not None:
        return max(0.0, 1.0 - (release_age / release)) * sustain
    if age < attack:
        return age / attack
    if age < attack + decay:
        return 1.0 - ((age - attack) / decay) * (1.0 - sustain)
    return sustain


def render_notes(notes: list[ActiveNote], output: Path, sample_rate: int = DEFAULT_SAMPLE_RATE) -> None:
    if not notes:
        raise ValueError("No MIDI notes were found")
    duration = max((note.end or note.start) for note in notes) + 0.35
    sample_count = int(math.ceil(duration * sample_rate))
    left = [0.0] * sample_count
    right = [0.0] * sample_count
    for note in notes[:MAX_POLYPHONY * 10]:
        start = int(note.start * sample_rate)
        note_end = note.end if note.end is not None else note.start + 0.2
        end = min(sample_count, int((note_end + 0.18) * sample_rate))
        frequency = midi_frequency(note.note)
        amplitude = (note.velocity / 127.0) * note.volume * 0.24
        pan = note.pan
        left_gain = math.cos(pan * math.pi / 2)
        right_gain = math.sin(pan * math.pi / 2)
        note_duration = max(note_end - note.start, 0.02)
        for sample_index in range(start, end):
            time = sample_index / sample_rate
            age = time - note.start
            release_age = None if time <= note_end else time - note_end
            env = envelope(age, release_age, note_duration)
            if env <= 0:
                continue
            phase = 2 * math.pi * frequency * age
            value = instrument_mix(note.program, phase) * amplitude * env
            left[sample_index] += value * left_gain
            right[sample_index] += value * right_gain

    peak = max(max(abs(value) for value in left), max(abs(value) for value in right), 1.0)
    scale = 0.92 / peak
    output.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output), "wb") as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        frames = bytearray()
        for l_value, r_value in zip(left, right):
            frames.extend(struct.pack("<hh", int(l_value * scale * 32767), int(r_value * scale * 32767)))
        wav.writeframes(frames)


def render_midi(source: Path, output: Path, sample_rate: int = DEFAULT_SAMPLE_RATE) -> dict[str, object]:
    ticks_per_beat, events = parse_midi(source)
    notes = notes_from_events(events, ticks_per_beat)
    render_notes(notes, output, sample_rate=sample_rate)
    return {
        "synth": "goblins-python-additive-v1",
        "sampleRate": sample_rate,
        "ticksPerBeat": ticks_per_beat,
        "eventCount": len(events),
        "noteCount": len(notes),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--sample-rate", type=int, default=DEFAULT_SAMPLE_RATE)
    args = parser.parse_args()
    metadata = render_midi(args.source, args.output, args.sample_rate)
    print(f"Wrote {args.output} with {metadata['noteCount']} MIDI notes")


if __name__ == "__main__":
    main()
