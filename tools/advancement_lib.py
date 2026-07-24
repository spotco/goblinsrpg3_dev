"""Classify PowerPoint slide advancement for the browser port.

Policy (from PLAN.md + MS-PPT SSSlideInfoAtom flag bits):
- ``autoAdvance`` bit → timer-based next sequential slide
- ``manualAdvance`` bit → stage click advances to next sequential slide
  *after* the animation OnNext queue is empty
- neither bit → stage click does **not** change slides (hyperlinks/media only)
- Hyperlinks always work via hotspots regardless of flags

Self-links (ExHyperlink label ``Slide N`` matching source) are confirmed at the
binary level (no separate target atom). The port applies a documented
**playability resolve** for continue/start, sole-image self-links, and the
special case of **all-self combat menus** so the graph is leave-able without
editing the ``.pps``. Provenance is stored on hotspots
(``originalTargetSlide``, ``resolveMethod``).

Combat all-self → next (e.g. s046 Ubergoblin)
---------------------------------------------
Binary labels every combat option as ``Slide 46``. The next sequential slide
is the authored death cutscene (15 damage, player dead) then the story
continues. There are no alternate win/flee outcome slides for this fight in
the file, no inbound hyperlinks to 46 (entry is 45 auto-advance), and working
combats elsewhere *do* branch to non-self targets. Partial combat selfs on
other slides (one option self, others leave) are **not** bulk-promoted.
"""

from __future__ import annotations

import re
from typing import Any

CONTINUE_TEXT_RE = re.compile(
    r"(click\s*here|click\s*to|continue|to\s*start|\bstart\b)",
    re.IGNORECASE,
)
COMBAT_TEXT_RE = re.compile(
    r"^\s*-?\s*(attack|flee|limit|magic)\s*$",
    re.IGNORECASE,
)
DEATH_TEXT_MARKERS = (
    "ded!!",
    "you ded",
    "press esc to exit",
)

# Why: ExHyperlink has no separate target atom; all options label self.
# Sequential next is the only authored outcome (scripted death cutscene).
RESOLVE_COMBAT_ALL_SELF = "combat_all_self_to_next_outcome"
RESOLVE_NOOP_MIRROR = "noop_mirror_sibling_hyperlink"
RESOLVE_NOOP_CONTINUE = "noop_continue_to_next"


def normalize_option_text(text: str | None) -> str:
    """Normalize continue/combat labels for sibling matching."""
    if not text:
        return ""
    t = str(text).strip().lower()
    t = t.replace("…", "").replace("...", "").strip(" .")
    t = " ".join(t.split())
    return t


