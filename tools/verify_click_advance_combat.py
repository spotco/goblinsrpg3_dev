#!/usr/bin/env python3
"""Regression: continue/result slides stay click-gated; combat self-flee reloads.

Discovered 2026-09-11:
  - User saw 29→30→31 "advancing automatically". Root cause: screenShouldAutoplayAnimations
    treated continue-only slides as autoplay, so OnNext builds ran without clicks and
    felt like free slide advances. Fix: autoplay only when advancement.autoAdvance.
  - s015 -flee is a binary self-hyperlink. Muting it as non-clickable diverged from PPT
    (self-link reloads the slide). Fix: residual_self_reload stays clickable → same slide.

This script fails if those regressions return.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8765"
ROOT = Path(__file__).resolve().parents[1]
GM = json.loads((ROOT / "docs/game-manifest.json").read_text())
OPTION_FLEE = re.compile(r"^\s*-?\s*flee\s*$", re.I)
OPTION_ATTACK = re.compile(r"^\s*-?\s*attack\s*$", re.I)
CONTINUE_RE = re.compile(r"click here.*continue", re.I)

failures: list[str] = []


def fail(msg: str) -> None:
    failures.append(msg)
    print(f"FAIL: {msg}")


def wait_ready(page) -> None:
    page.wait_for_function(
        "() => window.goblinsRpg3Debug && goblinsRpg3Debug.snapshot && document.querySelector('#stage')",
        timeout=25000,
    )
    page.wait_for_timeout(200)


def goto(page, slide: int) -> None:
    page.goto(f"{BASE}/?debug=1&slide={slide}", wait_until="domcontentloaded")
    wait_ready(page)
    page.evaluate("() => { try { goblinsRpg3Debug.setHudCollapsed(true); } catch (e) {} }")


def cur(page) -> int:
    return page.evaluate("() => goblinsRpg3Debug.snapshot().currentScreen.slide")


def autoplay_flag(page) -> bool:
    return page.evaluate(
        """() => {
      const h = (goblinsRpg3Debug.history() || [])
        .filter((e) => e.kind === 'slide' && e.detail === 'enter')
        .slice(-1)[0];
      if (h && typeof h.autoplay === 'boolean') return h.autoplay;
      const dump = goblinsRpg3Debug.dumpScreen();
      return Boolean(dump && dump.renderDecision && dump.renderDecision.autoplayAnimations);
    }"""
    )


def queue_len(page) -> int:
    return page.evaluate(
        """() => {
      const h = (goblinsRpg3Debug.history() || []).slice(-1)[0];
      return (h && typeof h.queueLen === 'number') ? h.queueLen : 0;
    }"""
    )


def click_layer_center(page, pattern: re.Pattern[str]) -> dict:
    info = page.evaluate(
        """(pattern) => {
      const re = new RegExp(pattern, 'i');
      const layer = [...document.querySelectorAll('#layers .layer')].find((el) =>
        re.test((el.textContent || '').trim())
      );
      const btn = [...document.querySelectorAll('#hotspots button.hotspot')].find((b) =>
        re.test(b.getAttribute('aria-label') || '')
      );
      const el = layer || btn;
      if (!el) return { ok: false, reason: 'missing' };
      const r = el.getBoundingClientRect();
      return {
        ok: true,
        x: r.left + r.width / 2,
        y: r.top + r.height / 2,
        pe: btn ? getComputedStyle(btn).pointerEvents : null,
        disabled: btn ? btn.disabled : null,
        aria: btn ? btn.getAttribute('aria-label') : null,
      };
    }""",
        pattern.pattern,
    )
    if not info.get("ok"):
        return info
    page.mouse.click(info["x"], info["y"])
    page.wait_for_timeout(250)
    return info


def assert_no_auto_nav(page, slide: int, seconds: float = 5.0) -> None:
    goto(page, slide)
    page.wait_for_timeout(300)
    trail = []
    steps = max(1, int(seconds / 0.5))
    for _ in range(steps):
        page.wait_for_timeout(500)
        trail.append(cur(page))
    if any(s != slide for s in trail):
        fail(f"s{slide:03d} auto-navigated without click: {trail}")
    else:
        print(f"OK s{slide:03d} stayed put for {seconds}s")


def assert_click_gated_continue(page, slide: int, expected_target: int) -> None:
    goto(page, slide)
    page.wait_for_timeout(300)
    if autoplay_flag(page):
        fail(f"s{slide:03d} should NOT autoplay OnNext (continue/result beat)")
    # OnNext should be queued (or become visible after stage clicks).
    q0 = queue_len(page)
    # Stage click should consume animation, not leave the slide.
    page.click("#stage", position={"x": 40, "y": 40})
    page.wait_for_timeout(400)
    if cur(page) != slide:
        fail(f"s{slide:03d} left on stage click (expected OnNext only); now {cur(page)}")
        return
    # Keep clicking stage until continue hotspot is hittable (cap ~8s of builds).
    enabled = False
    for _ in range(20):
        info = page.evaluate(
            """() => {
          const btn = [...document.querySelectorAll('#hotspots button.hotspot')].find((b) =>
            /continue/i.test(b.getAttribute('aria-label') || '')
          );
          if (!btn) return null;
          return {
            pe: getComputedStyle(btn).pointerEvents,
            disabled: btn.disabled,
            awaits: btn.dataset.awaitsReveal || null,
          };
        }"""
        )
        if info and info.get("pe") != "none" and not info.get("disabled"):
            enabled = True
            break
        page.click("#stage", position={"x": 40, "y": 40})
        page.wait_for_timeout(350)
        if cur(page) != slide:
            fail(f"s{slide:03d} left during OnNext stage clicks → {cur(page)}")
            return
    if not enabled:
        fail(f"s{slide:03d} continue hotspot never enabled after stage clicks (q0={q0})")
        return
    before = cur(page)
    click_layer_center(page, CONTINUE_RE)
    after = cur(page)
    if after != expected_target:
        fail(f"s{slide:03d} continue expected →{expected_target}, got {after} (from {before})")
    else:
        print(f"OK s{slide:03d} click-gated continue → {expected_target}")


def assert_flee_reloads(page) -> None:
    goto(page, 15)
    page.wait_for_timeout(400)
    # Flee must be a rendered clickable hotspot targeting self.
    meta = page.evaluate(
        """() => {
      const btn = [...document.querySelectorAll('#hotspots button.hotspot')].find((b) =>
        /^\\s*-?\\s*flee\\s*$/i.test(b.getAttribute('aria-label') || '')
      );
      return btn
        ? {
            aria: btn.getAttribute('aria-label'),
            target: btn.dataset.target,
            pe: getComputedStyle(btn).pointerEvents,
          }
        : null;
    }"""
    )
    if not meta:
        fail("s015 flee hotspot missing (should be residual_self_reload clickable)")
        return
    if meta.get("target") != "slide-015":
        fail(f"s015 flee target should be slide-015, got {meta.get('target')}")
    click_layer_center(page, OPTION_FLEE)
    page.wait_for_timeout(300)
    if cur(page) != 15:
        fail(f"s015 flee should reload slide 15, navigated to {cur(page)}")
        return
    # Must not invent flee→17
    hist = page.evaluate("() => (goblinsRpg3Debug.history() || []).slice(-6)")
    jumped_17 = any(
        (h.get("targetSlide") == 17) or ((h.get("to") or {}).get("slide") == 17) for h in hist
    )
    if jumped_17:
        fail("s015 flee invented navigation to slide 17")
    else:
        print("OK s015 flee reloads self (no invent-bridge to 17)")


def assert_attack_and_boredom(page) -> None:
    goto(page, 15)
    page.wait_for_timeout(300)
    click_layer_center(page, OPTION_ATTACK)
    if cur(page) != 18:
        fail(f"s015 Attack expected →18, got {cur(page)}")
    else:
        print("OK s015 Attack → 18")

    goto(page, 15)
    # Boredom auto-advance is authored (9s). Allow generous margin.
    page.wait_for_timeout(9500)
    if cur(page) != 16:
        fail(f"s015 boredom auto-advance expected →16 after ~9s, got {cur(page)}")
    else:
        print("OK s015 boredom auto → 16")


def assert_chapter_jump(page) -> None:
    entries = json.loads((ROOT / "docs/chapter-entries.json").read_text())
    hit = [e for e in entries.get("entries") or [] if e.get("id") == "first-goblin-battle"]
    if not hit:
        fail("chapter-entries missing first-goblin-battle")
        return
    if hit[0].get("slide") not in (14, 15):
        fail(f"first-goblin-battle slide should be 14 or 15, got {hit[0].get('slide')}")
    goto(page, int(hit[0]["slide"]))
    if cur(page) != int(hit[0]["slide"]):
        fail("chapter jump URL did not land on goblin battle entry")
    else:
        print(f"OK chapter jump entry s{hit[0]['slide']:03d}")


def assert_manifest_policy() -> None:
    s15 = next(s for s in GM["screens"] if s["slide"] == 15)
    flee = next(
        h
        for h in s15["hotspots"]
        if OPTION_FLEE.match(str(h.get("shapeText") or ""))
    )
    if flee.get("behaviorStatus") != "residual_self_reload":
        fail(f"manifest s015 flee behaviorStatus={flee.get('behaviorStatus')}")
    if not flee.get("clickable") or flee.get("targetSlide") != 15:
        fail(f"manifest s015 flee should be clickable self, got {flee}")
    for slide in (29, 30, 31):
        s = next(x for x in GM["screens"] if x["slide"] == slide)
        if s.get("advancement", {}).get("autoAdvance"):
            fail(f"s{slide:03d} must not have autoAdvance")
    print("OK manifest policy (flee reload; 29/30/31 no autoAdvance)")


def main() -> int:
    assert_manifest_policy()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        assert_chapter_jump(page)
        for slide in (29, 30, 31):
            assert_no_auto_nav(page, slide, seconds=5.0)
        # 29 continue → 30 (self_continue_to_next); 31 continue → 29 (binary)
        assert_click_gated_continue(page, 29, 30)
        assert_click_gated_continue(page, 31, 29)
        assert_flee_reloads(page)
        assert_attack_and_boredom(page)
        browser.close()
    if failures:
        print(f"\n{len(failures)} failure(s)")
        return 1
    print("\nAll click-advance / combat residual checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
