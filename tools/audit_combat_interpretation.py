#!/usr/bin/env python3
"""Deep combat-graph interpretation audit (no remaps / no invent-bridges).

Re-reads SSSlideInfoAtom, ExHyperlink (friendly-only), InteractiveInfo parents,
animation targets, and asset-013 goblin counts for the first-goblin fight.
Writes generated/combat_interpretation_audit.json with remembered-vs-binary
conflicts and the smallest remaining *interpretation* experiments.
"""
from __future__ import annotations

import json
import struct
from pathlib import Path

import olefile

from extract_ppt import RECORD_HEADER, iter_records_with_context

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "goblins3 v.1.0 LAUNCH.pps"
OUT = ROOT / "generated" / "combat_interpretation_audit.json"

EX_HYPERLINK = 4055
EX_HYPERLINK_ATOM = 4051
CSTRING = 4026
INTERACTIVE_INFO_ATOM = 4083
INTERACTIVE_INFO = 4082

TRANSITION_EFFECT = {
    0: "cut",
    1: "random",
    2: "blinds",
    3: "checker",
    4: "cover",
    5: "dissolve",
    6: "fade",
    7: "uncover",
    8: "randomBars",
    9: "strips",
    10: "wipe",
    11: "box",
    13: "split",
    17: "diamond",
    18: "plus",
    19: "wedge",
    20: "push",
    21: "comb",
    22: "newsflash",
    23: "alphafade",
    26: "wheel",
    27: "circle",
    255: "undefined",
}


def load(name: str):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def standing_goblins(layers, slide: int) -> int:
    s = next(x for x in layers["slides"] if x["slide"] == slide)
    return sum(1 for L in s["layers"] if L.get("assetId") == "asset-013")


def texts(layers, slide: int) -> list:
    s = next(x for x in layers["slides"] if x["slide"] == slide)
    return [L.get("text") for L in s["layers"] if L.get("text")]


def hotspots(adv, slide: int) -> list:
    s = next(x for x in adv["slides"] if x["slide"] == slide)
    return [
        {
            "shapeId": h.get("shapeId"),
            "shapeText": h.get("shapeText"),
            "targetSlide": h.get("targetSlide"),
            "targetLabel": h.get("targetLabel"),
            "hyperlinkId": h.get("hyperlinkId"),
            "actionCode": h.get("actionCode"),
            "clickable": h.get("clickable"),
            "resolveMethod": h.get("resolveMethod"),
            "behaviorStatus": h.get("behaviorStatus"),
            "flagsHex": h.get("flagsHex"),
        }
        for h in s.get("hotspots") or []
    ]


def transition(timing, slide: int) -> dict:
    t = next(x for x in timing["transitions"] if x["slide"] == slide)
    return {
        "slideTimeMs": t["slideTimeMs"],
        "effectType": t["effectType"],
        "effectName": TRANSITION_EFFECT.get(t["effectType"], f"unknown:{t['effectType']}"),
        "effectDirection": t["effectDirection"],
        "flags": t["flags"],
        "flagNames": t["flagNames"],
        "rawHex": t["rawHex"],
        "autoAdvanceBit": "autoAdvance" in (t["flagNames"] or []),
    }


def anim_targets(am, slide: int) -> list:
    s = next((x for x in am["slides"] if x["slide"] == slide), None)
    if not s:
        return []
    out = []

    def walk(n):
        for t in n.get("targets") or []:
            out.append(
                {
                    "node": n["id"],
                    "shapeId": t.get("shapeId"),
                    "kinds": [b.get("kind") for b in (n.get("behaviors") or [])],
                }
            )
        for ch in n.get("children") or []:
            walk(ch)
        for se in n.get("subEffects") or []:
            walk(se)

    for r in s.get("rootTimeNodes") or []:
        walk(r)
    return out


def build_edges(adv) -> list:
    edges = []
    for s in adv["slides"]:
        a = s["advancement"]
        if a.get("autoAdvance") and a.get("nextSequentialSlide"):
            edges.append(
                {"from": s["slide"], "to": a["nextSequentialSlide"], "via": "autoAdvance"}
            )
        for h in s.get("hotspots") or []:
            if h.get("targetSlide") is not None:
                edges.append(
                    {
                        "from": s["slide"],
                        "to": h["targetSlide"],
                        "via": h.get("shapeText") or h.get("action"),
                        "shapeId": h.get("shapeId"),
                    }
                )
    return edges


