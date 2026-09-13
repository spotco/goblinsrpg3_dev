#!/usr/bin/env python3
"""Regression: click Attack/Flee by visual OPTION layer centers (not aria selectors).

Prior playthroughs used button.hotspot.click() / aria-label substrings, which always
hit the Attack DOM node even if bounds/z-order would send a real pointer to Flee.
This clicks the center of the matching OPTION text layer and asserts navigation.
Fails if Attack navigates to the Flee target (or any wrong slide).

The s016 regression deliberately goes beyond an immediate target check: after the
authored s015 boredom auto-advance leaves two goblins, one Flee click must enter
s017, visibly settle on CAN'T ESCAPE, and remain there until its explicit Continue
hotspot is clicked. This catches a self-reload, timer race, click-through, or
accidental jump to the one-goblin s022 menu.
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
GM = json.loads((ROOT / "docs/game-manifest.json").read_text())

# Exact option label (do not use /attack/i — that matches "Goblin x3 attacked!").
OPTION_RE = {
    "Attack": re.compile(r"^\s*-?\s*attack\s*$", re.I),
    "flee": re.compile(r"^\s*-?\s*flee\s*$", re.I),
}

# Menus to probe: (slide, option, expected_target, notes)
CASES = [
    (15, "Attack", 18, "first combat; Attack → CAN'T ESCAPE (not flee 17)"),
    (16, "Attack", 32, "boredom menu Attack"),
    (16, "flee", 17, "boredom menu flee"),
    (21, "Attack", 19, "loop menu Attack"),
    (21, "flee", 17, "loop menu flee"),
    (22, "Attack", 34, "post-flee menu Attack"),
    (22, "flee", 36, "post-flee menu flee"),
    (24, "Attack", 31, "later menu Attack"),
]


def expected_flee_target(slide: int) -> int | None:
    screen = next(s for s in GM["screens"] if s["slide"] == slide)
    for h in screen.get("hotspots") or []:
        if OPTION_RE["flee"].match(str(h.get("shapeText") or "")) and h.get("clickable"):
            return h.get("targetSlide")
    return None


def wait_ready(page):
    page.wait_for_function(
        "() => window.goblinsRpg3Debug && window.goblinsRpg3Debug.dumpScreen && document.querySelector('#stage')",
        timeout=25000,
    )
    page.wait_for_timeout(250)


def goto(page, slide: int):
    page.goto(f"{BASE}/?debug=1&slide={slide}", wait_until="domcontentloaded")
    wait_ready(page)
    page.evaluate("() => { try { goblinsRpg3Debug.setHudCollapsed(true); } catch (e) {} }")
    page.wait_for_timeout(200)


def cur(page) -> int:
    return page.evaluate("() => goblinsRpg3Debug.snapshot().currentScreen.slide")


def exact_two_goblin_flee_regression(page, failures, notes) -> None:
    """Exercise the reported s015 boredom → s016 Flee failure end to end."""
    goto(page, 15)
    page.evaluate("() => goblinsRpg3Debug.clearHistory()")
    page.wait_for_function(
        "() => goblinsRpg3Debug.snapshot().currentScreen.slide === 16",
        timeout=15000,
    )
    page.wait_for_timeout(250)

    # Extracted s016 has two goblin picture layers: shapes 20483 and 20485.
    # Keep the assertion evidence-based rather than inferring entities from pixels.
    goblin_shapes = page.evaluate(
        """() => [...document.querySelectorAll('#layers .layer')]
          .filter((el) => ['20483', '20485'].includes(el.dataset.shapeId))
          .filter((el) => {
            const cs = getComputedStyle(el);
            return cs.visibility !== 'hidden' && Number(cs.opacity) > 0.1;
          })
          .map((el) => el.dataset.shapeId)"""
    )
    if set(goblin_shapes) != {"20483", "20485"}:
        failures.append(f"s016 expected two visible goblins 20483/20485, got {goblin_shapes}")

    info = visual_option_center(page, "flee")
    if not info:
        failures.append("s016 exact regression: missing visual Flee option")
        return
    if info.get("btnTarget") != "slide-017":
        failures.append(f"s016 Flee DOM target expected slide-017, got {info.get('btnTarget')}")
    if (info.get("top") or {}).get("aria", "").lower() != "-flee":
        failures.append(f"s016 Flee center not covered by Flee hotspot: {info.get('top')}")

    page.mouse.click(info["x"], info["y"])
    # Wait beyond the full s017 motion/text train. It must not self-advance or
    # click through to s022's authored one-goblin menu.
    page.wait_for_timeout(4250)
    after = cur(page)
    visible_text = page.evaluate(
        r"""() => [...document.querySelectorAll('#layers .layer')]
          .filter((el) => {
            const cs = getComputedStyle(el);
            return cs.visibility !== 'hidden' && Number(cs.opacity) > 0.2;
          })
          .map((el) => (el.textContent || '').replace(/\s+/g, ' ').trim())
          .filter(Boolean)"""
    )
    history = page.evaluate("() => goblinsRpg3Debug.history()")
    flee_events = [
        event for event in history
        if event.get("hotspotId") == "s016-a425115" and event.get("targetSlide") == 17
    ]
    if after != 17:
        failures.append(f"one s016 Flee click must remain on s017, got s{after:03d}")
    if not any("CAN'T ESCAPE" in text.upper() for text in visible_text):
        failures.append(f"s017 did not visibly settle on CAN'T ESCAPE: {visible_text}")
    if not flee_events:
        failures.append(f"history missing s016-a425115 →17: {history[-6:]}")
    if any(event.get("targetSlide") == 22 for event in history):
        failures.append("one s016 Flee click unexpectedly continued to one-goblin s022")

    shot = OUT / "goblins-exact-s016-two-goblins-flee.png"
    page.screenshot(path=str(shot), full_page=False)
    line = (
        f"exact boredom path: s015 auto→16 ({len(goblin_shapes)} goblins), "
        f"one visual Flee→{after}, visible={visible_text}, "
        f"historyTargets={[event.get('targetSlide') for event in flee_events]}"
    )
    notes.append(line)
    print(line, flush=True)


def visual_option_center(page, option: str):
    """Center of the OPTION text layer whose text exactly matches Attack/flee."""
    pattern = OPTION_RE[option].pattern
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


def main() -> int:
    failures = []
    notes = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.on("pageerror", lambda err: notes.append(f"PAGEERROR {err}"))

        for slide, option, expect, note in CASES:
            goto(page, slide)
            flee_tgt = expected_flee_target(slide)
            info = visual_option_center(page, option)
            if not info:
                failures.append(f"s{slide}: no visual OPTION for {option!r}")
                notes.append(f"FAIL s{slide} {option}: missing layer/button")
                continue
            before = cur(page)
            page.mouse.click(info["x"], info["y"])
            page.wait_for_timeout(500)
            after = cur(page)
            shot = OUT / f"goblins-visual-opt-s{slide:03d}-{option}.png"
            page.screenshot(path=str(shot), full_page=False)
            line = (
                f"s{slide} visual-{option} center → {after} (expect {expect}); "
                f"fleeTarget={flee_tgt}; top={info.get('top')}; {note}"
            )
            notes.append(line)
            print(line, flush=True)
            if after != expect:
                failures.append(
                    f"s{slide} {option}: expected {expect}, got {after} (before={before})"
                )
            # Only flag Attack→flee when flee and Attack have distinct targets
            # (s24 Attack/flee both →31 by PPT design — not a swap).
            if (
                option == "Attack"
                and flee_tgt is not None
                and after == flee_tgt
                and flee_tgt != expect
            ):
                failures.append(
                    f"s{slide} Attack navigated to flee target {flee_tgt} (coverage bug)"
                )

        exact_two_goblin_flee_regression(page, failures, notes)

        browser.close()

    report = OUT / "goblins-visual-options-report.txt"
    report.write_text("\n".join(notes + ["", f"failures={len(failures)}"] + failures) + "\n")
    print(f"wrote {report}", flush=True)
    if failures:
        print("FAILURES:", *failures, sep="\n  ", flush=True)
        return 1
    print("ALL VISUAL OPTION CASES PASSED", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
