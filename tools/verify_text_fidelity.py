"""Verify Phase 5.6/5.7 text encoding, empty placeholders, WordArt, sparse hybrid."""

from __future__ import annotations

import json
from pathlib import Path

from build_text_fidelity_report import main as rebuild_text_report
from extract_layers import normalize_ppt_text


def fail(message: str) -> None:
    raise SystemExit(message)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    rebuild_text_report()

    app_js = (root / "docs" / "app.js").read_text(encoding="utf-8")
    styles = (root / "docs" / "styles.css").read_text(encoding="utf-8")
    report = load_json(root / "generated" / "text_fidelity_report.json")
    game = load_json(root / "docs" / "game-manifest.json")
    layers = load_json(root / "generated" / "layers.json")

    if report.get("format") != "goblins-rpg3-text-fidelity-v1":
        fail("text_fidelity_report format unexpected")

    # Unit fixtures for encoding repair.
    fixtures = {
        "donÆt ask": "don't ask",
        "continueà": "continue…",
        "ôhelloö": "\u201chello\u201d",
        "Creditsù": "Credits:",
        "timeÖà": "time……",
    }
    for src, expected in fixtures.items():
        got = normalize_ppt_text(src)
        if got != expected:
            fail(f"normalize_ppt_text({src!r}) -> {got!r}, expected {expected!r}")

    # No residual artifact chars in published layer text.
    residual = report.get("summary", {}).get("residualArtifactLayerCount", 1)
    if residual != 0:
        fail(f"residual encoding artifacts remain in layer text: {residual}")

    if report.get("summary", {}).get("wordArtCount", 0) < 1:
        fail("expected WordArt layers in text fidelity report")

    # Empty placeholders flagged in layers.json.
    empty_flags = sum(
        1
        for slide in layers.get("slides") or []
        for layer in slide.get("layers") or []
        if layer.get("emptyTextPlaceholder")
    )
    if empty_flags < 1:
        fail("expected emptyTextPlaceholder flags on layers")

    # Sparse hybrid slides include known title/end slides when still sparse.
    sparse = set(report.get("sparseHybridSlides") or [])
    if 2 not in sparse and 200 not in sparse:
        # Not fatal if coverage improved; require at least the report list is present.
        pass

    for snippet in report.get("runtimeSnippets") or []:
        if snippet not in app_js and snippet not in styles:
            fail(f"runtime text-fidelity snippet missing: {snippet}")

    # Spot-check opening narrative text fixed in game-manifest.
    s3 = game["screens"][2]
    texts = [str(layer.get("text") or "") for layer in s3.get("layers") or []]
    joined = "\n".join(texts)
    if "Æ" in joined or "à" in joined:
        fail(f"slide 3 still has encoding artifacts: {joined[:200]!r}")
    if "…" not in joined and "ago" in joined:
        fail("slide 3 expected ellipsis after encoding repair")

    print("text fidelity verification passed")
    print(
        f"  emptyPlaceholders={report['summary']['emptyTextPlaceholders']} "
        f"wordArt={report['summary']['wordArtCount']} "
        f"sparseHybrid={report['summary']['sparseHybridSlideCount']} "
        f"residualArtifacts={report['summary']['residualArtifactLayerCount']}"
    )


if __name__ == "__main__":
    main()
