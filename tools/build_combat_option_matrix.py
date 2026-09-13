"""Build per-slide combat option → target matrix (PLAN Phase 2.3).

Writes generated/combat_option_matrix.json.

v2 adds DocSummary vs pptx debug-lens targets, outcome captions, and
Limit-menu bookkeeping. Web targets must equal pps DocSum (oracle) and
the converted pptx hyperlinks (debug lens). No invent-bridges.
"""

from __future__ import annotations

import json
import re
import zipfile
from collections import defaultdict
from pathlib import Path
from xml.etree import ElementTree as ET

from advancement_lib import is_combat_like_text

ROOT = Path(__file__).resolve().parents[1]
PPTX = ROOT / "source" / "goblins3_v.1.0_launch-pptx.pptx"
OPTION_RE = re.compile(r"^\s*-?\s*(attack|flee|limit|magic)\s*$", re.I)
CAPTION_RE = re.compile(
    r"attack|flee|limit|magic|felled|escape|charge|ded|damage|hp|fury|"
    r"boredom|can't|cannot|run|ow|win|infinity|pity|slug|commander",
    re.I,
)
A_HLINK = "{http://schemas.openxmlformats.org/drawingml/2006/main}hlinkClick"
R_ID = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
A_T = "{http://schemas.openxmlformats.org/drawingml/2006/main}t"
P_SP = "{http://schemas.openxmlformats.org/presentationml/2006/main}sp"


def option_kind(text: str | None) -> str | None:
    match = OPTION_RE.match(str(text or ""))
    return match.group(1).lower() if match else None


def outcome_caption(screens_by_slide: dict[int, dict], slide: int | None) -> str | None:
    if slide is None:
        return None
    screen = screens_by_slide.get(int(slide))
    if not screen:
        return None
    texts = [str(layer.get("text")) for layer in (screen.get("layers") or []) if layer.get("text")]
    good = [text for text in texts if not OPTION_RE.match(text) and CAPTION_RE.search(text)]
    if good:
        return " | ".join(good[:3])
    return " | ".join(texts[:3]) if texts else ""


def outcome_next(screens_by_slide: dict[int, dict], slide: int | None) -> list[dict]:
    if slide is None:
        return []
    screen = screens_by_slide.get(int(slide)) or {}
    adv = screen.get("advancement") or {}
    leaves: list[dict] = []
    if adv.get("autoAdvance"):
        leaves.append(
            {
                "kind": "auto_advance",
                "targetSlide": adv.get("nextSequentialSlide"),
                "delayMs": adv.get("autoAdvanceDelayMs"),
            }
        )
    for hotspot in screen.get("hotspots") or []:
        if hotspot.get("clickable") and hotspot.get("targetSlide"):
            leaves.append(
                {
                    "kind": "hyperlink",
                    "text": hotspot.get("shapeText") or hotspot.get("label"),
                    "targetSlide": hotspot.get("targetSlide"),
                    "resolveMethod": hotspot.get("resolveMethod"),
                }
            )
    return leaves[:6]


