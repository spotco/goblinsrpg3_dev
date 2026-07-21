"""Render legacy PowerPoint slides with Aspose.Slides (optional tool).

This tool is intentionally kept separate from the Python 3.14 extractor: the
current Aspose wheel supports Python 3.13 on Windows. It is a development-time
renderer only; generated PNGs are what the browser runtime will consume.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import aspose.slides as slides


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, default=Path("generated/renders"))
    parser.add_argument("--scale", type=float, default=2.0)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    manifest = []
    presentation = slides.Presentation(str(args.source))
    try:
        for index, slide in enumerate(presentation.slides, start=1):
            output = args.output / f"slide-{index:03d}.png"
            image = slide.get_image(args.scale, args.scale)
            image.save(str(output))
            manifest.append(
                {
                    "slide": index,
                    "path": output.as_posix(),
                    "width": image.width,
                    "height": image.height,
                    "bytes": output.stat().st_size,
                }
            )
    finally:
        # Aspose's Python wrapper exposes .close() on some versions and no
        # public dispose method on others; release through context cleanup when
        # available without making the renderer version-sensitive.
        close = getattr(presentation, "close", None)
        if close is not None:
            close()
    (args.output / "render_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(f"Rendered {len(manifest)} slides to {args.output}")


if __name__ == "__main__":
    main()
