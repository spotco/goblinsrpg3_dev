#!/usr/bin/env python3
"""Regression: result beats autoplay entrances; slide nav stays click-gated; flee reloads.

Discovered 2026-09-11 / overturned 2026-09-12:
  - s015 Attack→18 (PPT CAN'T ESCAPE + motion paths). With autoplay disabled on
    continue-only slides, Attack landed on entrance-hidden layers (empty debug
    outlines / "green boxes") until a stage click. Restore continue-only OnNext
    autoplay so attack motion/text play on arrival. Slide *navigation* still
    requires the continue hyperlink (29/30/31 must not auto-nav).
  - s015 -flee is a binary self-hyperlink (residual_self_reload): clickable reload
    replays slide anims — do not invent flee→17.

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
    # Continue/result beats SHOULD autoplay in-slide OnNext (so Attack→result is not blank),
    # but must NOT auto-navigate to another slide.
    if cur(page) != slide:
        fail(f"s{slide:03d} left immediately on enter → {cur(page)}")
        return
    if not autoplay_flag(page):
        # Soft signal: entrance may stay blank without autoplay.
        print(f"WARN s{slide:03d} autoplay=false (continue/result usually autoplays entrances)")
    # Wait for autoplay to reveal continue (or stage-click if still gated).
    enabled = False
    for i in range(24):
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
        # If still awaiting reveal after autoplay window, try a stage click (multi-beat).
        if i >= 8:
            page.click("#stage", position={"x": 40, "y": 40})
        page.wait_for_timeout(350)
        if cur(page) != slide:
            fail(f"s{slide:03d} auto-navigated while waiting for continue → {cur(page)}")
            return
    if not enabled:
        fail(f"s{slide:03d} continue hotspot never enabled (autoplay/stage)")
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
        return
    # Reload must re-enter and replay entrance (title text briefly re-hides / fades).
    replayed = page.evaluate(
        """() => {
          const h = goblinsRpg3Debug.history() || [];
          const same = h.filter((e) => e.result === 'navigate-to-same-screen' || e.detail === 'navigate-to-same-screen');
          const enters = h.filter((e) => e.kind === 'slide' && e.detail === 'enter' && e.targetSlide === 15);
          return { same: same.length, enters: enters.length };
        }"""
    )
    if replayed.get("same", 0) < 1 or replayed.get("enters", 0) < 2:
        fail(f"s015 flee did not visibly re-enter slide (history={replayed})")
    else:
        print("OK s015 flee reloads self (no invent-bridge to 17; slide re-entered)")


def assert_attack_shows_anim(page) -> None:
    """Attack→18 must show motion/text without an extra stage click (not empty green boxes)."""
    goto(page, 15)
    page.wait_for_timeout(400)
    click_layer_center(page, OPTION_ATTACK)
    page.wait_for_timeout(200)
    if cur(page) != 18:
        fail(f"s015 Attack expected →18, got {cur(page)}")
        return
    if not autoplay_flag(page):
        fail("s018 after Attack should autoplay OnNext entrances (else blank/green-box phase)")
        return
    # Within ~1.5s some attack motion target or result text must be visible.
    seen = False
    for _ in range(8):
        page.wait_for_timeout(250)
        info = page.evaluate(
            """() => {
          const layers = [...document.querySelectorAll('#layers .layer')].map((el) => ({
            id: el.dataset.shapeId,
            text: (el.textContent || '').trim(),
            vis: getComputedStyle(el).visibility,
            op: parseFloat(getComputedStyle(el).opacity || '0'),
          }));
          // Motion-path cast (23555/23556) or result caption — not static props.
          const motion = layers.filter((l) => (l.id === '23555' || l.id === '23556') && l.vis === 'visible' && l.op > 0.15);
          const visibleText = layers.filter((l) => l.text && l.vis === 'visible' && l.op > 0.2);
          return { motion: motion.map((l) => l.id), visibleText: visibleText.map((l) => l.text), slide: goblinsRpg3Debug.snapshot().currentScreen.slide };
        }"""
        )
        if info.get("slide") != 18:
            fail(f"left s018 during attack anim wait → {info.get('slide')}")
            return
        if info.get("motion") or info.get("visibleText"):
            seen = True
            break
    if not seen:
        fail("s018 after Attack stayed empty (no visible motion/text within ~2s; green-box regression)")
    else:
        print(f"OK s015 Attack → 18 with visible entrance (autoplay)")


def assert_attack_and_boredom(page) -> None:
    assert_attack_shows_anim(page)

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