def main() -> None:
    inv = load("generated/inventory.json")
    layers = load("generated/layers.json")
    adv = load("generated/advancement_model.json")
    am = load("docs/animation-manifest.json")
    timing = load("generated/timing_manifest.json")
    edges = build_edges(adv)

    def inbound(n: int):
        return [e for e in edges if e["to"] == n]

    with olefile.OleFileIO(SOURCE) as ole:
        ppt = ole.openstream("PowerPoint Document").read()

    ex_meta = {}
    for event in iter_records_with_context(ppt):
        if event["type"] != EX_HYPERLINK:
            continue
        ps = event["offset"] + RECORD_HEADER.size
        pe = ps + event["length"]
        lid = None
        cstrs = []
        child = ps
        while child + RECORD_HEADER.size <= pe:
            vi, ct, cl = RECORD_HEADER.unpack_from(ppt, child)
            inst = vi >> 4
            cp = ppt[child + RECORD_HEADER.size : child + RECORD_HEADER.size + cl]
            if ct == EX_HYPERLINK_ATOM and len(cp) >= 4:
                lid = struct.unpack_from("<I", cp)[0]
            elif ct == CSTRING:
                cstrs.append({"instance": inst, "text": cp.decode("utf-16le", "ignore")})
            child += RECORD_HEADER.size + cl
        if lid is not None:
            ex_meta[lid] = {"cstringCount": len(cstrs), "cstrings": cstrs}

    recs = list(iter_records_with_context(ppt))
    ii_parents = []
    for i, e in enumerate(recs):
        if e["type"] != INTERACTIVE_INFO_ATOM or e.get("slide_order") not in range(15, 25):
            continue
        parent = None
        for j in range(i - 1, max(-1, i - 30), -1):
            if recs[j]["type"] == INTERACTIVE_INFO and recs[j].get("depth", 99) < e.get(
                "depth", 0
            ):
                pvi = struct.unpack_from("<H", ppt, recs[j]["offset"])[0]
                inst = pvi >> 4
                parent = {
                    "instance": inst,
                    "meaning": "mouseClick" if inst == 0 else "mouseOver",
                }
                break
        ii_parents.append(
            {"slide": e["slide_order"], "shapeId": e.get("shape_id"), "parent": parent}
        )

    has_slide23 = b"S\x00l\x00i\x00d\x00e\x00 \x002\x003\x00" in ppt
    sample_ids = (46, 62, 67, 68, 77, 92, 146, 191)

    remembered = {
        "boredom": "passive anim on ×3, NOT killing / not leaving to lower count",
        "attack": "attack anim → goblin counter → menu with one fewer goblin",
        "flee": "always fail → their counterattack, same goblin count",
    }

    binary = {
        "s015": {
            "standingGoblinsAsset013": standing_goblins(layers, 15),
            "texts": texts(layers, 15),
            "transition": transition(timing, 15),
            "hotspots": hotspots(adv, 15),
            "animationTargets": anim_targets(am, 15),
            "legacyAnimationInfo": [a for a in timing["animations"] if a["slide"] == 15],
            "notes": [
                "autoAdvance bit 0x0400 confirmed in SSSlideInfoAtom rawHex; effectType 22=newsflash (visual only)",
                "I'm bored… is ExtTimeNode dissolve on shape 17427 (delay 3500ms) — on-slide only; no goblin hide",
                "autoAdvance 9000ms → s016 is separate from the boredom dissolve",
            ],
        },
        "s016": {
            "standingGoblinsAsset013": standing_goblins(layers, 16),
            "texts": texts(layers, 16),
            "transition": transition(timing, 16),
            "hotspots": hotspots(adv, 16),
            "notes": [
                "slideTimeMs=9000 but flags=0 (NO autoAdvance)",
                "text authored: Goblin fled of boredom…",
            ],
        },
        "s017": {
            "texts": texts(layers, 17),
            "transition": transition(timing, 17),
            "hotspots": hotspots(adv, 17),
            "inbound": inbound(17),
            "notes": [
                "Continue ExHyperlink id 77 label only Slide 22; no auto/chained nav after anim"
            ],
        },
        "s018": {
            "texts": texts(layers, 18),
            "hotspots": hotspots(adv, 18),
            "inbound": inbound(18),
            "animationTargets": anim_targets(am, 18),
            "standingGoblinsAsset013": standing_goblins(layers, 18),
            "notes": [
                "Only inbound is s015 Attack",
                "Caption CAN'T ESCAPE!! but carries motion paths; Continue→24 still ×3",
                "Not a kill ladder; HP drops 25→10 on s024 without goblin count drop",
            ],
        },
        "s019": {
            "texts": texts(layers, 19),
            "hotspots": hotspots(adv, 19),
            "inbound": inbound(19),
            "notes": [
                "Felled kill from s021 Attack only; Continue→24 (×3) — count does not drop"
            ],
        },
        "s021": {
            "standingGoblinsAsset013": standing_goblins(layers, 21),
            "hotspots": hotspots(adv, 21),
        },
        "s022": {
            "standingGoblinsAsset013": standing_goblins(layers, 22),
            "texts": texts(layers, 22),
            "hotspots": hotspots(adv, 22),
            "inbound": inbound(22),
            "notes": [
                "Exactly 1× asset-013 in layers + reconstructed art; Continue 17→22 drops ×2→×1"
            ],
        },
        "s023_orphan": {
            "texts": texts(layers, 23),
            "inbound": inbound(23),
            "hasExHyperlinkLabelSlide23InBinary": has_slide23,
            "notes": [
                "Goblin x3 Attacks! / 15 damage Continue→24",
                'ZERO inbound edges; string "Slide 23" absent from PowerPoint Document stream',
                "Cannot be a misread of Attack→18 — there is no hyperlink to 23 to mis-resolve",
            ],
        },
        "s024": {
            "standingGoblinsAsset013": standing_goblins(layers, 24),
            "texts": texts(layers, 24),
            "inbound": inbound(24),
        },
    }

    conflicts = [
        {
            "id": "boredom_not_kill",
            "remembered": remembered["boredom"],
            "binary": (
                "s015 fAutoAdvance+9000ms → s016 (2× asset-013, text Goblin fled of boredom…); "
                "boredom dissolve is on-slide only"
            ),
            "evidence": [
                "generated/timing_manifest.json transitions[slide=15] flagNames includes autoAdvance; effectType 22 newsflash",
                "docs/animation-manifest.json s015 targets only shapes 17418/17427 (text), not goblin pics",
                "generated/layers.json s015 asset-013×3 → s016 asset-013×2",
            ],
            "falsifiedMisreads": [
                "autoAdvance is NOT a mis-parsed media-end: SSSlideInfoAtom bit 0x0400 + positive slideTime",
                "effectType 22 is newsflash transition visual, independent of autoAdvance bit",
                "I'm bored dissolve is ExtTimeNode (not slide change)",
            ],
            "remapAllowed": False,
        },
        {
            "id": "attack_kill_ladder",
            "remembered": remembered["attack"],
            "binary": (
                "s015 Attack shape 17419 → ExHyperlink 62 Slide 18 (CAN'T ESCAPE + motions) → "
                "Continue → s024 still ×3; orphan s023 is the unused ×3 counter"
            ),
            "evidence": [
                "inventory interactive_actions s015 shape 17419 hlId 62",
                "poi_audit.tsv TEXTLINK 15 shape 17419 → Slide 18",
                "ExHyperlink 62 children: only CString inst0 Slide 18 (no target address atom)",
                "Slide 23 string absent from binary; inbound(23)=[]",
            ],
            "falsifiedMisreads": [
                "Attack/Flee shape binding swap: POI+InteractiveInfo agree; distinct bounds; 0 multi-InteractiveInfo per shape",
                "MouseOver vs MouseClick: InteractiveInfo parent instance=0 (click) for all combat options",
                "0-based Slide N: would break title Slide 2; POI DOCUMENT labels match 1-based order",
                "Label off-by-one to Felled(19): ExHyperlink says 18; s019 only inbound from s021 Attack",
            ],
            "remapAllowed": False,
        },
        {
            "id": "flee_same_count_counter",
            "remembered": remembered["flee"],
            "binary": (
                "s016/s021 Flee → s017 CAN'T ESCAPE → Continue ExHyperlink 77 Slide 22 "
                "(1× asset-013); no chained auto to ×2 counter s032"
            ),
            "evidence": [
                "s017 transition flags=[]; slideTimeMs=0",
                "ExHyperlink 77 = Slide 22 only",
                "layers s022 asset-013×1; reconstructed slide-022.png shows one goblin",
                "s032 inbound only from s016 Attack (not flee continue)",
            ],
            "falsifiedMisreads": [
                "s022 is not ×2 with a hidden goblin layer — only one picture shape uses asset-013",
                "No AfterEffect/WithEffect slide jump on s017 — behaviors are motion/set/effect only",
                "Prior override Continue→32 was a story remap; removed at db303a4",
            ],
            "remapAllowed": False,
        },
    ]

    experiments = [
        {
            "id": "A_human_ppt_oracle",
            "size": "smallest / decisive",
            "action": (
                "Open goblins3 v.1.0 LAUNCH.pps in real PowerPoint slideshow. On first ×3 menu: "
                "(1) wait ≥9s without clicking; (2) Attack; (3) from boredom ×2 Flee then Continue. "
                "Record destinations."
            ),
            "expectIfBinaryFaithful": (
                "auto→boredom×2; Attack→CAN'T ESCAPE then ×3@HP10; Flee Continue→×1 menu"
            ),
            "ifMatchesBinary": "Remembered play conflicts with this .pps build — still no remaps",
            "ifDiffersFromOurExtract": (
                "Re-open extract bugs with the observed targets as oracle (still interpretation, not invent bridges)"
            ),
        },
        {
            "id": "B_alternate_source_build",
            "size": "small",
            "action": (
                "Hash/compare any other goblins .pps/.ppt on the author machine against "
                f"inventory source.sha256={inv['source']['sha256']}"
            ),
            "why": "Memory may be from a different wiring of Attack→23 / Continue→32 that never shipped in this LAUNCH.pps",
        },
        {
            "id": "C_poi_address_null",
            "size": "tiny (already done)",
            "action": "POI HSLFHyperlink.getAddress() null for combat links; getLabel() is Slide N",
            "status": "confirmed_null_address_in_poi_audit",
        },
        {
            "id": "D_do_not_clear_autoAdvance",
            "size": "non-experiment / anti-pattern",
            "action": "Do NOT clear s015 autoAdvance or remap 17→32 / 18→19/23 — invent-bridge forbidden",
        },
    ]

    overrides_present = any(
        (h.get("resolveMethod") or "").startswith("user_authorized")
        or "override" in (h.get("resolveMethod") or "")
        for s in adv["slides"]
        for h in (s.get("hotspots") or [])
    )

    audit = {
        "format": "goblins-rpg3-combat-interpretation-audit-v1",
        "policy": "PPT binary is oracle; no USER_AUTHORIZED_TARGET_OVERRIDES; no invent-bridges",
        "sourceSha256": inv["source"]["sha256"],
        "assetCountHeuristic": {
            "method": "count HSLFPictureShape layers with assetId==asset-013 (standing goblin sprite)",
            "validatedAgainstReconstructedPng": {
                "s015": 3,
                "s016": 2,
                "s021": 2,
                "s022": 1,
                "s024": 3,
            },
            "chromaNote": (
                "pure green (0,128,0) placeholders are separate assets; "
                "asset-013 is the goblin sprite used for counts"
            ),
        },
        "interactiveInfoParents": ii_parents,
        "exHyperlinkFriendlyOnly": {
            "combatHyperlinkIdsSample": {
                str(k): ex_meta[k] for k in sample_ids if k in ex_meta
            },
            "allHaveSingleFriendlyCString": all(
                ex_meta[k]["cstringCount"] == 1 for k in sample_ids if k in ex_meta
            ),
        },
        "binary": binary,
        "rememberedVsBinaryConflicts": conflicts,
        "interpretationExperimentsLeft": experiments,
        "overridesPresentInManifest": overrides_present,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(audit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        f"Wrote {OUT} conflicts={len(conflicts)} overrides={overrides_present} "
        f"slide23_string={has_slide23}"
    )


if __name__ == "__main__":
    main()
