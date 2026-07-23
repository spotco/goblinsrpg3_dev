"""Analyze slides 1-10 for PPT features vs runtime coverage gaps."""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def walk_nodes(roots):
    stack = list(roots or [])
    while stack:
        node = stack.pop()
        yield node
        stack.extend(node.get("children") or [])


def behavior_strings(behavior):
    out = []
    for v in behavior.get("variants") or []:
        p = v.get("parsed") or {}
        if isinstance(p.get("stringValue"), str):
            out.append(p["stringValue"])
        elif "intValue" in p:
            out.append(f"int:{p['intValue']}")
    return out


def node_delay(node):
    delay = 0
    for c in node.get("conditions") or []:
        p = c.get("parsed") or {}
        d = p.get("delayMs")
        if isinstance(d, (int, float)) and d > delay:
            delay = d
    return delay


def main():
    game = load(ROOT / "docs" / "game-manifest.json")
    anim = load(ROOT / "docs" / "animation-manifest.json")
    layers = load(ROOT / "generated" / "layers.json")
    risks = load(ROOT / "generated" / "visual_risks.json") if (ROOT / "generated" / "visual_risks.json").exists() else {"risks": []}

    anim_by_slide = {int(s["slide"]): s for s in anim.get("slides") or []}
    layers_by_slide = {int(s["slide"]): s for s in layers.get("slides") or []}
    screens = {int(s["slide"]): s for s in game.get("screens") or []}

    report = {"slides": [], "aggregateGaps": Counter(), "featureInventory": Counter()}

    for slide in range(1, 11):
        screen = screens.get(slide) or {}
        layer_entry = layers_by_slide.get(slide) or {}
        anim_entry = anim_by_slide.get(slide)
        slide_layers = screen.get("layers") or layer_entry.get("layers") or []
        hotspots = screen.get("hotspots") or []
        transition = screen.get("transition") or {}

        kinds = Counter()
        strings = Counter()
        effect_names = Counter()
        set_props = Counter()
        animate_props = Counter()
        has_motion = False
        has_scale = False
        has_command = False
        has_filter = False
        has_color = False
        has_rotation = False
        waits_click = 0
        trigger_start_end = 0
        delays = []
        target_shapes = set()
        node_count = 0
        behavior_count = 0
        sequential = 0
        on_click_seq = 0
        iterate = 0
        wordart = []
        media = []
        self_links = []
        empty_text = []
        large_images = 0

        for layer in slide_layers:
            bounds = layer.get("bounds") or {}
            area = float(bounds.get("width") or 0) * float(bounds.get("height") or 0)
            if layer.get("type") == "image" and area >= 0.5:
                large_images += 1
            if layer.get("wordArt"):
                wordart.append({"shapeId": layer.get("shapeId"), "text": layer.get("text"), "shapeType": layer.get("shapeType")})
            if layer.get("type") == "text" and not str(layer.get("text") or "").strip() and not layer.get("wordArt"):
                if str(layer.get("shapeType") or "").startswith("TEXT_"):
                    empty_text.append(layer.get("shapeId"))

        if anim_entry:
            for node in walk_nodes(anim_entry.get("rootTimeNodes") or []):
                node_count += 1
                delays.append(node_delay(node))
                for c in node.get("conditions") or []:
                    p = c.get("parsed") or {}
                    if p.get("triggerEvent") in (9, 10):
                        waits_click += 1
                    if p.get("triggerObject") == 2 and p.get("triggerEvent") in (3, 4):
                        trigger_start_end += 1
                seq = (node.get("sequence") or {}).get("parsed") or {}
                if seq.get("usesConcurrency") and seq.get("concurrency") == 0:
                    sequential += 1
                if seq.get("usesNextAction") and seq.get("nextAction") == 1 and len(node.get("children") or []) > 1:
                    on_click_seq += 1
                if node.get("iterate") or any(
                    (v.get("parsed") or {}).get("stringValue") == "iterate" for v in node.get("variants") or []
                ):
                    iterate += 1
                # iterate data record presence
                if node.get("iterateData") or node.get("timeIterateData"):
                    iterate += 1
                for t in node.get("targets") or []:
                    if t.get("shapeId") is not None:
                        target_shapes.add(int(t["shapeId"]))
                for b in node.get("behaviors") or []:
                    behavior_count += 1
                    kind = b.get("kind") or "unknown"
                    kinds[kind] += 1
                    report["featureInventory"][f"behavior:{kind}"] += 1
                    bstrings = behavior_strings(b)
                    for s in bstrings:
                        strings[s] += 1
                    for t in b.get("targets") or []:
                        if t.get("shapeId") is not None:
                            target_shapes.add(int(t["shapeId"]))
                    if kind == "motion":
                        has_motion = True
                    if kind == "scale":
                        has_scale = True
                    if kind == "command":
                        has_command = True
                    if kind == "effect":
                        for s in bstrings:
                            if s not in ("",) and not s.startswith("int:"):
                                effect_names[s] += 1
                    if kind == "set":
                        for s in bstrings:
                            if s.startswith("ppt_") or s in ("style.visibility", "visible", "hidden"):
                                set_props[s] += 1
                            if "rotation" in s.lower() or "ppt_r" in s:
                                has_rotation = True
                            if "color" in s.lower() or "fillcolor" in s.lower():
                                has_color = True
                            if "filter" in s.lower():
                                has_filter = True
                    if kind == "animate":
                        for s in bstrings:
                            if s in ("ppt_x", "ppt_y", "ppt_w", "ppt_h"):
                                animate_props[s] += 1
                            if "rotation" in s.lower() or s == "ppt_r":
                                has_rotation = True
                            if "color" in s.lower():
                                has_color = True
                            if "filter" in s.lower() or s in ("opacity", "style.opacity"):
                                pass
                    # unknown / other kinds
                    if kind not in ("set", "effect", "animate", "motion", "scale", "command"):
                        report["featureInventory"][f"other-behavior:{kind}"] += 1

        for h in hotspots:
            if h.get("action") == "media" or h.get("mediaBindingId"):
                media.append(
                    {
                        "id": h.get("id"),
                        "status": h.get("behaviorStatus"),
                        "mediaBindingId": h.get("mediaBindingId"),
                        "shapeId": h.get("shapeId"),
                    }
                )
            if h.get("action") == "hyperlink" and h.get("targetSlide") == slide:
                self_links.append(h.get("id"))

        # Gaps relative to known runtime limitations
        gaps = []

        def gap(code, severity, detail):
            gaps.append({"code": code, "severity": severity, "detail": detail})
            report["aggregateGaps"][code] += 1

        # Effect types beyond fade/dissolve
        for name, count in effect_names.items():
            if name not in ("fade", "dissolve"):
                gap("effect_not_fade_dissolve", "high", f"{name} x{count}")
            else:
                report["featureInventory"][f"effect:{name}"] += count

        if has_motion:
            report["featureInventory"]["motion"] += 1
            # motion is implemented but path sampling may be endpoint-only
            gap("motion_endpoint_only", "medium", "motion paths present; runtime uses endpoint translate only")

        if has_scale:
            report["featureInventory"]["scale"] += 1

        if has_command:
            report["featureInventory"]["command"] += 1

        if has_rotation:
            gap("rotation_animation", "high", "rotation-related animate/set strings present")

        if has_color:
            gap("color_animation", "high", "color-related animate/set strings present")

        if has_filter:
            gap("filter_animation", "high", "filter-related behavior present")

        # multi-keyframe animate with empty string separators already handled; check property coverage
        for prop in animate_props:
            report["featureInventory"][f"animate:{prop}"] += animate_props[prop]

        # set metric vs visibility
        for prop, count in set_props.items():
            report["featureInventory"][f"set:{prop}"] += count

        # click-gated main sequences on non-autoplay slides
        if waits_click and slide != 1:
            gap(
                "click_gated_sequence",
                "medium",
                f"{waits_click} OnNext/OnPrev conditions; only slide 1 autoplays through them",
            )

        if trigger_start_end:
            report["featureInventory"]["chained_triggers"] += trigger_start_end

        if sequential:
            report["featureInventory"]["sequential_children"] += sequential

        if on_click_seq:
            gap("on_click_child_sequence", "medium", f"{on_click_seq} sequences queue children for click")

        if iterate:
            gap("time_iterate", "high", "iterate/paragraph build timing present")

        # WordArt geometry styles beyond flat text
        for w in wordart:
            st = str(w.get("shapeType") or "")
            if st and st not in ("TEXT_PLAIN_TEXT", "TEXT_BOX"):
                gap("wordart_geometry", "medium", f"shape {w.get('shapeId')} type {st} text={w.get('text')!r}")

        if empty_text:
            gap("empty_wordart_or_text", "medium", f"shapeIds={empty_text}")

        if not large_images and slide not in (1, 2):
            # title slides often sparse
            gap("sparse_or_no_fullbleed", "low", f"large image layers={large_images}, layers={len(slide_layers)}")

        if self_links:
            gap("self_hyperlink", "high", f"hotspots={self_links}")

        for m in media:
            if m.get("status") not in ("clickable_media", "navigation"):
                if "unresolved" in str(m.get("status") or "") or m.get("status") == "missing_media_binding":
                    gap("unresolved_media", "high", m)
                else:
                    report["featureInventory"][f"media:{m.get('status')}"] += 1
            else:
                report["featureInventory"]["media_mapped"] += 1

        # transition effects
        et = transition.get("effectType")
        if et not in (None, 0):
            report["featureInventory"][f"transition_effectType:{et}"] += 1
            # runtime supports subset of effect types via CSS classes
            supported = {0, 3, 11, 21, 22, 23, 27}
            if et not in supported:
                gap("transition_effect_unmapped", "medium", f"effectType={et} direction={transition.get('effectDirection')}")

        if transition.get("flagNames") and "autoAdvance" in (transition.get("flagNames") or []):
            report["featureInventory"]["autoAdvance"] += 1

        # master / background
        bg = screen.get("backgroundColor") or layer_entry.get("backgroundColor")
        if bg:
            report["featureInventory"]["solid_background"] += 1

        # animation targets missing layers
        layer_ids = {int(L["shapeId"]) for L in slide_layers if L.get("shapeId") is not None}
        missing_targets = sorted(sid for sid in target_shapes if sid not in layer_ids)
        if missing_targets:
            gap("animation_target_missing_layer", "high", f"shapeIds={missing_targets}")

        # Record counts from anim entry
        record_counts = (anim_entry or {}).get("recordCounts") or {}
        if record_counts.get("RT_TimeAnimateBehavior") or record_counts.get("RT_TimeAnimateBehaviorContainer"):
            pass
        if record_counts.get("RT_TimeRotationBehavior") or record_counts.get("RT_TimeColorBehavior"):
            gap("special_time_behavior_records", "high", {k: record_counts[k] for k in record_counts if "Rotation" in k or "Color" in k or "Filter" in k or "Command" in k})

        # any non-standard record types
        interesting_records = {
            k: v
            for k, v in record_counts.items()
            if any(
                key in k
                for key in (
                    "Rotation",
                    "Color",
                    "Filter",
                    "Motion",
                    "Command",
                    "Iterate",
                    "ParaBuild",
                    "Build",
                    "Sequence",
                )
            )
        }

        slide_risks = [r for r in risks.get("risks") or [] if r.get("slide") == slide]

        report["slides"].append(
            {
                "slide": slide,
                "layerCount": len(slide_layers),
                "hotspotCount": len(hotspots),
                "transition": {
                    "effectType": transition.get("effectType"),
                    "effectDirection": transition.get("effectDirection"),
                    "slideTimeMs": transition.get("slideTimeMs"),
                    "flagNames": transition.get("flagNames"),
                },
                "backgroundColor": bg,
                "animation": {
                    "present": anim_entry is not None,
                    "nodeCount": node_count,
                    "behaviorCount": behavior_count,
                    "behaviorKinds": dict(kinds),
                    "effectNames": dict(effect_names),
                    "setProps": dict(set_props),
                    "animateProps": dict(animate_props),
                    "waitsClickConditions": waits_click,
                    "triggerStartEnd": trigger_start_end,
                    "maxDelayMs": max(delays) if delays else 0,
                    "interestingRecords": interesting_records,
                    "targetShapeCount": len(target_shapes),
                },
                "wordArt": wordart,
                "media": media,
                "gaps": gaps,
                "visualRiskCodes": sorted({r.get("code") for r in slide_risks}),
            }
        )

    # summarize gap priorities
    report["aggregateGaps"] = dict(report["aggregateGaps"].most_common())
    report["featureInventory"] = dict(report["featureInventory"].most_common())
    out = ROOT / "generated" / "slide_1_10_feature_gaps.json"
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {out}")
    print("\n=== Per-slide gaps ===")
    for s in report["slides"]:
        print(f"\nSlide {s['slide']:02d}: layers={s['layerCount']} hotspots={s['hotspotCount']} animNodes={s['animation']['nodeCount']} kinds={s['animation']['behaviorKinds']}")
        print(f"  transition={s['transition']} effects={s['animation']['effectNames']}")
        if s["wordArt"]:
            print(f"  wordArt={s['wordArt']}")
        if s["media"]:
            print(f"  media={s['media']}")
        for g in s["gaps"]:
            print(f"  [{g['severity']}] {g['code']}: {g['detail']}")
    print("\n=== Aggregate gaps ===")
    for k, v in report["aggregateGaps"].items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