def load_pptx_option_targets() -> dict[int, dict[str, list[int]]]:
    """pptx file number == presentation order for this deck (201 slides)."""
    by_slide: dict[int, dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
    if not PPTX.exists():
        return {}
    with zipfile.ZipFile(PPTX) as archive:
        for order in range(1, 202):
            xml_name = f"ppt/slides/slide{order}.xml"
            rels_name = f"ppt/slides/_rels/slide{order}.xml.rels"
            if xml_name not in archive.namelist():
                continue
            rels: dict[str, str] = {}
            if rels_name in archive.namelist():
                rel_root = ET.fromstring(archive.read(rels_name))
                for rel in rel_root:
                    rid = rel.attrib.get("Id")
                    target = rel.attrib.get("Target") or ""
                    if rid:
                        rels[rid] = target
            root = ET.fromstring(archive.read(xml_name))
            for shape in root.findall(f".//{P_SP}"):
                texts = [node.text or "" for node in shape.findall(f".//{A_T}")]
                text = "".join(texts).strip()
                kind = option_kind(text)
                if not kind:
                    continue
                dests: list[int] = []
                for hlink in shape.findall(f".//{A_HLINK}"):
                    rid = hlink.attrib.get(R_ID)
                    target = rels.get(rid or "", "")
                    match = re.search(r"slide(\d+)\.xml", target)
                    if match:
                        dests.append(int(match.group(1)))
                if dests:
                    by_slide[order][kind].extend(dests)
    return {slide: dict(kinds) for slide, kinds in by_slide.items()}


def load_inventory_option_targets(inventory: dict) -> dict[int, dict[str, list[int]]]:
    text_by: dict[tuple[int | None, int | None], list[str]] = defaultdict(list)
    for run in inventory.get("text_runs") or []:
        text_by[(run.get("slide"), run.get("shape_id"))].append(str(run.get("text") or ""))
    by_slide: dict[int, dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
    for action in inventory.get("interactive_actions") or []:
        slide = action.get("slide")
        texts = text_by.get((slide, action.get("shape_id")), [])
        kind = None
        for text in texts:
            kind = option_kind((text or "").split("\n")[0])
            if kind:
                break
        if not kind or action.get("target_slide") is None:
            continue
        by_slide[int(slide)][kind].append(int(action["target_slide"]))
    return {slide: dict(kinds) for slide, kinds in by_slide.items()}


def main() -> None:
    game = json.loads((ROOT / "docs" / "game-manifest.json").read_text(encoding="utf-8"))
    inventory = json.loads((ROOT / "generated" / "inventory.json").read_text(encoding="utf-8"))
    screens_by_slide = {int(screen["slide"]): screen for screen in game.get("screens") or []}
    pptx_by_slide = load_pptx_option_targets()
    inv_by_slide = load_inventory_option_targets(inventory)

    rows = []
    mismatches: list[dict] = []
    limit_rows: list[dict] = []
    for screen in game.get("screens") or []:
        slide = int(screen["slide"])
        options = []
        for hotspot in screen.get("hotspots") or []:
            text = hotspot.get("shapeText") or hotspot.get("label") or ""
            if not is_combat_like_text(str(text)):
                continue
            if not hotspot.get("clickable"):
                # leftover same-shape action=none stays in hotspot list but is
                # not a playable option (explicit_noop).
                if hotspot.get("action") == "none":
                    continue
            target = hotspot.get("targetSlide")
            kind = option_kind(str(text))
            inv_targets = sorted(set((inv_by_slide.get(slide) or {}).get(kind or "", [])))
            pptx_targets = sorted(set((pptx_by_slide.get(slide) or {}).get(kind or "", [])))
            web_targets = [int(target)] if target is not None else []
            caption = outcome_caption(screens_by_slide, target)
            flags: list[str] = []
            if web_targets != inv_targets:
                flags.append("web_ne_docsum")
            if pptx_targets and web_targets != pptx_targets:
                flags.append("web_ne_pptx")
            option = {
                "kind": kind,
                "shapeId": hotspot.get("shapeId"),
                "text": text,
                "action": hotspot.get("action"),
                "targetSlide": target,
                "docsumTarget": inv_targets[0] if len(inv_targets) == 1 else inv_targets,
                "pptxTarget": pptx_targets[0] if len(pptx_targets) == 1 else pptx_targets,
                "outcomeCaption": caption,
                "outcomeNext": outcome_next(screens_by_slide, target),
                "isSelf": target is not None and int(target) == slide,
                "resolveMethod": hotspot.get("resolveMethod"),
                "clickable": bool(hotspot.get("clickable")),
                "behaviorStatus": hotspot.get("behaviorStatus"),
                "flags": flags,
            }
            options.append(option)
            if flags:
                mismatches.append({"slide": slide, **option})
            if kind == "limit":
                limit_rows.append({"slide": slide, **option})
        if not options:
            continue
        layer_texts = [layer.get("text") for layer in (screen.get("layers") or []) if layer.get("text")]
        rows.append(
            {
                "slide": slide,
                "options": options,
                "optionCount": len(options),
                "selfCount": sum(1 for option in options if option["isSelf"]),
                "noopCount": sum(1 for option in options if option["action"] == "none"),
                "navCount": sum(
                    1
                    for option in options
                    if option["action"] == "hyperlink" and option["targetSlide"] and not option["isSelf"]
                ),
                "layerTexts": layer_texts[:6],
            }
        )

    report = {
        "format": "goblins-rpg3-combat-option-matrix-v2",
        "policy": (
            "pps DocSummary slideId is oracle; pptx is debug lens; "
            "no USER_AUTHORIZED_TARGET_OVERRIDES; no invent-bridges"
        ),
        "pptxDebugLens": str(PPTX.relative_to(ROOT)),
        "summary": {
            "combatSlideCount": len(rows),
            "totalOptions": sum(row["optionCount"] for row in rows),
            "selfOptions": sum(row["selfCount"] for row in rows),
            "noopOptions": sum(row["noopCount"] for row in rows),
            "navOptions": sum(row["navCount"] for row in rows),
            "limitMenuCount": len(limit_rows),
            "mismatchCount": len(mismatches),
        },
        "limitMenus": [
            {
                "slide": row["slide"],
                "targetSlide": row["targetSlide"],
                "outcomeCaption": row["outcomeCaption"],
                "pptxTarget": row["pptxTarget"],
                "docsumTarget": row["docsumTarget"],
                "resolveMethod": row["resolveMethod"],
            }
            for row in limit_rows
        ],
        "mismatches": mismatches,
        "slides": rows,
    }
    out = ROOT / "generated" / "combat_option_matrix.json"
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"Wrote {out}")
    print(report["summary"])
    if mismatches:
        print("MISMATCHES:")
        for row in mismatches:
            print(
                f"  s{row['slide']} {row.get('kind')} web={row.get('targetSlide')} "
                f"docsum={row.get('docsumTarget')} pptx={row.get('pptxTarget')}"
            )


if __name__ == "__main__":
    main()
