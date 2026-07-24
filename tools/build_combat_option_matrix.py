"""Build per-slide combat option → target matrix (PLAN Phase 2.3).

Writes generated/combat_option_matrix.json.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from advancement_lib import is_combat_like_text

ROOT = Path(__file__).resolve().parents[1]
COMBAT_SLIDE_HINT = re.compile(r"attack|flee|limit|magic|goblin|player takes", re.I)


def main() -> None:
    game = json.loads((ROOT / "docs" / "game-manifest.json").read_text(encoding="utf-8"))
    rows = []
    for screen in game.get("screens") or []:
        slide = int(screen["slide"])
        options = []
        for hotspot in screen.get("hotspots") or []:
            text = hotspot.get("shapeText") or hotspot.get("label") or ""
            if not is_combat_like_text(str(text)):
                continue
            target = hotspot.get("targetSlide")
            options.append(
                {
                    "shapeId": hotspot.get("shapeId"),
                    "text": text,
                    "action": hotspot.get("action"),
                    "targetSlide": target,
                    "isSelf": target is not None and int(target) == slide,
                    "resolveMethod": hotspot.get("resolveMethod"),
                    "clickable": bool(hotspot.get("clickable")),
                    "behaviorStatus": hotspot.get("behaviorStatus"),
                }
            )
        if not options:
            continue
        layer_texts = [L.get("text") for L in (screen.get("layers") or []) if L.get("text")]
        rows.append(
            {
                "slide": slide,
                "options": options,
                "optionCount": len(options),
                "selfCount": sum(1 for o in options if o["isSelf"]),
                "noopCount": sum(1 for o in options if o["action"] == "none"),
                "navCount": sum(
                    1
                    for o in options
                    if o["action"] == "hyperlink" and o["targetSlide"] and not o["isSelf"]
                ),
                "layerTexts": layer_texts[:5],
            }
        )

    report = {
        "format": "goblins-rpg3-combat-option-matrix-v1",
        "summary": {
            "combatSlideCount": len(rows),
            "totalOptions": sum(r["optionCount"] for r in rows),
            "selfOptions": sum(r["selfCount"] for r in rows),
            "noopOptions": sum(r["noopCount"] for r in rows),
            "navOptions": sum(r["navCount"] for r in rows),
        },
        "slides": rows,
    }
    out = ROOT / "generated" / "combat_option_matrix.json"
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"Wrote {out}")
    print(report["summary"])


if __name__ == "__main__":
    main()
