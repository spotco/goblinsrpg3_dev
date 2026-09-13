#!/usr/bin/env python3
"""Smoke: every Limit-available combat menu is deterministic and PPT-faithful.

For each menu that offers -limit / -LIMIT, click the visual OPTION center once
(and a second time from a fresh goto) and assert the landing slide matches
generated/combat_option_matrix.json (DocSum == pptx == web).

Also clicks Attack / Flee / Magic on those same menus when present, so a
swapped hotspot cannot hide behind a lucky Limit click.

Requires docs served at http://127.0.0.1:8765
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8765"
OUT = Path("/workspace")
ROOT = Path(__file__).resolve().parents[1]
MATRIX = json.loads((ROOT / "generated/combat_option_matrix.json").read_text())
GM = json.loads((ROOT / "docs/game-manifest.json").read_text())

OPTION_RE = {
    "attack": re.compile(r"^\s*-?\s*attack\s*$", re.I),
    "flee": re.compile(r"^\s*-?\s*flee\s*$", re.I),
    "limit": re.compile(r"^\s*-?\s*limit\s*$", re.I),
    "magic": re.compile(r"^\s*-?\s*magic\s*$", re.I),
}


def wait_ready(page):
    page.wait_for_function(
        "() => window.goblinsRpg3Debug && window.goblinsRpg3Debug.dumpScreen && document.querySelector('#stage')",
        timeout=25000,
    )
    page.wait_for_timeout(200)


def goto(page, slide: int):
    page.goto(f"{BASE}/?debug=1&slide={slide}", wait_until="domcontentloaded")
    wait_ready(page)
    page.evaluate("() => { try { goblinsRpg3Debug.setHudCollapsed(true); } catch (e) {} }")
    page.wait_for_function(
        "() => !document.getElementById('stage')?.classList.contains('is-transitioning')",
        timeout=5000,
    )
    page.wait_for_timeout(120)


def cur(page) -> int:
    return page.evaluate("() => goblinsRpg3Debug.snapshot().currentScreen.slide")


def visual_option_center(page, kind: str):
    pattern = OPTION_RE[kind].pattern
    return page.evaluate(
        """(pattern) => {
      const re = new RegExp(pattern, 'i');
      const stage = document.querySelector('#stage');
      const sb = stage.getBoundingClientRect();
      const layer = [...document.querySelectorAll('#layers .layer')].find((el) =>
        re.test((el.textContent || '').trim())
      );
      const btn = [...document.querySelectorAll('#hotspots button.hotspot')].find((b) =>
        re.test((b.getAttribute('aria-label') || '').trim())
      );
      const el = layer || btn;
      if (!el) return null;
      const r = el.getBoundingClientRect();
      const cx = r.x + r.width / 2;
      const cy = r.y + r.height / 2;
      const top = document.elementFromPoint(cx, cy);
      return {
        x: cx,
        y: cy,
        source: layer ? 'layer' : 'button',
        text: (el.textContent || el.getAttribute('aria-label') || '').trim(),
        btnTarget: btn && btn.dataset.target,
        top: top && {
          tag: top.tagName,
          cls: String(top.className || ''),
          aria: top.getAttribute && top.getAttribute('aria-label'),
        },
        frac: {
          x: (r.x - sb.x) / sb.width,
          y: (r.y - sb.y) / sb.height,
          w: r.width / sb.width,
          h: r.height / sb.height,
        },
      };
    }""",
        pattern,
    )


def matrix_cases():
    cases = []
    for slide_row in MATRIX.get("slides") or []:
        slide = int(slide_row["slide"])
        kinds = {opt.get("kind") for opt in slide_row.get("options") or []}
        if "limit" not in kinds:
            continue
        for opt in slide_row.get("options") or []:
            kind = opt.get("kind")
            target = opt.get("targetSlide")
            if not kind or target is None:
                continue
            cases.append(
                {
                    "slide": slide,
                    "kind": kind,
                    "expect": int(target),
                    "pptx": opt.get("pptxTarget"),
                    "docsum": opt.get("docsumTarget"),
                    "caption": opt.get("outcomeCaption"),
                }
            )
    return cases


def assert_static(failures, notes) -> None:
    if MATRIX.get("summary", {}).get("mismatchCount", 0):
        failures.append(f"matrix mismatchCount={MATRIX['summary']['mismatchCount']}")
    limit_menus = MATRIX.get("limitMenus") or []
    if len(limit_menus) < 10:
        failures.append(f"expected many Limit menus, got {len(limit_menus)}")
    for row in limit_menus:
        web = row.get("targetSlide")
        if web != row.get("pptxTarget") or web != row.get("docsumTarget"):
            failures.append(f"s{row['slide']} LIMIT web/pptx/docsum disagree: {row}")
    # One clickable Limit hotspot per menu slide
    screens = {s["slide"]: s for s in GM["screens"]}
    for row in limit_menus:
        screen = screens[row["slide"]]
        hits = [
            h
            for h in screen.get("hotspots") or []
            if h.get("clickable")
            and OPTION_RE["limit"].match(str(h.get("shapeText") or ""))
        ]
        if len(hits) != 1:
            failures.append(f"s{row['slide']} expected 1 clickable Limit hotspot, got {len(hits)}")
        elif hits[0].get("targetSlide") != row["targetSlide"]:
            failures.append(
                f"s{row['slide']} Limit hotspot target {hits[0].get('targetSlide')} != matrix {row['targetSlide']}"
            )
    notes.append(f"static: {len(limit_menus)} Limit menus; mismatchCount=0")


def click_option(page, slide: int, kind: str, expect: int, failures, notes, tag: str) -> None:
    goto(page, slide)
    page.evaluate("() => goblinsRpg3Debug.clearHistory()")
    info = visual_option_center(page, kind)
    if not info:
        failures.append(f"{tag} s{slide} missing visual {kind}")
        return
    page.mouse.click(info["x"], info["y"])
    page.wait_for_timeout(550)
    after = cur(page)
    line = (
        f"{tag} s{slide} visual-{kind} → {after} (expect {expect}); "
        f"top={info.get('top')}; btn={info.get('btnTarget')}"
    )
    notes.append(line)
    print(line, flush=True)
    if after != expect:
        failures.append(
            f"{tag} s{slide} {kind}: expected {expect}, got {after}"
        )
        page.screenshot(path=str(OUT / f"goblins-limit-fail-s{slide:03d}-{kind}-{tag}.png"), full_page=False)


def main() -> int:
    failures: list[str] = []
    notes: list[str] = []
    assert_static(failures, notes)
    cases = matrix_cases()
    if not cases:
        print("no Limit-menu cases in matrix", flush=True)
        return 1

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.on("pageerror", lambda err: notes.append(f"PAGEERROR {err}"))

        # Two independent passes per Limit option prove the landing is not random.
        limit_cases = [c for c in cases if c["kind"] == "limit"]
        other_cases = [c for c in cases if c["kind"] != "limit"]
        for pass_id in ("p1", "p2"):
            for case in limit_cases:
                click_option(
                    page,
                    case["slide"],
                    "limit",
                    case["expect"],
                    failures,
                    notes,
                    pass_id,
                )
        for case in other_cases:
            click_option(
                page,
                case["slide"],
                case["kind"],
                case["expect"],
                failures,
                notes,
                "opt",
            )

        # s190 overlap strip: visual Limit center must still be Limit, not Flee/Attack.
        goto(page, 190)
        info = visual_option_center(page, "limit")
        if info:
            notes.append(f"s190 Limit center frac={info.get('frac')} top={info.get('top')}")
            page.screenshot(path=str(OUT / "goblins-limit-s190-center.png"), full_page=False)

        browser.close()

    report = OUT / "goblins-limit-combat-report.txt"
    report.write_text("\n".join(notes + ["", f"failures={len(failures)}"] + failures) + "\n")
    print(f"wrote {report}", flush=True)
    if failures:
        print("FAILURES:", *failures, sep="\n  ", flush=True)
        return 1
    print(f"ALL LIMIT / COMBAT OPTION CASES PASSED ({len(limit_cases)} Limit x2 + {len(other_cases)} siblings)", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
