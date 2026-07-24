"""Parse and sample PowerPoint motion-path strings (VML-like M/L/C).

Used offline for Phase 5.4 inventory and to mirror docs/app.js sampling.
Coordinates are PPT fraction units (same as runtime: *100 cqw/cqh).
"""

from __future__ import annotations

import re
from typing import Any

TOKEN_RE = re.compile(
    r"([MLCZmlcz])|([+\-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+\-]?\d+)?)"
)


def tokenize_motion_path(path: str) -> list[str]:
    if not isinstance(path, str):
        return []
    return [m.group(0) for m in TOKEN_RE.finditer(path.strip())]


def parse_motion_path(path: str) -> dict[str, Any] | None:
    tokens = tokenize_motion_path(path)
    if not tokens or tokens[0].upper() != "M":
        return None
    index = 0
    segments: list[dict[str, Any]] = []
    start: dict[str, float] | None = None
    current = {"x": 0.0, "y": 0.0}
    commands: list[str] = []

    def read_number() -> float | None:
        nonlocal index
        if index >= len(tokens):
            return None
        try:
            value = float(tokens[index])
        except ValueError:
            return None
        index += 1
        return value

    def read_point() -> dict[str, float] | None:
        x = read_number()
        y = read_number()
        if x is None or y is None:
            return None
        return {"x": x, "y": y}

    while index < len(tokens):
        token = tokens[index]
        if not token.isalpha():
            # Implicit command continuation is rare; stop cleanly.
            break
        cmd = token.upper()
        index += 1
        commands.append(cmd)
        if cmd == "M":
            point = read_point()
            if not point:
                return None
            current = point
            if start is None:
                start = dict(point)
            # Subsequent pairs after M are treated as L in SVG; PPT paths use explicit L.
            while index < len(tokens) and not tokens[index].isalpha():
                nxt = read_point()
                if not nxt:
                    break
                segments.append({"cmd": "L", "from": dict(current), "to": dict(nxt)})
                current = nxt
        elif cmd == "L":
            while index < len(tokens) and not tokens[index].isalpha():
                nxt = read_point()
                if not nxt:
                    break
                segments.append({"cmd": "L", "from": dict(current), "to": dict(nxt)})
                current = nxt
        elif cmd == "C":
            while index < len(tokens) and not tokens[index].isalpha():
                c1 = read_point()
                c2 = read_point()
                end = read_point()
                if not c1 or not c2 or not end:
                    break
                segments.append(
                    {
                        "cmd": "C",
                        "from": dict(current),
                        "c1": c1,
                        "c2": c2,
                        "to": dict(end),
                    }
                )
                current = end
        elif cmd == "Z":
            if start is not None:
                segments.append({"cmd": "L", "from": dict(current), "to": dict(start)})
                current = dict(start)
        else:
            # Unsupported command — leave residual.
            break

    if start is None:
        return None
    cmd_key = "".join(commands)
    kind = "line"
    if "C" in commands:
        kind = "cubic"
    elif cmd_key not in ("M", "ML") and commands.count("L") > 1:
        kind = "polyline"
    elif cmd_key == "ML" or (len(commands) == 2 and commands[0] == "M" and commands[1] == "L"):
        kind = "line"
    elif len(segments) > 1:
        kind = "polyline"

    return {
        "start": start,
        "end": dict(current),
        "segments": segments,
        "commands": commands,
        "commandKey": cmd_key,
        "kind": kind,
        "segmentCount": len(segments),
    }


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _point_on_line(p0: dict[str, float], p1: dict[str, float], t: float) -> dict[str, float]:
    return {"x": _lerp(p0["x"], p1["x"], t), "y": _lerp(p0["y"], p1["y"], t)}


def _point_on_cubic(
    p0: dict[str, float],
    p1: dict[str, float],
    p2: dict[str, float],
    p3: dict[str, float],
    t: float,
) -> dict[str, float]:
    u = 1.0 - t
    uu = u * u
    tt = t * t
    uuu = uu * u
    ttt = tt * t
    return {
        "x": uuu * p0["x"] + 3 * uu * t * p1["x"] + 3 * u * tt * p2["x"] + ttt * p3["x"],
        "y": uuu * p0["y"] + 3 * uu * t * p1["y"] + 3 * u * tt * p2["y"] + ttt * p3["y"],
    }


def _distance(a: dict[str, float], b: dict[str, float]) -> float:
    dx = b["x"] - a["x"]
    dy = b["y"] - a["y"]
    return (dx * dx + dy * dy) ** 0.5


def densify_path(parsed: dict[str, Any], steps_per_cubic: int = 16) -> list[dict[str, float]]:
    points: list[dict[str, float]] = [dict(parsed["start"])]
    for segment in parsed.get("segments") or []:
        if segment["cmd"] == "L":
            points.append(dict(segment["to"]))
        elif segment["cmd"] == "C":
            for step in range(1, steps_per_cubic + 1):
                t = step / steps_per_cubic
                points.append(
                    _point_on_cubic(
                        segment["from"],
                        segment["c1"],
                        segment["c2"],
                        segment["to"],
                        t,
                    )
                )
    return points


def sample_motion_path(
    path: str,
    sample_count: int = 48,
    steps_per_cubic: int = 16,
) -> dict[str, Any] | None:
    parsed = parse_motion_path(path)
    if not parsed:
        return None
    dense = densify_path(parsed, steps_per_cubic=steps_per_cubic)
    if len(dense) == 1:
        samples = [dict(dense[0])]
    else:
        # Arc-length parameterization.
        lengths = [0.0]
        for index in range(1, len(dense)):
            lengths.append(lengths[-1] + _distance(dense[index - 1], dense[index]))
        total = lengths[-1]
        count = max(2, int(sample_count))
        samples: list[dict[str, float]] = []
        if total <= 1e-12:
            samples = [dict(dense[0]), dict(dense[-1])]
        else:
            targets = [total * i / (count - 1) for i in range(count)]
            cursor = 0
            for target in targets:
                while cursor < len(lengths) - 1 and lengths[cursor + 1] < target:
                    cursor += 1
                if cursor >= len(lengths) - 1:
                    samples.append(dict(dense[-1]))
                    continue
                span = lengths[cursor + 1] - lengths[cursor]
                t = 0.0 if span <= 1e-12 else (target - lengths[cursor]) / span
                samples.append(_point_on_line(dense[cursor], dense[cursor + 1], t))

    endpoint = dict(parsed["end"])
    # Ensure final sample lands on true endpoint.
    samples[-1] = endpoint
    mid = samples[len(samples) // 2]
    return {
        "parsed": {
            "kind": parsed["kind"],
            "commandKey": parsed["commandKey"],
            "segmentCount": parsed["segmentCount"],
            "start": parsed["start"],
            "end": endpoint,
        },
        "samples": samples,
        "sampleCount": len(samples),
        "endpoint": endpoint,
        "midpoint": mid,
        "pathLengthEstimate": sum(
            _distance(samples[i], samples[i + 1]) for i in range(len(samples) - 1)
        ),
    }


def motion_endpoint(path: str) -> dict[str, float] | None:
    parsed = parse_motion_path(path)
    if not parsed:
        return None
    return dict(parsed["end"])


def classify_path(path: str) -> str:
    parsed = parse_motion_path(path)
    if not parsed:
        return "invalid"
    return str(parsed["kind"])
