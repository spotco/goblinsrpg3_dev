#!/usr/bin/env python3
"""Regression: click Attack/Flee by visual OPTION layer centers (not aria selectors).

Prior playthroughs used button.hotspot.click() / aria-label substrings, which always
hit the Attack DOM node even if bounds/z-order would send a real pointer to Flee.
This clicks the center of the matching OPTION text layer and asserts navigation.
Fails if Attack navigates to the Flee target (or any wrong slide).

Targets use DocSummary slideId resolution (stale ExHyperlink 'Slide N' labels lie).
Attack 15→19→25→21 (one fewer); Flee 15→17→23→24 (same ×3). No target overrides.
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
    (15, "Attack", 19, "first combat; Attack → Felled (one fewer)"),
    (15, "flee", 17, "first combat; Flee → CAN'T ESCAPE (same count)"),
    (16, "Attack", 33, "boredom menu Attack"),
    (16, "flee", 18, "boredom menu flee"),
    (21, "Attack", 20, "×2 menu Attack"),
    (21, "flee", 18, "×2 menu flee"),
    (22, "Attack", 35, "×1 menu Attack"),
    (22, "flee", 37, "×1 menu flee"),
    (24, "Attack", 32, "×3 menu Attack"),
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
    # Wait out CSS slide transitions (newsflash/zoom/etc. up to ~900ms) so hotspots hit-test.
    page.wait_for_function(
        "() => !document.getElementById('stage')?.classList.contains('is-transitioning')",
        timeout=5000,
    )
    page.wait_for_timeout(150)


def cur(page) -> int:
    return page.evaluate("() => goblinsRpg3Debug.snapshot().currentScreen.slide")



def standing_goblin_count(slide: int) -> int:
    screen = next(s for s in GM["screens"] if s["slide"] == slide)
    return sum(1 for L in screen.get("layers") or [] if L.get("assetId") == "asset-013")


def assert_first_goblin_count_edges(failures, notes) -> None:
    """Static regressions: Attack/Flee count transitions for the opening fight."""
    if standing_goblin_count(15) != 3:
        failures.append(f"s015 expected 3 standing goblins, got {standing_goblin_count(15)}")
    if standing_goblin_count(16) != 2:
        failures.append(f"s016 expected 2 standing goblins, got {standing_goblin_count(16)}")
    if standing_goblin_count(21) != 2:
        failures.append(f"s021 expected 2 standing goblins, got {standing_goblin_count(21)}")
    if standing_goblin_count(22) != 1:
        failures.append(f"s022 expected 1 standing goblin, got {standing_goblin_count(22)}")
    if standing_goblin_count(24) != 3:
        failures.append(f"s024 expected 3 standing goblins, got {standing_goblin_count(24)}")

    def hyperlink(slide: int, shape_text_re: str):
        import re as _re
        screen = next(s for s in GM["screens"] if s["slide"] == slide)
        rx = _re.compile(shape_text_re, _re.I)
        for h in screen.get("hotspots") or []:
            if h.get("action") == "hyperlink" and rx.search(str(h.get("shapeText") or "")):
                return h
        return None

    atk15 = hyperlink(15, r"^-?\s*attack\s*$")
    if not atk15 or atk15.get("targetSlide") != 19:
        failures.append(f"s015 Attack must →19 (Felled), got {atk15}")
    cont19 = hyperlink(19, r"continue")
    if not cont19 or cont19.get("targetSlide") != 25:
        failures.append(f"s019 Continue must →25 (x2 Attacks), got {cont19}")
    cont25 = hyperlink(25, r"continue")
    if not cont25 or cont25.get("targetSlide") != 21:
        failures.append(f"s025 Continue must →21 (×2 menu), got {cont25}")

    flee15 = hyperlink(15, r"^-?\s*flee\s*$")
    if not flee15 or flee15.get("targetSlide") != 17:
        failures.append(f"s015 Flee must →17 (CAN'T ESCAPE), got {flee15}")
    if flee15 and flee15.get("resolveMethod") == "user_authorized_target_override":
        failures.append("s015 Flee must not use user_authorized_target_override")
    cont17 = hyperlink(17, r"continue")
    if not cont17 or cont17.get("targetSlide") != 23:
        failures.append(f"s017 Continue must →23 (x3 Attacks), got {cont17}")
    if cont17 and cont17.get("resolveMethod") == "user_authorized_target_override":
        failures.append("s017 Continue must not use user_authorized_target_override")
    cont23 = hyperlink(23, r"continue")
    if not cont23 or cont23.get("targetSlide") != 24:
        failures.append(f"s023 Continue must →24 (×3 menu), got {cont23}")

    atk16 = hyperlink(16, r"^-?\s*attack\s*$")
    if not atk16 or atk16.get("targetSlide") != 33:
        failures.append(f"s016 Attack must →33, got {atk16}")

    notes.append(
        "count edges: Attack 15→19→25→21 (×3→×2); Flee 15→17→23→24 (×3→×3); "
        "boredom auto→16×2 authored; s016 Attack→33"
    )
    print(notes[-1], flush=True)


def exact_two_goblin_flee_regression(page, failures, notes) -> None:
    """End-to-end Attack (one fewer) and Flee (same count) first-combat paths."""

    def click_continue_when_ready(expect_slide: int, expect_next: int) -> bool:
        if cur(page) != expect_slide:
            failures.append(f"expected s{expect_slide:03d}, got s{cur(page):03d}")
            return False
        cont = None
        for _ in range(24):
            cont = page.evaluate(
                """() => {
                  const btn = [...document.querySelectorAll('#hotspots button.hotspot')]
                    .find((b) => /continue/i.test(b.getAttribute('aria-label') || ''));
                  if (!btn) return null;
                  const r = btn.getBoundingClientRect();
                  return {
                    x: r.x + r.width / 2,
                    y: r.y + r.height / 2,
                    pe: getComputedStyle(btn).pointerEvents,
                    disabled: btn.disabled,
                  };
                }"""
            )
            if cont and cont.get("pe") != "none" and not cont.get("disabled"):
                break
            page.click("#stage", position={"x": 40, "y": 40})
            page.wait_for_timeout(300)
            if cur(page) != expect_slide:
                failures.append(
                    f"left s{expect_slide:03d} while waiting for continue → s{cur(page):03d}"
                )
                return False
        if not cont:
            failures.append(f"s{expect_slide:03d} missing Continue")
            return False
        page.mouse.click(cont["x"], cont["y"])
        page.wait_for_timeout(700)
        if cur(page) != expect_next:
            failures.append(
                f"s{expect_slide:03d} Continue expected →{expect_next}, got s{cur(page):03d}"
            )
            return False
        return True

    # Attack: 15 → 19 → 25 → 21 (×2)
    goto(page, 15)
    page.evaluate("() => goblinsRpg3Debug.clearHistory()")
    info_atk = visual_option_center(page, "Attack")
    if not info_atk:
        failures.append("s015 missing visual Attack")
        return
    page.mouse.click(info_atk["x"], info_atk["y"])
    page.wait_for_timeout(600)
    if cur(page) != 19:
        failures.append(f"s015 Attack must enter s019, got s{cur(page):03d}")
        return
    if not click_continue_when_ready(19, 25):
        return
    if not click_continue_when_ready(25, 21):
        return
    if standing_goblin_count(21) != 2:
        failures.append(f"Attack path s021 expected ×2, got {standing_goblin_count(21)}")
    notes.append("Attack path: 15→19→25→21 (×3→×2)")
    print(notes[-1], flush=True)
    page.screenshot(path=str(OUT / "goblins-exact-attack-one-fewer.png"), full_page=False)

    # Flee: 15 → 17 → 23 → 24 (×3)
    goto(page, 15)
    page.evaluate("() => goblinsRpg3Debug.clearHistory()")
    info_flee = visual_option_center(page, "flee")
    if not info_flee:
        failures.append("s015 missing visual Flee")
        return
    page.mouse.click(info_flee["x"], info_flee["y"])
    page.wait_for_timeout(600)
    if cur(page) != 17:
        failures.append(f"s015 Flee must enter s017, got s{cur(page):03d}")
        return
    if not click_continue_when_ready(17, 23):
        return
    if not click_continue_when_ready(23, 24):
        return
    if standing_goblin_count(24) != 3:
        failures.append(f"Flee path s024 expected ×3, got {standing_goblin_count(24)}")
    notes.append("Flee path: 15→17→23→24 (×3→×3 same count)")
    print(notes[-1], flush=True)
    page.screenshot(path=str(OUT / "goblins-exact-flee-same-count.png"), full_page=False)


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

        assert_first_goblin_count_edges(failures, notes)

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
