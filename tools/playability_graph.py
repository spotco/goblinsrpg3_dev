"""Shared post-resolve navigation graph helpers for offline playability tools."""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Any


def load_screens(game: dict[str, Any]) -> list[dict[str, Any]]:
    return list(game.get("screens") or [])


def screen_texts(screen: dict[str, Any]) -> list[str]:
    texts: list[str] = []
    for layer in screen.get("layers") or []:
        if layer.get("text"):
            texts.append(str(layer["text"]))
    for hotspot in screen.get("hotspots") or []:
        if hotspot.get("shapeText"):
            texts.append(str(hotspot["shapeText"]))
    return texts


def build_outbound(screens: list[dict[str, Any]]) -> dict[int, set[int]]:
    """Directed edges: hyperlinks + auto/stage sequential next."""
    out: dict[int, set[int]] = defaultdict(set)
    for screen in screens:
        slide = int(screen["slide"])
        adv = screen.get("advancement") or {}
        for hotspot in screen.get("hotspots") or []:
            if hotspot.get("action") == "hyperlink" and hotspot.get("targetSlide") is not None:
                out[slide].add(int(hotspot["targetSlide"]))
        if adv.get("autoAdvance") or adv.get("stageClickAdvancesSlide"):
            nxt = adv.get("nextSequentialSlide")
            if nxt is not None:
                out[slide].add(int(nxt))
    return out


def build_inbound(outbound: dict[int, set[int]]) -> dict[int, set[int]]:
    into: dict[int, set[int]] = defaultdict(set)
    for src, targets in outbound.items():
        for target in targets:
            into[target].add(src)
    return into


def bfs_reachable(outbound: dict[int, set[int]], start: int) -> set[int]:
    seen: set[int] = set()
    q: deque[int] = deque([start])
    while q:
        cur = q.popleft()
        if cur in seen:
            continue
        seen.add(cur)
        for target in outbound.get(cur, ()):
            if target not in seen:
                q.append(target)
    return seen


def edge_choices(
    screen: dict[str, Any],
    outbound: dict[int, set[int]],
) -> list[dict[str, Any]]:
    """Human-readable leave choices from one screen."""
    slide = int(screen["slide"])
    adv = screen.get("advancement") or {}
    choices: list[dict[str, Any]] = []
    seen_targets: set[tuple[str, int | None]] = set()

    for hotspot in screen.get("hotspots") or []:
        action = hotspot.get("action")
        if action == "hyperlink" and hotspot.get("targetSlide") is not None:
            target = int(hotspot["targetSlide"])
            key = ("hyperlink", target)
            if key in seen_targets:
                continue
            seen_targets.add(key)
            choices.append(
                {
                    "kind": "hyperlink",
                    "targetSlide": target,
                    "shapeText": hotspot.get("shapeText"),
                    "resolveMethod": hotspot.get("resolveMethod"),
                    "isSelf": target == slide,
                    "clickable": bool(hotspot.get("clickable")),
                }
            )
        elif action == "media" and hotspot.get("clickable"):
            choices.append(
                {
                    "kind": "media",
                    "targetSlide": None,
                    "behaviorStatus": hotspot.get("behaviorStatus"),
                    "clickable": True,
                }
            )

    if adv.get("autoAdvance") and adv.get("nextSequentialSlide") is not None:
        target = int(adv["nextSequentialSlide"])
        choices.append(
            {
                "kind": "auto_advance",
                "targetSlide": target,
                "delayMs": adv.get("autoAdvanceDelayMs"),
            }
        )
    if adv.get("stageClickAdvancesSlide") and adv.get("nextSequentialSlide") is not None:
        target = int(adv["nextSequentialSlide"])
        choices.append(
            {
                "kind": "stage_click",
                "targetSlide": target,
                "resolveMethod": adv.get("stageClickResolveMethod"),
            }
        )
    if adv.get("deathTerminal") or "restart_only" in (adv.get("leavePaths") or []):
        choices.append({"kind": "restart_only", "targetSlide": None})

    return choices


def classify_ending(screen: dict[str, Any], outbound: dict[int, set[int]]) -> str | None:
    slide = int(screen["slide"])
    adv = screen.get("advancement") or {}
    if adv.get("deathTerminal") or "restart_only" in (adv.get("leavePaths") or []):
        return "death_or_restart"
    targets = outbound.get(slide, set())
    if not targets and not adv.get("leavePaths"):
        return "stuck"
    if targets == {slide}:
        return "self_only"
    # Loop member if all outs stay in a small cycle detected by caller
    return None
