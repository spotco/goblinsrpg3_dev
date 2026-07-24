"""Phase 5.6/5.7 offline text/WordArt fidelity report.

Writes generated/text_fidelity_report.json:
  - encoding repair inventory (artifact → replacement counts)
  - empty text placeholders
  - WordArt geometry inventory
  - sparse hybrid underlay slides
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from extract_layers import PPT_TEXT_ARTIFACT_REPLACEMENTS, normalize_ppt_text

ROOT = Path(__file__).resolve().parents[1]


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    game = load_json(ROOT / "docs" / "game-manifest.json")
    layers = load_json(ROOT / "generated" / "layers.json")

    artifact_counts: Counter[str] = Counter()
    fixed_examples: list[dict] = []
    residual_bad: list[dict] = []
    empty_placeholders = 0
    empty_animated = 0
    wordart: list[dict] = []
    sparse_hybrid: list[int] = []

    # Scan published screens (post build_game_manifest copy of layers).
    for screen in game.get("screens") or []:
        slide = int(screen["slide"])
        layers_list = screen.get("layers") or []
        max_area = 0.0
        large_images = 0
        non_empty_text = 0
        for layer in layers_list:
            bounds = layer.get("bounds") or {}
            area = float(bounds.get("width") or 0) * float(bounds.get("height") or 0)
            max_area = max(max_area, area)
            if layer.get("type") == "image" and area >= 0.5:
                large_images += 1
            text = str(layer.get("text") or "")
            if layer.get("type") == "text" and text.strip() and not layer.get("emptyTextPlaceholder"):
                non_empty_text += 1
            if layer.get("emptyTextPlaceholder") or (
                layer.get("type") == "text" and not text.strip() and not layer.get("wordArt")
            ):
                empty_placeholders += 1
                if layer.get("animated"):
                    empty_animated += 1
            if layer.get("wordArt"):
                wordart.append(
                    {
                        "slide": slide,
                        "shapeId": layer.get("shapeId"),
                        "geometry": layer.get("wordArtGeometry") or layer.get("shapeType"),
                        "text": text,
                        "fontFamily": (layer.get("geoText") or {}).get("fontFamily"),
                    }
                )
            # Residual encoding artifacts should be gone after extract normalize.
            for ch in PPT_TEXT_ARTIFACT_REPLACEMENTS:
                if ch in text:
                    residual_bad.append(
                        {"slide": slide, "shapeId": layer.get("shapeId"), "char": ch, "text": text[:80]}
                    )
            # Count what *would* have been fixed from raw-ish residual checks via inverse:
            # also scan if replacement chars appear (informational).
            for src, dst in PPT_TEXT_ARTIFACT_REPLACEMENTS.items():
                if dst in text and src not in text:
                    pass

        if large_images == 0 and max_area < 0.5 and non_empty_text <= 2 and layers_list:
            sparse_hybrid.append(slide)

    # Compare against raw geotext in layers.json (pre-publish same normalize).
    # Use a synthetic re-application check on known fixed samples by re-decoding
    # from residual report of original artifact chars in any field including geoText.rawUnicode.
    for slide_entry in layers.get("slides") or []:
        slide = int(slide_entry["slide"])
        for layer in slide_entry.get("layers") or []:
            candidates = [str(layer.get("text") or "")]
            geo = layer.get("geoText") or {}
            if geo.get("rawUnicode"):
                candidates.append(str(geo.get("rawUnicode")))
            for run in layer.get("textRuns") or []:
                candidates.append(str(run.get("text") or ""))
            for raw in candidates:
                for ch in PPT_TEXT_ARTIFACT_REPLACEMENTS:
                    if ch in raw:
                        # Should not remain in normalized `text` field.
                        if ch in str(layer.get("text") or ""):
                            artifact_counts[ch] += raw.count(ch)
                        else:
                            # raw had it but normalized text does not — count as repaired source
                            artifact_counts[f"raw:{ch}"] += raw.count(ch)
                normalized = normalize_ppt_text(raw)
                if normalized != raw and len(fixed_examples) < 20:
                    fixed_examples.append(
                        {
                            "slide": slide,
                            "shapeId": layer.get("shapeId"),
                            "before": raw[:100],
                            "after": normalized[:100],
                        }
                    )

    report = {
        "format": "goblins-rpg3-text-fidelity-v1",
        "policy": {
            "encoding": "normalize_ppt_text in extract_layers (Phase 5.7)",
            "emptyText": "emptyTextPlaceholder flag; runtime hides non-animated empties (Phase 5.6)",
            "wordArt": "wordArtGeometry + CSS approx for DEFLATE/CURVE (Phase 5.6)",
            "sparse": "hybrid PNG underlay when sparse layers (Phase 5.6)",
        },
        "replacements": dict(PPT_TEXT_ARTIFACT_REPLACEMENTS),
        "summary": {
            "emptyTextPlaceholders": empty_placeholders,
            "emptyTextAnimated": empty_animated,
            "wordArtCount": len(wordart),
            "sparseHybridSlideCount": len(sparse_hybrid),
            "residualArtifactLayerCount": len(residual_bad),
            "fixedExampleCount": len(fixed_examples),
        },
        "sparseHybridSlides": sparse_hybrid,
        "wordArt": wordart,
        "fixedExamples": fixed_examples,
        "residualArtifacts": residual_bad[:20],
        "runtimeSnippets": [
            "function screenNeedsPngUnderlay",
            "pngUnderlay",
            "wordArtGeometry",
            "empty-text-placeholder",
            "wordart-deflate",
        ],
    }

    out = ROOT / "generated" / "text_fidelity_report.json"
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(
        f"Wrote {out} emptyPlaceholders={empty_placeholders} wordArt={len(wordart)} "
        f"sparseHybrid={len(sparse_hybrid)} residualArtifacts={len(residual_bad)}"
    )


if __name__ == "__main__":
    main()
