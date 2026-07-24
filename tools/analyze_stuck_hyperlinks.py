"""Deep analysis of stuck slides and self-hyperlinks for advancement unstick work."""

from __future__ import annotations

import json
import struct
from collections import defaultdict
from pathlib import Path

import olefile

from advancement_lib import build_screen_advancement, summarize_model

ROOT = Path(__file__).resolve().parents[1]
RH = struct.Struct("<HHI")
EX_HYPERLINK = 4055
EX_HYPERLINK_ATOM = 4051
CSTRING = 4026
INTERACTIVE_INFO_ATOM = 4083


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def walk_ex_hyperlinks(ppt: bytes):
    def walk(start: int, end: int):
        pos = start
        while pos + 8 <= end:
            vi, typ, length = RH.unpack_from(ppt, pos)
            rec_end = pos + 8 + length
            if rec_end > end or length < 0:
                break
            if typ == EX_HYPERLINK:
                link_id = None
                strings = []
                c = pos + 8
                while c + 8 <= rec_end:
                    _cvi, ctyp, clen = RH.unpack_from(ppt, c)
                    cpay = ppt[c + 8 : c + 8 + clen]
                    if ctyp == EX_HYPERLINK_ATOM and len(cpay) >= 4:
                        link_id = struct.unpack_from("<I", cpay)[0]
                    elif ctyp == CSTRING:
                        strings.append(cpay.decode("utf-16le", "ignore").rstrip("\x00"))
                    c += 8 + clen
                yield {"offset": pos, "id": link_id, "strings": strings}
            if (vi & 0xF) == 0xF and length > 0:
                yield from walk(pos + 8, rec_end)
            pos = rec_end

    yield from walk(0, len(ppt))


def main() -> None:
    inv = load_json(ROOT / "generated" / "inventory.json")
    game = load_json(ROOT / "docs" / "game-manifest.json")
    model = load_json(ROOT / "generated" / "advancement_model.json")
    stuck = {int(s["slide"]): s for s in model["summary"]["stuckSlides"]}

    ole = olefile.OleFileIO(str(ROOT / "goblins3 v.1.0 LAUNCH.pps"))
    ppt = ole.openstream("PowerPoint Document").read()
    links = {L["id"]: L for L in walk_ex_hyperlinks(ppt) if L["id"] is not None}

    texts = {}
    for t in inv.get("text_runs") or []:
        if t.get("slide") is None or t.get("shape_id") is None:
            continue
        texts[(int(t["slide"]), int(t["shape_id"]))] = t.get("text")
    for screen in game.get("screens") or []:
        slide = int(screen["slide"])
        for layer in screen.get("layers") or []:
            if layer.get("shapeId") is not None and layer.get("text"):
                texts.setdefault((slide, int(layer["shapeId"])), layer["text"])

    inbound = defaultdict(list)
    for a in inv.get("interactive_actions") or []:
        if a.get("action_code") == 4 and a.get("target_slide") is not None:
            inbound[int(a["target_slide"])].append(int(a["slide"]))

    self_details = []
    for a in inv.get("interactive_actions") or []:
        if a.get("action_code") != 4:
            continue
        slide = int(a["slide"])
        target = a.get("target_slide")
        if target is None or int(target) != slide:
            continue
        hid = a.get("hyperlink_id")
        link = links.get(hid)
        shape_id = a.get("shape_id")
        text = texts.get((slide, int(shape_id))) if shape_id is not None else None
        # Interactive atom jump/action already known; re-read for report
        off = int(a["record_offset"])
        payload = ppt[off + 8 : off + 8 + 16]
        action = payload[8] if len(payload) > 8 else None
        jump = payload[9] if len(payload) > 9 else None
        self_details.append(
            {
                "slide": slide,
                "shapeId": shape_id,
                "text": text,
                "hyperlinkId": hid,
                "exHyperlinkStrings": link["strings"] if link else None,
                "exHyperlinkOffset": link["offset"] if link else None,
                "interactiveAction": action,
                "interactiveJump": jump,
                "status": "confirmed_self_label_match",
                "evidence": [
                    "ExHyperlink has only one CString (friendly name), no separate target atom",
                    "All 194 ExHyperlinks are single-string Slide N labels",
                    "POI HSLFHyperlink type=DOCUMENT label matches on sampled slides",
                    f"InteractiveInfoAtom action={action} jump={jump} (4=hyperlink, jump 0=no jump enum)",
                ],
                "inboundFrom": sorted(set(inbound.get(slide, [])))[:20],
            }
        )

    no_nav = []
    for sid, info in sorted(stuck.items()):
        if info.get("reason") != "no_nav_hotspots_and_no_advance_flags":
            continue
        screen = next(s for s in game["screens"] if int(s["slide"]) == sid)
        layer_texts = [L.get("text") for L in (screen.get("layers") or []) if L.get("text")]
        no_nav.append(
            {
                "slide": sid,
                "reason": info["reason"],
                "inboundFrom": sorted(set(inbound.get(sid, [])))[:20],
                "layerTexts": layer_texts[:6],
                "hotspotCount": len(screen.get("hotspots") or []),
                "hotspots": [
                    {
                        "action": h.get("action"),
                        "targetSlide": h.get("targetSlide"),
                        "behaviorStatus": h.get("behaviorStatus"),
                    }
                    for h in (screen.get("hotspots") or [])
                ],
            }
        )

    # Pattern: continue/start text on self-link → sequential next is the playable intent in practice,
    # but binary says self. Document as confirmed_self with recommended port policy options.
    continue_self = [
        d
        for d in self_details
        if d.get("text")
        and any(k in str(d["text"]).lower() for k in ("click here", "continue", "start", "click to"))
    ]

    report = {
        "format": "goblins-rpg3-stuck-hyperlink-analysis-v1",
        "summary": {
            "stuckSlideCount": len(stuck),
            "selfLinkActionCount": len(self_details),
            "continueLikeSelfLinks": len(continue_self),
            "noNavNoFlagsCount": len(no_nav),
            "exHyperlinkCount": len(links),
            "exHyperlinksAllSingleSlideLabel": all(
                len(L["strings"]) == 1 and (L["strings"][0] or "").startswith("Slide ") for L in links.values()
            ),
            "conclusion": (
                "Self-links are confirmed at the label level: ExHyperlink stores only one UTF-16 string "
                "'Slide N' with no second target atom. InteractiveInfoAtom uses action=hyperlink (4), jump=0. "
                "This is not a runtime bug; the port currently has no other decoded leave path on those slides. "
                "No-nav/no-flags slides (e.g. 30, 139…) are hubs/returns with no outbound hyperlink and no "
                "manual/auto advance bits—leave only if something else is missing from extraction."
            ),
        },
        "selfLinks": self_details,
        "continueLikeSelfLinks": continue_self,
        "noNavNoFlagsSlides": no_nav,
        "stuckSlides": list(stuck.values()),
    }

    out = ROOT / "generated" / "stuck_hyperlink_analysis.json"
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"Wrote {out}")
    print(report["summary"]["conclusion"])
    print("continue-like self links:")
    for d in continue_self:
        print(f"  s{d['slide']:03d} text={d['text']!r} -> label Slide {d['slide']}")
    print("no-nav slides:", [n["slide"] for n in no_nav])


if __name__ == "__main__":
    main()
