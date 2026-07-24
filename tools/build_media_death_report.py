"""Report media residuals + death/end terminals (PLAN Phase 2.7–2.9).

Writes generated/media_death_residuals.json.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    game = json.loads((ROOT / "docs" / "game-manifest.json").read_text(encoding="utf-8"))
    media_residuals = []
    for screen in game.get("screens") or []:
        slide = int(screen["slide"])
        for h in screen.get("hotspots") or []:
            status = h.get("behaviorStatus") or ""
            if status not in (
                "documented_unresolved_media",
                "documented_zero_area_media",
                "unresolved_media",
                "mapped_media_zero_area",
                "missing_media_binding",
            ):
                if h.get("residualStatus") not in (
                    "accepted_unresolved_media",
                    "accepted_zero_area_media",
                ):
                    continue
            media_residuals.append(
                {
                    "slide": slide,
                    "hotspotId": h.get("id"),
                    "shapeId": h.get("shapeId"),
                    "behaviorStatus": h.get("behaviorStatus"),
                    "mediaStatus": h.get("mediaStatus"),
                    "mediaBindingId": h.get("mediaBindingId"),
                    "residualStatus": h.get("residualStatus"),
                    "residualKind": h.get("residualKind"),
                    "clickable": bool(h.get("clickable")),
                    "resolveRationale": h.get("resolveRationale"),
                    "bounds": h.get("bounds"),
                }
            )

    terminals = []
    for screen in game.get("screens") or []:
        adv = screen.get("advancement") or {}
        if not adv.get("deathTerminal") and not adv.get("terminalKind"):
            continue
        texts = [L.get("text") for L in (screen.get("layers") or []) if L.get("text")]
        terminals.append(
            {
                "slide": int(screen["slide"]),
                "deathTerminal": bool(adv.get("deathTerminal")),
                "terminalKind": adv.get("terminalKind"),
                "terminalNotes": adv.get("terminalNotes"),
                "leavePaths": adv.get("leavePaths"),
                "texts": texts[:4],
                "hotspots": [
                    {
                        "action": h.get("action"),
                        "targetSlide": h.get("targetSlide"),
                        "behaviorStatus": h.get("behaviorStatus"),
                        "clickable": h.get("clickable"),
                    }
                    for h in screen.get("hotspots") or []
                ],
            }
        )

    bindings = game.get("mediaBindings") or []
    unresolved_bindings = [b for b in bindings if b.get("status") != "mapped"]

    report = {
        "format": "goblins-rpg3-media-death-residuals-v1",
        "summary": {
            "mediaResidualHotspotCount": len(media_residuals),
            "unresolvedBindingCount": len(unresolved_bindings),
            "terminalSlideCount": len(terminals),
            "unresolvedLegacyCueIds": sorted(
                {
                    b.get("legacyCueId")
                    for b in unresolved_bindings
                    if b.get("legacyCueId") is not None
                }
            ),
        },
        "mediaResidualHotspots": media_residuals,
        "unresolvedMediaBindings": unresolved_bindings,
        "terminalSlides": terminals,
        "policy": {
            "unresolvedMedia": "non-clickable; missing embedded cue ids; no invented audio",
            "zeroAreaMedia": "non-clickable; mapped audio may auto-play via timing",
            "death": "restart_only leave; optional media click",
            "end_card": "hyperlink and/or restart; terminalKind end_card",
        },
    }
    out = ROOT / "generated" / "media_death_residuals.json"
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"Wrote {out}")
    print(report["summary"])


if __name__ == "__main__":
    main()
