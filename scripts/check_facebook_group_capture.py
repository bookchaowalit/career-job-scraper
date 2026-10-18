#!/usr/bin/env python3
"""Validate a facebook.group-post.v1 capture without printing contact values."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.import_facebook_group_posts import (  # noqa: E402
    GROUP_FIELDNAMES,
    _truthy,
    canonical_group_url,
    canonical_post_url,
    legacy_canonical_post_url,
    legacy_post_id,
)


ROLE_VALUES = {"owner", "agent", "owner_or_agent", "unknown"}
CO_AGENT_VALUES = {"yes", "no", "unknown"}
CONFIDENCE_VALUES = {"high", "medium", "low"}
VISIBILITY_VALUES = {"public", "private", "unknown"}
LEAD_REVIEW_VALUES = {"co_agent_candidate", "needs_human_review", "unqualified"}
REVIEW_DECISIONS = {"pending", "approved", "rejected", "needs_more_evidence"}
OUTREACH_STATUSES = {"not_contacted", "approved_to_contact", "contacted", "opt_out"}
CAPTURE_METHODS = {
    "chrome_extension_visible_tab",
    "chrome_extension_auto_scroll",
    "manual_browser_export",
    "playwright_visible_tab",
}
REQUIRED_FIELDS = {
    "captured_at",
    "group_url",
    "post_url",
    "post_id",
    "group_name",
    "author_name",
    "posted_at",
    "text",
    "visibility",
    "text_complete",
    "capture_method",
    "source_channel",
    "source_platform",
    "contact_role",
    "co_agent_status",
    "contact_public",
    "lead_review_status",
    "review_decision",
    "outreach_status",
}


def _error(row: int, code: str) -> dict[str, Any]:
    return {"row": row, "code": code}


def _timestamp(value: Any) -> bool:
    try:
        datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return False
    return True


def _duplicate_value_count(values: Iterable[Any]) -> int:
    normalised = [str(value or "").strip() for value in values]
    non_empty = [value for value in normalised if value]
    return len(non_empty) - len(set(non_empty))


def _quality_summary(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    materialised = list(rows)
    visibility_counts = {value: 0 for value in sorted(VISIBILITY_VALUES)}
    incomplete_row_numbers: list[int] = []
    for row_number, row in enumerate(materialised, start=2):
        visibility = str(row.get("visibility") or "").strip().casefold()
        bucket = visibility if visibility in visibility_counts else "invalid"
        visibility_counts[bucket] = visibility_counts.get(bucket, 0) + 1
        if not _truthy(row.get("text_complete"), default=False):
            incomplete_row_numbers.append(row_number)
    post_urls = [str(row.get("post_url") or "").strip() for row in materialised]
    post_ids = [str(row.get("post_id") or "").strip() for row in materialised]
    return {
        "row_count": len(materialised),
        "visibility_counts": visibility_counts,
        "complete_text_rows": len(materialised) - len(incomplete_row_numbers),
        "incomplete_text_rows": len(incomplete_row_numbers),
        "incomplete_row_numbers": incomplete_row_numbers,
        "unique_post_urls": len({value for value in post_urls if value}),
        "duplicate_post_url_rows": _duplicate_value_count(post_urls),
        "unique_post_ids": len({value for value in post_ids if value}),
        "duplicate_post_id_rows": _duplicate_value_count(post_ids),
        "candidate_rows": sum(
            str(row.get("lead_review_status") or "").strip() == "co_agent_candidate"
            for row in materialised
        ),
        "unqualified_rows": sum(
            str(row.get("lead_review_status") or "").strip() == "unqualified"
            for row in materialised
        ),
        "pending_review_rows": sum(
            str(row.get("review_decision") or "").strip() == "pending"
            for row in materialised
        ),
    }


def validate_group_capture_rows(
    rows: Iterable[dict[str, Any]],
    *,
    min_rows: int = 1,
    max_rows: int = 500,
    require_governance: bool = False,
    require_complete: bool = False,
) -> dict[str, Any]:
    """Return stable, redacted validation codes for group post rows."""

    materialised = list(rows)
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    if len(materialised) < max(0, int(min_rows)):
        errors.append(_error(0, "too_few_rows"))
    if len(materialised) > max(0, int(max_rows)):
        errors.append(_error(0, "too_many_rows"))

    seen_urls: set[str] = set()
    seen_ids: set[str] = set()
    for row_number, row in enumerate(materialised, start=2):
        missing = REQUIRED_FIELDS - set(row)
        for field in sorted(missing):
            errors.append(_error(row_number, f"missing_{field}"))
        if missing:
            continue

        group_url = str(row.get("group_url") or "").strip()
        try:
            canonical_group = canonical_group_url(group_url)
        except ValueError:
            canonical_group = ""
        if not canonical_group or canonical_group != group_url:
            errors.append(_error(row_number, "invalid_group_url"))

        post_url = str(row.get("post_url") or "").strip()
        try:
            canonical_post, expected_id = canonical_post_url(post_url)
        except ValueError:
            canonical_post, expected_id = "", ""
        # Snapshots written before 1.4 hold the older canonical form (with
        # Facebook's per-load query); keep them reviewable.
        if canonical_post and canonical_post != post_url:
            try:
                if legacy_canonical_post_url(post_url) != post_url:
                    canonical_post = ""
                else:
                    expected_id = legacy_post_id(post_url)
            except ValueError:
                canonical_post = ""
        if not canonical_post:
            errors.append(_error(row_number, "invalid_post_url"))
        elif post_url in seen_urls:
            errors.append(_error(row_number, "duplicate_post_url"))
        else:
            seen_urls.add(post_url)
        post_id = str(row.get("post_id") or "").strip()
        if not post_id:
            errors.append(_error(row_number, "missing_post_id"))
        elif post_id in seen_ids:
            errors.append(_error(row_number, "duplicate_post_id"))
        else:
            seen_ids.add(post_id)
        if expected_id and post_id != expected_id:
            errors.append(_error(row_number, "post_id_mismatch"))
        post_group_match = re.match(r"^/groups/([^/]+)/", urlsplit(post_url).path, re.IGNORECASE) if canonical_post else None
        if post_group_match and canonical_group:
            group_slug = urlsplit(canonical_group).path.rstrip("/").rsplit("/", 1)[-1].casefold()
            if post_group_match.group(1).casefold() != group_slug:
                errors.append(_error(row_number, "group_url_mismatch"))

        if str(row.get("source_channel") or "").strip() != "facebook_group":
            errors.append(_error(row_number, "source_channel_mismatch"))
        if str(row.get("source_platform") or "").strip() != "facebook":
            errors.append(_error(row_number, "source_platform_mismatch"))
        if str(row.get("capture_method") or "").strip() not in CAPTURE_METHODS:
            errors.append(_error(row_number, "invalid_capture_method"))

        visibility = str(row.get("visibility") or "").strip().casefold()
        if visibility not in VISIBILITY_VALUES:
            errors.append(_error(row_number, "invalid_visibility"))
        elif visibility == "unknown":
            warnings.append(_error(row_number, "visibility_unknown"))
        text_complete = _truthy(row.get("text_complete"), default=False)
        text_complete_value = str(
            row.get("text_complete") if row.get("text_complete") is not None else ""
        ).strip().casefold()
        if text_complete_value not in {"true", "false", "1", "0", "yes", "no"}:
            errors.append(_error(row_number, "invalid_text_complete"))
        if not text_complete:
            warnings.append(_error(row_number, "text_incomplete"))
            if require_complete:
                errors.append(_error(row_number, "text_incomplete"))
        contact_public = _truthy(row.get("contact_public"), default=False)
        if contact_public != (visibility == "public"):
            errors.append(_error(row_number, "contact_public_visibility_mismatch"))
        if not str(row.get("text") or "").strip():
            errors.append(_error(row_number, "missing_text"))

        for field, allowed in (
            ("contact_role", ROLE_VALUES),
            ("co_agent_status", CO_AGENT_VALUES),
            ("contact_confidence", CONFIDENCE_VALUES),
            ("lead_review_status", LEAD_REVIEW_VALUES),
            ("review_decision", REVIEW_DECISIONS),
            ("outreach_status", OUTREACH_STATUSES),
        ):
            if str(row.get(field) or "").strip() not in allowed:
                errors.append(_error(row_number, f"invalid_{field}"))
        if not _timestamp(row.get("captured_at")):
            errors.append(_error(row_number, "invalid_captured_at"))
        source_url = str(row.get("contact_source_url") or "").strip()
        if source_url and source_url != post_url:
            errors.append(_error(row_number, "contact_source_url_mismatch"))
        if not source_url:
            errors.append(_error(row_number, "contact_source_url_required"))

        decision = str(row.get("review_decision") or "").strip()
        if decision != "pending":
            if not str(row.get("reviewer_id") or "").strip():
                errors.append(_error(row_number, "reviewer_required"))
            if not _timestamp(row.get("reviewed_at")):
                errors.append(_error(row_number, "reviewed_at_required"))
        outreach = str(row.get("outreach_status") or "").strip()
        if outreach in {"approved_to_contact", "contacted"} and decision != "approved":
            errors.append(_error(row_number, "outreach_not_approved"))

        if visibility != "public" or require_governance:
            if not _timestamp(row.get("retention_until")):
                errors.append(_error(row_number, "retention_until_required"))
            if not str(row.get("terms_basis_ref") or "").strip():
                errors.append(_error(row_number, "terms_basis_ref_required"))

    return {
        "ok": not errors,
        "row_count": len(materialised),
        "errors": errors,
        "warnings": warnings,
        "quality": _quality_summary(materialised),
    }


def validate_group_capture_file(
    path: Path,
    *,
    min_rows: int = 1,
    max_rows: int = 500,
    require_governance: bool = False,
    require_complete: bool = False,
) -> dict[str, Any]:
    if not path.exists():
        return {"ok": False, "row_count": 0, "errors": [_error(0, "missing_file")]}
    try:
        with path.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            headers = reader.fieldnames or []
            errors: list[dict[str, Any]] = []
            if headers != GROUP_FIELDNAMES:
                errors.append(_error(1, "headers_do_not_match_facebook_group_post_v1"))
            report = validate_group_capture_rows(
                reader,
                min_rows=min_rows,
                max_rows=max_rows,
                require_governance=require_governance,
                require_complete=require_complete,
            )
    except (OSError, UnicodeError, csv.Error):
        return {"ok": False, "row_count": 0, "errors": [_error(0, "unreadable_file")]}
    report["errors"] = errors + report["errors"]
    report["ok"] = not report["errors"]
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("--min-rows", type=int, default=1)
    parser.add_argument("--max-rows", type=int, default=500)
    parser.add_argument("--require-governance", action="store_true")
    parser.add_argument("--require-complete", action="store_true", help="Fail when a row is marked text_complete=false")
    parser.add_argument("--json", action="store_true", help="Print a redacted JSON report")
    args = parser.parse_args(argv)
    report = validate_group_capture_file(
        args.path,
        min_rows=args.min_rows,
        max_rows=args.max_rows,
        require_governance=args.require_governance,
        require_complete=args.require_complete,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    else:
        status = "PASS" if report["ok"] else "FAIL"
        print(f"facebook_group_capture: {status} ({report['row_count']} rows, {len(report['errors'])} errors)")
        for error in report["errors"]:
            print(f"  row {error['row']}: {error['code']}")
        for warning in report.get("warnings", []):
            print(f"  row {warning['row']}: warning {warning['code']}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
