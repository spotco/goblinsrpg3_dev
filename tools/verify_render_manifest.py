"""Verify reconstructed render output and render-manifest integrity."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fail(message: str) -> None:
    raise SystemExit(message)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path("generated/reconstructed/render_manifest.json"))
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    if manifest.get("format") != "goblins-rpg3-render-manifest-v2":
        fail("unexpected render manifest format")
    if manifest.get("renderer") != "goblins-layer-reconstruction-v2":
        fail("unexpected renderer id")
    settings = manifest.get("renderSettings", {})
    if settings.get("width") != 720 or settings.get("height") != 540:
        fail("expected 720x540 render settings")
    slides = manifest.get("slides", [])
    if len(slides) != 201:
        fail(f"expected 201 rendered slides, found {len(slides)}")
    expected_slides = list(range(1, 202))
    actual_slides = [int(item["slide"]) for item in slides]
    if actual_slides != expected_slides:
        fail("rendered slide list is not contiguous 1..201")

    total_images = 0
    total_text = 0
    transformed = 0
    for item in slides:
        path = Path(item["path"])
        if not path.exists():
            fail(f"missing rendered slide: {path}")
        if path.stat().st_size != item["bytes"]:
            fail(f"byte count mismatch: {path}")
        if sha256(path) != item["sha256"]:
            fail(f"sha256 mismatch: {path}")
        with Image.open(path) as image:
            if image.size != (720, 540):
                fail(f"unexpected image size for {path}: {image.size}")
        total_images += int(item.get("imageLayerCount", 0))
        total_text += int(item.get("textLayerCount", 0))
        transformed += int(item.get("transformedLayerCount", 0))

    summary = manifest.get("summary", {})
    if summary.get("imageCount") != total_images or total_images != 532:
        fail(f"unexpected image layer total: {total_images}")
    if summary.get("textCount") != total_text or total_text != 650:
        fail(f"unexpected text layer total: {total_text}")
    if summary.get("transformedLayerCount") != transformed:
        fail(f"unexpected transformed layer total: {transformed}")

    print("render manifest verification passed")


if __name__ == "__main__":
    main()