def apply_media_residual_policy(hotspots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Document unresolved / zero-area media; keep non-clickable (no fake audio).

    Legacy cue ids 3/4 are missing from the embedded sound collection. Zero-area
    mapped media (clamped bounds) still carries audio for automatic anim play but
    is not a usable hit target.
    """
    for h in hotspots:
        if h.get("action") != "media" and not h.get("mediaBindingId"):
            continue
        status = h.get("behaviorStatus") or h.get("mediaStatus")
        if status == "unresolved_media" or h.get("mediaStatus") == "unresolved_audio_id":
            h["clickable"] = False
            h["enabled"] = False
            h["residualStatus"] = "accepted_unresolved_media"
            h["residualKind"] = "missing_legacy_audio_cue"
            h["behaviorStatus"] = "documented_unresolved_media"
            if not h.get("resolveRationale"):
                h["resolveRationale"] = (
                    "Media action references a legacy animation cue id that is not "
                    "present in converted embedded/linked audio (known missing ids 3/4). "
                    "Left non-clickable; no invented sound mapping."
                )
        elif status == "mapped_media_zero_area":
            h["clickable"] = False
            h["enabled"] = False
            h["residualStatus"] = "accepted_zero_area_media"
            h["residualKind"] = "zero_area_mapped_media"
            h["behaviorStatus"] = "documented_zero_area_media"
            if not h.get("resolveRationale"):
                h["resolveRationale"] = (
                    "Media is mapped to a known audio cue but client-anchor bounds "
                    "clamp to zero width/height. Non-clickable hit target; automatic "
                    "animation playFrom may still fire from the timing tree."
                )
    return hotspots


def terminal_kind_for_screen(
    *,
    death_terminal: bool,
    layer_texts: list[str] | None,
    leave_paths: list[str] | None,
) -> str | None:
    if not death_terminal:
        return None
    joined = " ".join(str(t).lower() for t in (layer_texts or []) if t)
    if "the end" in joined or "end." in joined:
        return "end_card"
    if "ded" in joined or "you ded" in joined:
        return "death"
    if "restart_only" in (leave_paths or []):
        return "death"
    return "terminal"


def apply_residual_self_policy(hotspots: list[dict[str, Any]], slide: int) -> list[dict[str, Any]]:
    """Document binary residual selfs and disable click when the slide can still leave.

    Partial combat selfs (e.g. flee self while attack navigates) and image selfs on
    multi-exit hubs stay at target==source in the manifest (inventory-faithful) but
    become non-clickable so players use working leave paths. Provenance fields:
    residualStatus, resolveRationale, behaviorStatus=documented_residual_self.
    """
    has_leave = False
    for h in hotspots:
        if h.get("action") == "hyperlink" and h.get("targetSlide") is not None:
            if int(h["targetSlide"]) != slide and h.get("clickable", True):
                has_leave = True
                break
        if h.get("action") == "media" and h.get("clickable"):
            has_leave = True
            break
    # auto/stage leave is applied later in advancement; also treat non-self hyperlink
    # even if not yet clickable
    if not has_leave:
        for h in hotspots:
            if h.get("action") == "hyperlink" and h.get("targetSlide") is not None:
                if int(h["targetSlide"]) != slide:
                    has_leave = True
                    break

    for h in hotspots:
        if h.get("action") != "hyperlink" or h.get("targetSlide") is None:
            continue
        if int(h["targetSlide"]) != slide:
            continue
        method = str(h.get("resolveMethod") or "confirmed_self_label_match")
        is_combat = method == "confirmed_self_combat" or is_combat_like_text(
            str(h.get("shapeText") or "")
        )
        kind = "partial_combat_self" if is_combat else "hub_image_self"
        h["residualStatus"] = "accepted_source_self"
        h["residualKind"] = kind
        if not h.get("resolveMethod"):
            h["resolveMethod"] = (
                "confirmed_self_combat" if is_combat else "confirmed_self_label_match"
            )
        if not h.get("resolveRationale"):
            if is_combat:
                h["resolveRationale"] = (
                    "Binary ExHyperlink labels this combat option as this slide. "
                    "Other options or auto-advance still leave. Accepted residual — "
                    "do not invent flee/attack targets without PPT UI oracle."
                )
            else:
                h["resolveRationale"] = (
                    "Binary self-hyperlink on a multi-exit hub (no shape text). "
                    "Other hotspots navigate. Accepted residual — left non-clickable."
                )
        if has_leave:
            h["clickable"] = False
            h["enabled"] = False
            h["behaviorStatus"] = "documented_residual_self"
        else:
            # Would stuck the slide if disabled; keep clickable self for visibility
            h["behaviorStatus"] = "documented_residual_self_only_leave"
    return hotspots


def resolve_explicit_noop(
    *,
    slide: int,
    shape_text: str | None,
    next_slide: int | None,
    sibling_hyperlinks: list[dict[str, Any]],
) -> dict[str, Any]:
    """Promote binary action=none hotspots when labels imply navigation.

    1. If shape text matches a sibling hyperlink on the same slide, mirror that
       target (duplicate hitbox; common for -attack/-limit and double continues).
    2. Else if continue/start-like text and next exists, go to next sequential
       (sole leave control, e.g. damage interstitials s155/158/163).
    3. Else leave as explicit_noop (decorative dead zone).
    """
    norm = normalize_option_text(shape_text)
    if norm:
        for sib in sibling_hyperlinks:
            if normalize_option_text(sib.get("shapeText") or sib.get("label")) == norm:
                target = sib.get("targetSlide")
                if target is None:
                    continue
                return {
                    "action": "hyperlink",
                    "targetSlide": int(target),
                    "originalTargetSlide": None,
                    "resolveMethod": RESOLVE_NOOP_MIRROR,
                    "binaryActionCode": 0,
                    "resolveRationale": (
                        "InteractiveInfoAtom action=none but shape text matches a "
                        "sibling hyperlink on the same slide; mirror that target so "
                        "the labeled control navigates (duplicate hitbox pattern)."
                    ),
                }

    if next_slide is not None and is_continue_like_text(shape_text):
        # Only sequential-next when this noop is the sole labeled leave
        # (no non-self hyperlink siblings). If siblings exist but text did not
        # match, leave as explicit_noop rather than inventing a second destination.
        has_nav_sibling = any(
            sib.get("targetSlide") is not None and int(sib["targetSlide"]) != slide
            for sib in sibling_hyperlinks
        )
        if not has_nav_sibling:
            return {
                "action": "hyperlink",
                "targetSlide": next_slide,
                "originalTargetSlide": None,
                "resolveMethod": RESOLVE_NOOP_CONTINUE,
                "binaryActionCode": 0,
                "resolveRationale": (
                    "InteractiveInfoAtom action=none with continue/start shape text "
                    "and no non-self hyperlink leave on the slide; promote to next "
                    "sequential so the labeled control navigates."
                ),
            }

    return {
        "action": "none",
        "targetSlide": None,
        "resolveMethod": None,
        "binaryActionCode": 0,
    }


def is_continue_like_text(text: str | None) -> bool:
    if not text or not str(text).strip():
        return False
    return bool(CONTINUE_TEXT_RE.search(str(text)))


def is_combat_like_text(text: str | None) -> bool:
    if not text or not str(text).strip():
        return False
    return bool(COMBAT_TEXT_RE.match(str(text).strip()))


def is_death_terminal_texts(texts: list[str] | None) -> bool:
    joined = " ".join(str(t).lower() for t in (texts or []) if t)
    if not joined.strip():
        return False
    return any(marker in joined for marker in DEATH_TEXT_MARKERS)


def shape_text_map(
    inventory: dict[str, Any] | None,
    layers_by_slide: dict[int, list[dict[str, Any]]] | None = None,
) -> dict[tuple[int, int], str]:
    """Map (slide, shapeId) → text from inventory runs and/or layer manifests."""
    texts: dict[tuple[int, int], str] = {}
    if inventory:
        for run in inventory.get("text_runs") or []:
            if run.get("slide") is None or run.get("shape_id") is None:
                continue
            texts[(int(run["slide"]), int(run["shape_id"]))] = str(run.get("text") or "")
    if layers_by_slide:
        for slide, layers in layers_by_slide.items():
            for layer in layers or []:
                if layer.get("shapeId") is None or not layer.get("text"):
                    continue
                texts.setdefault((int(slide), int(layer["shapeId"])), str(layer["text"]))
    return texts


def combat_all_self_slide_ids(
    inventory: dict[str, Any],
    texts: dict[tuple[int, int], str],
    total_slides: int,
) -> set[int]:
    """Slides where every hyperlink is a combat option self-link (no non-self leave).

    Used only when next sequential slide exists so options can promote to the
    authored outcome cutscene without inventing win/flee branches.
    """
    by_slide: dict[int, list[dict[str, Any]]] = {}
    for action in inventory.get("interactive_actions") or []:
        if int(action.get("action_code", 0)) != 4:
            continue
        if action.get("target_slide") is None:
            continue
        slide = int(action["slide"])
        by_slide.setdefault(slide, []).append(action)

    result: set[int] = set()
    for slide, actions in by_slide.items():
        if slide >= total_slides:
            continue
        if not actions:
            continue
        all_combat_self = True
        for action in actions:
            target = int(action["target_slide"])
            sid = action.get("shape_id")
            text = texts.get((slide, int(sid))) if sid is not None else None
            if target != slide or not is_combat_like_text(text):
                all_combat_self = False
                break
        if all_combat_self:
            result.add(slide)
    return result


def resolve_self_hyperlink(
    *,
    slide: int,
    target_slide: int | None,
    shape_text: str | None,
    sole_hyperlink_on_slide: bool,
    next_slide: int | None,
    combat_all_self_promote: bool = False,
) -> dict[str, Any]:
    """Decide port target for a binary self-link (or pass through non-self).

    Returns keys: targetSlide, originalTargetSlide, resolveMethod, isSelfLink.
    """
    if target_slide is None:
        return {
            "targetSlide": None,
            "originalTargetSlide": None,
            "resolveMethod": None,
            "isSelfLink": False,
        }
    target = int(target_slide)
    if target != slide:
        return {
            "targetSlide": target,
            "originalTargetSlide": target,
            "resolveMethod": "binary_label",
            "isSelfLink": False,
        }

    original = slide
    if next_slide is not None and is_continue_like_text(shape_text):
        return {
            "targetSlide": next_slide,
            "originalTargetSlide": original,
            "resolveMethod": "self_continue_to_next",
            "isSelfLink": False,
            "binarySelfLink": True,
        }
    if next_slide is not None and sole_hyperlink_on_slide and not (shape_text or "").strip():
        return {
            "targetSlide": next_slide,
            "originalTargetSlide": original,
            "resolveMethod": "sole_image_self_to_next",
            "isSelfLink": False,
            "binarySelfLink": True,
        }
    if is_combat_like_text(shape_text):
        # All options on this slide are combat selfs → promote to sequential
        # outcome (scripted death / only authored follow-up). Partial selfs
        # on mixed combat slides stay confirmed_self_combat.
        if combat_all_self_promote and next_slide is not None:
            return {
                "targetSlide": next_slide,
                "originalTargetSlide": original,
                "resolveMethod": RESOLVE_COMBAT_ALL_SELF,
                "isSelfLink": False,
                "binarySelfLink": True,
                "resolveRationale": (
                    "Binary ExHyperlink labels every combat option as this slide; "
                    "no non-self leave path and no alternate outcome slides in the "
                    "file. Next sequential slide is the authored fight outcome "
                    "(e.g. Ubergoblin death cutscene). Partial combat selfs on "
                    "other slides are not bulk-promoted."
                ),
            }
        return {
            "targetSlide": slide,
            "originalTargetSlide": original,
            "resolveMethod": "confirmed_self_combat",
            "isSelfLink": True,
            "binarySelfLink": True,
        }
    return {
        "targetSlide": slide,
        "originalTargetSlide": original,
        "resolveMethod": "confirmed_self_label_match",
        "isSelfLink": True,
        "binarySelfLink": True,
    }


def _flag_set(transition: dict[str, Any] | None) -> set[str]:
    if not transition:
        return set()
    return set(transition.get("flagNames") or [])


def classify_hyperlinks(slide: int, hotspots: list[dict[str, Any]]) -> dict[str, Any]:
    non_self: list[dict[str, Any]] = []
    self_links: list[dict[str, Any]] = []
    media: list[dict[str, Any]] = []
    noops: list[dict[str, Any]] = []
    for hotspot in hotspots or []:
        action = hotspot.get("action")
        if action == "media" or hotspot.get("mediaBindingId"):
            media.append(
                {
                    "id": hotspot.get("id"),
                    "shapeId": hotspot.get("shapeId"),
                    "behaviorStatus": hotspot.get("behaviorStatus"),
                }
            )
            continue
        if action == "hyperlink" and hotspot.get("targetSlide") is not None:
            target = int(hotspot["targetSlide"])
            entry = {
                "id": hotspot.get("id"),
                "shapeId": hotspot.get("shapeId"),
                "targetSlide": target,
                "label": hotspot.get("label") or hotspot.get("targetLabel"),
                "clickable": bool(hotspot.get("clickable")),
                "resolveMethod": hotspot.get("resolveMethod"),
                "originalTargetSlide": hotspot.get("originalTargetSlide"),
            }
            # Resolved continue/image selfs are non-self at runtime.
            if target == slide:
                self_links.append(entry)
            else:
                non_self.append(entry)
            continue
        if action in ("none",) or hotspot.get("behaviorStatus") == "explicit_noop":
            noops.append({"id": hotspot.get("id"), "shapeId": hotspot.get("shapeId")})
    return {
        "nonSelfHyperlinks": non_self,
        "selfHyperlinks": self_links,
        "mediaActions": media,
        "noopActions": noops,
        "nonSelfHyperlinkCount": len(non_self),
        "selfHyperlinkCount": len(self_links),
    }


def count_on_next_conditions(animation_slide: dict[str, Any] | None) -> int:
    if not animation_slide:
        return 0
    count = 0
    stack = list(animation_slide.get("rootTimeNodes") or [])
    while stack:
        node = stack.pop()
        for condition in node.get("conditions") or []:
            parsed = condition.get("parsed") or {}
            if parsed.get("triggerEvent") in (9, 10):
                count += 1
        stack.extend(node.get("children") or [])
    return count


def build_screen_advancement(
    *,
    slide: int,
    total_slides: int,
    transition: dict[str, Any] | None,
    hotspots: list[dict[str, Any]] | None,
    animation_slide: dict[str, Any] | None = None,
    self_link_status: dict[str, str] | None = None,
    layer_texts: list[str] | None = None,
) -> dict[str, Any]:
    """Return advancement policy for one screen (embedded in game-manifest)."""
    flags = _flag_set(transition)
    link_info = classify_hyperlinks(slide, hotspots or [])
    slide_time = transition.get("slideTimeMs") if transition else None
    auto_flag = "autoAdvance" in flags
    manual_flag = "manualAdvance" in flags
    auto_delay = (
        int(slide_time)
        if auto_flag and isinstance(slide_time, (int, float)) and slide_time > 0
        else None
    )
    next_slide = slide + 1 if slide < total_slides else None
    next_id = f"slide-{next_slide:03d}" if next_slide is not None else None

    death_terminal = is_death_terminal_texts(layer_texts)
    continue_text_present = any(is_continue_like_text(t) for t in (layer_texts or []))

    modes: list[str] = []
    if auto_delay is not None:
        modes.append("auto_advance")
    if manual_flag:
        modes.append("click_advance_after_anims")
    if link_info["nonSelfHyperlinkCount"] > 0:
        modes.append("hyperlink")
    if link_info["mediaActions"]:
        modes.append("media")

    # Stage-click advances sequential slide when PPT fManualAdvance is set.
    stage_click_advances = bool(manual_flag and next_id)
    stage_click_resolve: str | None = "manualAdvance_bit" if stage_click_advances else None

    leave_paths: list[str] = []
    if auto_delay is not None and next_id:
        leave_paths.append("auto_advance")
    if stage_click_advances:
        leave_paths.append("stage_click_after_anims")
    if link_info["nonSelfHyperlinkCount"] > 0:
        leave_paths.append("non_self_hyperlink")

    # Documented port fallbacks when binary has no leave path (source unchanged).
    if not leave_paths and next_id and not death_terminal:
        if continue_text_present:
            stage_click_advances = True
            stage_click_resolve = "continue_text_stage_click"
            leave_paths.append("stage_click_continue_text")
            if "click_advance_after_anims" not in modes:
                modes.append("click_advance_after_anims")
        elif link_info["selfHyperlinkCount"] == 0:
            # Empty / interstitial / noop-only screens: allow stage leave.
            stage_click_advances = True
            stage_click_resolve = "interstitial_stage_click"
            leave_paths.append("stage_click_interstitial")
            if "click_advance_after_anims" not in modes:
                modes.append("click_advance_after_anims")

    if death_terminal and not leave_paths:
        modes.append("terminal_death")
        leave_paths.append("restart_only")

    if not modes:
        if link_info["selfHyperlinkCount"] > 0:
            modes.append("self_hyperlink_only")
        else:
            modes.append("no_decoded_leave_path")

    if not leave_paths:
        stuck_reason = (
            "self_hyperlinks_only"
            if link_info["selfHyperlinkCount"] > 0
            else "no_nav_hotspots_and_no_advance_flags"
        )
    else:
        stuck_reason = None

    self_statuses = []
    for link in link_info["selfHyperlinks"]:
        key = f"{slide}:{link.get('shapeId')}"
        status = (
            link.get("resolveMethod")
            or (self_link_status or {}).get(key)
            or "confirmed_self_label_match"
        )
        self_statuses.append({**link, "status": status})

    return {
        "modes": modes,
        "flagNames": sorted(flags),
        "stageClickAdvancesSlide": stage_click_advances,
        "stageClickResolveMethod": stage_click_resolve,
        "autoAdvance": auto_delay is not None,
        "autoAdvanceDelayMs": auto_delay,
        "nextSequentialSlide": next_slide,
        "nextSequentialId": next_id,
        "onNextConditionCount": count_on_next_conditions(animation_slide),
        "nonSelfHyperlinkCount": link_info["nonSelfHyperlinkCount"],
        "selfHyperlinkCount": link_info["selfHyperlinkCount"],
        "selfHyperlinks": self_statuses,
        "mediaActionCount": len(link_info["mediaActions"]),
        "leavePaths": leave_paths,
        "stuckReason": stuck_reason,
        "deathTerminal": death_terminal,
        "policyNotes": [
            "manualAdvance bit (SSSlideInfoAtom) => stage click advances to next sequential slide after OnNext queue is empty",
            "autoAdvance bit + positive slideTimeMs => timer advance; delay is max(slideTime, animation timeline) at runtime",
            "without manualAdvance, blank stage click does not change slides (hyperlinks/media only) unless a documented fallback applies",
            "self-hyperlinks: ExHyperlink stores only friendly name 'Slide N'; continue/start and sole-image selfs promote to next with resolveMethod provenance",
            "combat menus where ALL options are binary selfs promote to next sequential outcome (combat_all_self_to_next_outcome); partial combat selfs stay self",
            "death screens (DED/Press esc) are terminal via Restart, not stuck",
            "continue-text or empty interstitials with no leave path get stage-click-to-next fallback",
        ],
    }


def summarize_model(slides: list[dict[str, Any]]) -> dict[str, Any]:
    mode_counts: dict[str, int] = {}
    stuck: list[dict[str, Any]] = []
    manual: list[int] = []
    auto: list[int] = []
    self_only: list[int] = []
    terminals: list[int] = []
    resolved_selfs = 0
    for entry in slides:
        slide = int(entry["slide"])
        adv = entry["advancement"]
        for mode in adv.get("modes") or []:
            mode_counts[mode] = mode_counts.get(mode, 0) + 1
        if adv.get("stuckReason"):
            stuck.append(
                {
                    "slide": slide,
                    "reason": adv["stuckReason"],
                    "modes": adv.get("modes"),
                    "selfHyperlinkCount": adv.get("selfHyperlinkCount"),
                    "flagNames": adv.get("flagNames"),
                }
            )
        if adv.get("stageClickAdvancesSlide"):
            manual.append(slide)
        if adv.get("autoAdvance"):
            auto.append(slide)
        if adv.get("deathTerminal"):
            terminals.append(slide)
        if adv.get("modes") == ["self_hyperlink_only"] or (
            adv.get("stuckReason") == "self_hyperlinks_only"
        ):
            self_only.append(slide)
        for link in adv.get("selfHyperlinks") or []:
            if link.get("status") in (
                "confirmed_self_label_match",
                "confirmed_self_combat",
            ):
                pass
        for hs in entry.get("hotspots") or []:
            if hs.get("resolveMethod") in (
                "self_continue_to_next",
                "sole_image_self_to_next",
            ):
                resolved_selfs += 1
    return {
        "slideCount": len(slides),
        "modeCounts": mode_counts,
        "clickAdvanceSlideCount": len(manual),
        "autoAdvanceSlideCount": len(auto),
        "stuckSlideCount": len(stuck),
        "stuckSlides": stuck,
        "selfHyperlinkOnlySlides": self_only,
        "clickAdvanceSlides": manual,
        "deathTerminalSlides": terminals,
    }
