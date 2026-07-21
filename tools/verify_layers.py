"""Regression checks for the generated non-Aspose layer manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", nargs="?", type=Path, default=Path("generated/layers.json"))
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    summary = manifest["summary"]
    assert manifest["format"] == "goblins-rpg3-layer-manifest-v1"
    assert summary["slides"] == 201
    assert summary["layers"] == 1182
    assert summary["imageInstances"] == 532
    assert summary["textLayers"] == 650
    assert summary["animatedShapeTargets"] == 567
    assert summary["animatedLayers"] == 567

    image_layers = []
    animated_images = 0
    animated_text = 0
    for slide in manifest["slides"]:
        assert "layers" in slide
        z_orders = [layer["zOrder"] for layer in slide["layers"]]
        assert z_orders == sorted(z_orders), slide["slide"]
        for layer in slide["layers"]:
            bounds = layer["bounds"]
            assert "points" in bounds
            assert layer["type"] in {"image", "text", "shape"}
            if layer["animated"] and layer["type"] == "image":
                animated_images += 1
            if layer["animated"] and layer["type"] == "text":
                animated_text += 1
            if layer["type"] == "image":
                image_layers.append(layer)
                path = Path(layer["instancePath"])
                assert path.exists(), path
                assert path.stat().st_size == layer["sourceBytes"], path

    assert len(image_layers) == 532
    assert animated_images > 0
    assert animated_text > 0
    print("layer manifest verification passed")


if __name__ == "__main__":
    main()
