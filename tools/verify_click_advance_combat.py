#!/usr/bin/env python3
"""Regression: result beats autoplay entrances; slide nav stays click-gated.

DocSummary slideId resolution (2026-09-13):
  - s015 Attack→19 (Felled) with autoplay OnNext entrances on result beats.
  - s015 Flee→17 (CAN'T ESCAPE) — not residual self; stale label "Slide 15" lied.
  - Slide *navigation* still requires continue hyperlink (29/30/31 must not auto-nav).

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
    page.wait_for_function(
        "() => !document.getElementById('stage')?.classList.contains('is-transitioning')",
        timeout=5000,
    )


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


def assert_flee_to_cant_escape(page) -> None:
    goto(page, 15)
    page.wait_for_timeout(400)
    meta = page.evaluate(
        r"""() => {
      const btn = [...document.querySelectorAll('#hotspots button.hotspot')].find((b) =>
        /^\s*-?\s*flee\s*$/i.test(b.getAttribute('aria-label') || '')
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
        fail("s015 flee hotspot missing")
        return
    if meta.get("target") != "slide-017":
        fail(f"s015 flee target should be slide-017, got {meta.get('target')}")
    click_layer_center(page, OPTION_FLEE)
    page.wait_for_timeout(400)
    if cur(page) != 17:
        fail(f"s015 flee should navigate to slide 17, got {cur(page)}")
    else:
        print("OK s015 flee → 17 (CAN'T ESCAPE; slideId-resolved)")


def assert_attack_shows_anim(page) -> None:
    """Attack→19 must show motion/text without an extra stage click (not empty green boxes).

    Also: left goblin (shape 24584) is exit-only (blinds) and must be visible at land,
    not entrance-pre-hidden (guy+slash-only regression after hyperlink fix).
    """
    goto(page, 15)
    page.wait_for_timeout(400)
    click_layer_center(page, OPTION_ATTACK)
    page.wait_for_timeout(120)
    if cur(page) != 19:
        fail(f"s015 Attack expected →19, got {cur(page)}")
        return
    if not autoplay_flag(page):
        fail("s019 after Attack should autoplay OnNext entrances (else blank/green-box phase)")
        return
    # Goblin is exit-only: must be visible immediately (before ~500ms hide-after).
    goblin = page.evaluate(
        """() => {
          const el = document.querySelector('#layers .layer[data-shape-id="24584"]');
          if (!el) return { missing: true };
          const cs = getComputedStyle(el);
          const r = el.getBoundingClientRect();
          return {
            vis: cs.visibility,
            op: parseFloat(cs.opacity || '0'),
            display: cs.display,
            pureGreen: el.dataset.pureGreenPlaceholder || el.classList.contains('pure-green-placeholder'),
            left: r.left,
            width: r.width,
          };
        }"""
    )
    if goblin.get("missing"):
        fail("s019 missing left goblin layer shape 24584")
    elif goblin.get("pureGreen") in (True, "true", "1"):
        fail("s019 left goblin wrongly tagged pure-green-placeholder")
    elif goblin.get("vis") != "visible" or float(goblin.get("op") or 0) < 0.15:
        fail(f"s019 left goblin not visible at Attack land (exit-only must not be entrance-hidden): {goblin}")
    elif float(goblin.get("width") or 0) < 8:
        fail(f"s019 left goblin has no layout width: {goblin}")
    else:
        print("OK s019 left goblin visible at Attack land (exit-only)")

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
          // Felled result caption or any visible text/image entrance on s019.
          const motion = layers.filter((l) => l.vis === 'visible' && l.op > 0.15 && (l.id || l.text));
          const visibleText = layers.filter((l) => l.text && l.vis === 'visible' && l.op > 0.2);
          return { motion: motion.map((l) => l.id), visibleText: visibleText.map((l) => l.text), slide: goblinsRpg3Debug.snapshot().currentScreen.slide };
        }"""
        )
        if info.get("slide") != 19:
            fail(f"left s019 during attack anim wait → {info.get('slide')}")
            return
        if info.get("motion") or info.get("visibleText"):
            seen = True
            break
    if not seen:
        fail("s019 after Attack stayed empty (no visible motion/text within ~2s; green-box regression)")
    else:
        print(f"OK s015 Attack → 19 with visible entrance (autoplay)")

    # After blinds (~500ms) + hide-after (499ms) the felled goblin should fade/blinds out.
    page.wait_for_timeout(900)
    after = page.evaluate(
        """() => {
          const el = document.querySelector('#layers .layer[data-shape-id="24584"]');
          if (!el) return { missing: true };
          const cs = getComputedStyle(el);
          return { vis: cs.visibility, op: parseFloat(cs.opacity || '0') };
        }"""
    )
    if after.get("missing"):
        fail("s019 lost left goblin layer during blinds exit")
    elif after.get("vis") == "visible" and float(after.get("op") or 0) > 0.2:
        fail(f"s019 left goblin should blinds-exit (opacity→0 / hidden) after ~1s: {after}")
    else:
        print("OK s019 left goblin blinds-exited after kill")


def _layer_state(page, shape_id: int) -> dict:
    return page.evaluate(
        """(sid) => {
          const el = document.querySelector(`#layers .layer[data-shape-id="${sid}"]`);
          if (!el) return { missing: true };
          const cs = getComputedStyle(el);
          const r = el.getBoundingClientRect();
          return {
            vis: cs.visibility,
            op: parseFloat(cs.opacity || '0'),
            width: r.width,
            height: r.height,
          };
        }""",
        shape_id,
    )


def assert_counter_goblins_visible(page) -> None:
    """s023/s025/s032 goblin pics are motion-only (no entrance); must be visible at land."""
    cases = (
        (23, (29701, 29703, 29704), "x3 Attacks"),
        (25, (32771, 32772), "x2 Attacks"),
        (32, (39939, 39940), "x2 Attacks"),
    )
    for slide, shape_ids, label in cases:
        goto(page, slide)
        page.wait_for_timeout(80)
        if cur(page) != slide:
            fail(f"goto s{slide:03d} landed on {cur(page)}")
            continue
        missing = []
        hidden = []
        for sid in shape_ids:
            st = _layer_state(page, sid)
            if st.get("missing"):
                missing.append(sid)
            elif st.get("vis") != "visible" or float(st.get("op") or 0) < 0.15 or float(st.get("width") or 0) < 8:
                hidden.append((sid, st))
        if missing:
            fail(f"s{slide:03d} {label} missing goblin layers {missing}")
        elif hidden:
            fail(f"s{slide:03d} {label} goblins hidden at land (motion-only must not be pre-hidden): {hidden}")
        else:
            print(f"OK s{slide:03d} {label} goblins visible at land (motion-only)")


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
    if not flee.get("clickable") or flee.get("targetSlide") != 17:
        fail(f"manifest s015 flee should be clickable →17, got {flee}")
    if flee.get("resolveMethod") == "user_authorized_target_override":
        fail("s015 flee must not use target override")
    for slide in (29, 30, 31):
        s = next(x for x in GM["screens"] if x["slide"] == slide)
        if s.get("advancement", {}).get("autoAdvance"):
            fail(f"s{slide:03d} must not have autoAdvance")
    print("OK manifest policy (flee→17; 29/30/31 no autoAdvance)")


def main() -> int:
    assert_manifest_policy()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        assert_chapter_jump(page)
        for slide in (29, 30, 31):
            assert_no_auto_nav(page, slide, seconds=5.0)
        # 29 continue → 30 (self_continue_to_next); 31 continue → 30 (slideId-resolved; stale label Slide 29)
        assert_click_gated_continue(page, 29, 30)
        assert_click_gated_continue(page, 31, 30)
        assert_flee_to_cant_escape(page)
        assert_attack_and_boredom(page)
        assert_counter_goblins_visible(page)
        browser.close()
    if failures:
        print(f"\n{len(failures)} failure(s)")
        return 1
    print("\nAll click-advance / combat residual checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
