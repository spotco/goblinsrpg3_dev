"""Offline estimate of animation timeline duration (mirrors docs/app.js heuristics)."""

from __future__ import annotations

from typing import Any


def node_parsed(node: dict[str, Any]) -> dict[str, Any]:
    time_node = node.get("timeNode") or {}
    parsed = time_node.get("parsed")
    return parsed if isinstance(parsed, dict) else {}


def node_delay(node: dict[str, Any]) -> float:
    delay = 0.0
    for condition in node.get("conditions") or []:
        parsed = condition.get("parsed") or {}
        if not isinstance(parsed, dict):
            continue
        # Skip start/end trigger conditions that chain other nodes (JS does this).
        if parsed.get("triggerObject") == 2 and parsed.get("triggerEvent") in (3, 4):
            continue
        delay_ms = parsed.get("delayMs")
        if isinstance(delay_ms, (int, float)) and delay_ms > delay:
            delay = float(delay_ms)
    return delay


def node_duration(node: dict[str, Any]) -> float:
    parsed = node_parsed(node)
    duration = parsed.get("durationMs")
    if not isinstance(duration, (int, float)) or duration <= 1:
        return 1.0
    return float(duration)


def node_runs_sequential_children(node: dict[str, Any]) -> bool:
    """Best-effort: match runtime when sequence data indicates sequential children."""
    sequence = node.get("sequence") or {}
    if isinstance(sequence, dict):
        parsed = sequence.get("parsed") or {}
        if isinstance(parsed, dict) and parsed.get("concurrent") is False:
            return True
        # Some extracts use nextAction / grouping
        if parsed.get("groupingType") in (1, "sequential"):
            return True
    parsed = node_parsed(node)
    # nodeType 1 often container; without explicit concurrent flag, prefer parallel max
    return False


def subtree_duration(node: dict[str, Any]) -> float:
    children = node.get("children") or []
    if not children:
        return node_delay(node) + node_duration(node)
    if node_runs_sequential_children(node):
        return node_delay(node) + node_duration(node) + sum(subtree_duration(c) for c in children)
    child_max = max(subtree_duration(c) for c in children)
    return node_delay(node) + max(node_duration(node), child_max)


def slide_animation_timeline(animation_slide: dict[str, Any] | None) -> dict[str, Any]:
    if not animation_slide:
        return {"available": False, "rootCount": 0, "durationMs": 0.0}
    roots = animation_slide.get("rootTimeNodes") or []
    durations = [subtree_duration(root) for root in roots]
    finite = [d for d in durations if isinstance(d, (int, float))]
    return {
        "available": True,
        "rootCount": len(roots),
        "durationMs": max(finite) if finite else 0.0,
    }


def count_on_next(animation_slide: dict[str, Any] | None) -> int:
    if not animation_slide:
        return 0
    count = 0
    stack = list(animation_slide.get("rootTimeNodes") or [])
    while stack:
        node = stack.pop()
        for condition in node.get("conditions") or []:
            parsed = condition.get("parsed") or {}
            if parsed.get("triggerEvent") in (9, 10):
                count += 1
        stack.extend(node.get("children") or [])
    return count


def inventory_behaviors(animation_slide: dict[str, Any] | None) -> dict[str, int]:
    counts: dict[str, int] = {}
    if not animation_slide:
        return counts
    stack = list(animation_slide.get("rootTimeNodes") or [])
    while stack:
        node = stack.pop()
        for behavior in node.get("behaviors") or []:
            kind = str(behavior.get("kind") or behavior.get("type") or "unknown")
            counts[kind] = counts.get(kind, 0) + 1
        stack.extend(node.get("children") or [])
    return counts
