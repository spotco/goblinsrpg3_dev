#!/usr/bin/env python3
"""Smoke: deck transition effectTypes used in this PPS have CSS + effectName coverage."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TM = json.loads((ROOT / "generated/timing_manifest.json").read_text())
CSS = (ROOT / "docs/styles.css").read_text()
APP = (ROOT / "docs/app.js").read_text()

# effectTypes present in this deck (non-cut)
used = sorted({int(t["effectType"]) for t in TM["transitions"] if int(t.get("effectType") or 0) != 0})
print("used effectTypes:", used)

failures = []
for et in used:
    name = next((t.get("effectName") for t in TM["transitions"] if int(t["effectType"]) == et), None)
    if not name or str(name).startswith("unknown_"):
        failures.append(f"effectType {et} missing effectName in timing_manifest")
    cls = f"transition-effect-{et}"
    if cls not in CSS:
        failures.append(f"CSS missing .{cls} for effectType {et} ({name})")
    # keyframes referenced
    m = re.search(rf"transition-effect-{et}[^{{]*\{{[^}}]*animation-name:\s*([a-z0-9-]+)", CSS)
    if not m:
        failures.append(f"CSS .{cls} has no animation-name")
    else:
        kf = m.group(1)
        if f"@keyframes {kf}" not in CSS and kf != "slide-fade-in":
            # slide-fade-in is the default; still should exist
            if f"@keyframes {kf}" not in CSS:
                failures.append(f"missing @keyframes {kf} for effect {et}")
        if f"@keyframes {kf}" not in CSS:
            failures.append(f"missing @keyframes {kf} for effect {et}")

if "transitionEffectClass" not in APP:
    failures.append("app.js missing transitionEffectClass")
if "applySlideTransition" not in APP:
    failures.append("app.js missing applySlideTransition")

# Combat-adjacent: s015 newsflash (22)
s15 = next(t for t in TM["transitions"] if t["slide"] == 15)
if int(s15["effectType"]) != 22 or s15.get("effectName") != "newsflash":
    failures.append(f"s015 expected newsflash/22, got {s15}")

if failures:
    print("FAIL")
    for f in failures:
        print(" ", f)
    sys.exit(1)
print("OK transition smoke:", ", ".join(f"{et}" for et in used))
