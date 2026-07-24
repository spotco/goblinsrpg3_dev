"""Verify visual risk queue uses post-resolve self-hyperlink policy (Phase 5.8)."""

from __future__ import annotations

import json
from pathlib import Path

from audit_visual_risks import main as rebuild_visual_risks


def fail(message: str) -> None:
    raise SystemExit(message)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    rebuild_visual_risks()

    report = load_json(root / "generated" / "visual_risks.json")
    if report.get("format") != "goblins-rpg3-visual-risks-v2":
        fail(f"expected visual_risks format v2, got {report.get('format')}")

    post = report.get("selfHyperlinkPostResolve") or {}
    if post.get("clickableSelfCount", 1) != 0:
        fail(
            "clickable post-resolve self-hyperlinks must be 0; "
            f"found {post.get('clickableSelfCount')}: {post.get('clickableSelfHotspotIds')}"
        )
    if post.get("documentedResidualSelfCount") != 5:
        fail(
            "expected 5 documented residual selfs (Phase 2), "
            f"found {post.get('documentedResidualSelfCount')}"
        )
    if post.get("promoteAuditResidualSelfCount") != 5:
        fail(
            "promote_audit residualSelfCount should be 5, "
            f"found {post.get('promoteAuditResidualSelfCount')}"
        )
    if not post.get("residualMatchesPromoteAudit"):
        fail("visual residual self set does not match promote_audit residualSelfHyperlinks")

    if post.get("promotedSelfCount", 0) < 1:
        fail("expected at least one self_hyperlink_promoted info row (provenance)")

    # No legacy high self_hyperlink code without classification suffix.
    legacy = [
        risk
        for risk in report.get("risks") or []
        if risk.get("code") == "self_hyperlink" and risk.get("severity") == "high"
    ]
    if legacy:
        fail(f"stale high self_hyperlink rows still present: {legacy[:3]}")

    unclassified = (report.get("summary") or {}).get("byCode", {}).get("self_hyperlink_unclassified", 0)
    if unclassified:
        fail(f"unclassified self-hyperlinks: {unclassified}")

    # High defects should not include residual selfs.
    high_self = [
        risk
        for risk in report.get("risks") or []
        if risk.get("severity") == "high"
        and str(risk.get("code") or "").startswith("self_hyperlink")
    ]
    if high_self:
        fail(f"high self_hyperlink* defects remain: {high_self}")

    print("visual risks verification passed")
    print(
        f"  residualSelf={post['documentedResidualSelfCount']} "
        f"promotedSelf={post['promotedSelfCount']} "
        f"clickableSelf={post['clickableSelfCount']} "
        f"defectTotal={report['summary'].get('defectTotal')} "
        f"riskTotal={report['summary'].get('riskTotal')}"
    )


if __name__ == "__main__":
    main()
