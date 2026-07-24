"""Scan all screens for common fidelity / mapping risks.

Uses **post-resolve** game-manifest hotspots (promotes + residual policy), not raw
binary ExHyperlink self-labels. Writes generated/visual_risks.json with a
prioritized queue for agents and humans.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from pathlib import Path

from debug_lib import (
    REPO_ROOT,
    animation_by_slide,
    collect_screen_risks,
    layers_by_slide,
    load_animation_manifest,
    load_game_manifest,
    load_json,
    load_layers_manifest,
    parse_poi_audit,
    parse_slide_list,
    write_json,
)

SELF_CLICKABLE = "self_hyperlink_clickable"
SELF_RESIDUAL = "self_hyperlink_documented_residual"
SELF_PROMOTED = "self_hyperlink_promoted"
SELF_UNCLASSIFIED = "self_hyperlink_unclassified"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=REPO_ROOT)
    parser.add_argument("--slides", type=str, default=None, help="Optional subset, e.g. 1-10,14")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    repo = args.repo
    game_manifest = load_game_manifest(repo / "docs" / "game-manifest.json")
    layers_manifest = load_layers_manifest(repo / "generated" / "layers.json")
    animation_manifest = load_animation_manifest()
    _, poi_by_slide, backgrounds = parse_poi_audit(repo / "generated" / "poi_audit.tsv")
    selected = parse_slide_list(args.slides)

    promote_path = repo / "generated" / "promote_audit.json"
    promote_audit = load_json(promote_path) if promote_path.exists() else None

    all_risks = []
    per_slide = []
    slides_scanned = 0
    for screen in game_manifest.get("screens") or []:
        slide = int(screen["slide"])
        if selected is not None and slide not in selected:
            continue
        slides_scanned += 1
        layers_slide = layers_by_slide(layers_manifest, slide)
        docs_png = repo / "docs" / "screens" / f"slide-{slide:03d}.png"
        gen_png = repo / "generated" / "reconstructed" / f"slide-{slide:03d}.png"
        png_path = docs_png if docs_png.exists() else gen_png
        risks = collect_screen_risks(
            slide=slide,
            screen=screen,
            layers_slide=layers_slide,
            poi_shapes=poi_by_slide.get(slide, []),
            background=backgrounds.get(slide),
            png_path=png_path,
            animation_slide=animation_by_slide(animation_manifest, slide),
        )
        all_risks.extend(risks)
        # Queue prioritizes unresolved defects, not documented info residuals.
        defect_risks = [risk for risk in risks if risk["severity"] in {"high", "medium"}]
        if defect_risks or risks:
            per_slide.append(
                {
                    "slide": slide,
                    "screenId": screen.get("id"),
                    "riskCount": len(risks),
                    "defectCount": len(defect_risks),
                    "high": sum(1 for risk in risks if risk["severity"] == "high"),
                    "medium": sum(1 for risk in risks if risk["severity"] == "medium"),
                    "codes": sorted({risk["code"] for risk in risks}),
                    "defectCodes": sorted({risk["code"] for risk in defect_risks}),
                    "suggestedUrl": f"http://127.0.0.1:8765/?debug=1&slide={slide}",
                    "suggestedCommand": f"python tools/debug_slide.py {slide}",
                }
            )

    by_code: dict[str, list[dict]] = defaultdict(list)
    for risk in all_risks:
        by_code[risk["code"]].append(risk)

    severity_rank = {"high": 0, "medium": 1, "low": 2, "info": 3}
    queue = sorted(
        [item for item in per_slide if item["high"] or item["medium"]],
        key=lambda item: (
            -item["high"],
            -item["medium"],
            -item["defectCount"],
            item["slide"],
        ),
    )
    full_queue = sorted(
        per_slide,
        key=lambda item: (
            -item["high"],
            -item["medium"],
            -item["riskCount"],
            item["slide"],
        ),
    )

    residual_self = by_code.get(SELF_RESIDUAL) or []
    clickable_self = by_code.get(SELF_CLICKABLE) or []
    promoted_self = by_code.get(SELF_PROMOTED) or []
    unclassified_self = by_code.get(SELF_UNCLASSIFIED) or []

    promote_residual_count = None
    promote_residual_ids: set[str] = set()
    if isinstance(promote_audit, dict):
        promote_residual_count = (promote_audit.get("summary") or {}).get("residualSelfCount")
        for row in promote_audit.get("residualSelfHyperlinks") or []:
            hid = row.get("hotspotId")
            if hid:
                promote_residual_ids.add(str(hid))

    residual_ids = {
        str((risk.get("evidence") or {}).get("hotspotId"))
        for risk in residual_self
        if (risk.get("evidence") or {}).get("hotspotId")
    }

    post_resolve = {
        "policy": (
            "Self-hyperlink risks use docs/game-manifest.json post-resolve targets "
            "(promotes + residual policy). Binary ExHyperlink self-labels that were "
            "promoted are self_hyperlink_promoted (info), not high defects."
        ),
        "clickableSelfCount": len(clickable_self),
        "documentedResidualSelfCount": len(residual_self),
        "promotedSelfCount": len(promoted_self),
        "unclassifiedSelfCount": len(unclassified_self),
        "promoteAuditResidualSelfCount": promote_residual_count,
        "residualMatchesPromoteAudit": (
            promote_residual_count is not None
            and len(residual_self) == int(promote_residual_count)
            and residual_ids == promote_residual_ids
        ),
        "documentedResidualHotspotIds": sorted(residual_ids),
        "clickableSelfHotspotIds": sorted(
            str((risk.get("evidence") or {}).get("hotspotId"))
            for risk in clickable_self
            if (risk.get("evidence") or {}).get("hotspotId")
        ),
    }

    report = {
        "format": "goblins-rpg3-visual-risks-v2",
        "policy": {
            "hotspotTargets": "post_resolve_game_manifest",
            "selfHyperlink": {
                "clickable_self": "high defect",
                "documented_residual": "info (accepted Phase 2)",
                "promoted_leave": "info provenance",
            },
            "media": {
                "unresolved_media": "high",
                "documented_*_media": "info residual",
            },
        },
        "summary": {
            "slidesScanned": slides_scanned,
            "slidesWithRisks": len(per_slide),
            "slidesWithDefects": len(queue),
            "riskTotal": len(all_risks),
            "defectTotal": sum(1 for risk in all_risks if risk["severity"] in {"high", "medium"}),
            "bySeverity": dict(Counter(risk["severity"] for risk in all_risks)),
            "byCode": {code: len(items) for code, items in sorted(by_code.items())},
        },
        "selfHyperlinkPostResolve": post_resolve,
        "queue": queue,
        "allSlidesWithRisks": full_queue,
        "byCode": {
            code: {
                "count": len(items),
                "severity": Counter(item["severity"] for item in items).most_common(1)[0][0],
                "slides": sorted({item["slide"] for item in items}),
                "examples": items[:5],
            }
            for code, items in sorted(
                by_code.items(),
                key=lambda pair: (severity_rank.get(pair[1][0]["severity"], 9), -len(pair[1]), pair[0]),
            )
        },
        "risks": sorted(
            all_risks,
            key=lambda risk: (severity_rank.get(risk["severity"], 9), risk["slide"], risk["code"]),
        ),
    }

    output = args.output or (repo / "generated" / "visual_risks.json")
    write_json(output, report)
    print(
        f"Scanned risks: total={report['summary']['riskTotal']} "
        f"defects={report['summary']['defectTotal']} "
        f"slidesWithDefects={report['summary']['slidesWithDefects']} -> {output}"
    )
    print(
        "Self-hyperlink post-resolve: "
        f"clickable={post_resolve['clickableSelfCount']} "
        f"residual={post_resolve['documentedResidualSelfCount']} "
        f"promoted={post_resolve['promotedSelfCount']} "
        f"matchPromoteAudit={post_resolve['residualMatchesPromoteAudit']}"
    )
    print("Top defect queue:")
    for item in queue[:15]:
        print(
            f"  slide {item['slide']:03d}: high={item['high']} medium={item['medium']} "
            f"codes={','.join(item['defectCodes'][:6]) or '(none)'}"
        )


if __name__ == "__main__":
    main()
