#!/usr/bin/env python3
"""Import user-selected rendered Facebook Group posts into a review CSV.

The input is a CSV or JSON export made from the included browser extension (or
an equivalent manual exporter).  This command never opens Facebook, follows a
post URL, reads cookies, calls a platform API, or sends outreach.  Public rows
are retained for search and review; private and visibility-unknown rows are
quarantined unless the operator supplies an explicit gate plus retention and
terms-basis metadata.

Examples::

    python scripts/import_facebook_group_posts.py \
        --input ~/Downloads/facebook_group_posts_export.csv \
        --output-dir data/exported

    python scripts/import_facebook_group_posts.py \
        --input tests/fixtures/facebook_group_posts_export.csv \
        --output-dir /tmp/facebook-group-fixture
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from property.lead_extraction import CONTACT_FIELDS, extract_contact_details  # noqa: E402


DEFAULT_OUTPUT_DIR = ROOT / "data" / "exported"
MAX_INPUT_BYTES = 10_000_000
MAX_INPUT_ROWS = 500
MAX_TEXT_LENGTH = 10_000
MAX_GROUP_NAME_LENGTH = 240
MAX_AUTHOR_NAME_LENGTH = 160
MAX_POST_ID_LENGTH = 100

GROUP_FIELDNAMES = [
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
    *CONTACT_FIELDS,
]

QUARANTINE_FIELDNAMES = ["row_number", "reason", "url_sha256", "input_sha256"]

FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "group_url": (
        "group_url",
        "group url",
        "group_link",
        "group link",
        "group",
        "source_group_url",
        "กลุ่ม",
        "ลิงก์กลุ่ม",
    ),
    "post_url": (
        "post_url",
        "post url",
        "url",
        "link",
        "href",
        "post_link",
        "post link",
        "ลิงก์โพสต์",
        "ลิงก์",
    ),
    "post_id": ("post_id", "post id", "postid", "รหัสโพสต์"),
    "group_name": ("group_name", "group name", "group_title", "ชื่อกลุ่ม"),
    "author_name": (
        "author_name",
        "author name",
        "author",
        "publisher",
        "ผู้โพสต์",
        "ชื่อผู้โพสต์",
    ),
    "posted_at": ("posted_at", "posted at", "published_at", "date", "เวลาโพสต์"),
    "text": (
        "text",
        "post_text",
        "post text",
        "content",
        "description",
        "body",
        "ข้อความ",
    ),
    "visibility": ("visibility", "group_visibility", "privacy", "การมองเห็น"),
    "text_complete": (
        "text_complete",
        "text complete",
        "complete",
        "ข้อความครบ",
    ),
    "capture_method": ("capture_method", "capture method", "method"),
    "captured_at": ("captured_at", "captured at", "exported_at", "เวลาจับข้อมูล"),
    "source_platform": ("source_platform", "source platform", "platform"),
}

_TRACKING_KEYS = {
    "fbclid",
    "gclid",
    "dclid",
    "igshid",
    "mc_cid",
    "mc_eid",
    "ref",
    "referrer",
    "source",
    "src",
    "si",
}
_TRACKING_PREFIXES = ("utm_", "vero_")
_FACEBOOK_HOSTS = {"facebook.com", "fb.com"}
_VISIBILITY_VALUES = {"public", "private", "unknown"}
_CAPTURE_METHODS = {
    "chrome_extension_visible_tab",
    "manual_browser_export",
    "playwright_visible_tab",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def _unguard_formula(value: str) -> str:
    """Undo the extension's spreadsheet formula guard (one leading quote)."""
    if len(value) >= 2 and value[0] == "'" and value[1] in "=+-@\t\r":
        return value[1:]
    return value


def _scalar(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return _unguard_formula(str(value))


def _bounded_text(value: Any, limit: int = MAX_TEXT_LENGTH) -> str:
    return re.sub(r"\s+", " ", _scalar(value)).strip()[:limit]


def _safe_metadata(value: Any, limit: int = 200) -> str:
    return _bounded_text(value, limit)


def _normalise_key(value: Any) -> str:
    return re.sub(r"[^0-9a-zก-๙]+", "", _scalar(value).casefold())


def _row_lookup(row: dict[str, Any]) -> dict[str, str]:
    return {_normalise_key(key): _scalar(value).strip() for key, value in row.items()}


def _pick(row: dict[str, Any], field: str) -> str:
    lookup = _row_lookup(row)
    for alias in FIELD_ALIASES.get(field, (field,)):
        value = lookup.get(_normalise_key(alias), "").strip()
        if value:
            return value
    return ""


def _json_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        rows = None
        for key in ("rows", "items", "results", "records", "data", "posts"):
            candidate = payload.get(key)
            if isinstance(candidate, list):
                rows = candidate
                break
        if rows is None and ("post_url" in payload or "url" in payload):
            rows = [payload]
        if rows is None:
            raise ValueError("JSON input must be a list or contain rows/items/results/records/data/posts")
    else:
        raise ValueError("JSON input must be a list or object")
    if len(rows) > MAX_INPUT_ROWS:
        raise ValueError(f"input exceeds {MAX_INPUT_ROWS} rows")
    if not all(isinstance(row, dict) for row in rows):
        raise ValueError("JSON rows must be objects")
    return [dict(row) for row in rows]


def load_group_rows(path: Path) -> tuple[bytes, list[dict[str, Any]]]:
    """Read bounded UTF-8 CSV/JSON bytes without making a network request."""

    raw = path.read_bytes()
    if len(raw) > MAX_INPUT_BYTES:
        raise ValueError(f"input exceeds {MAX_INPUT_BYTES} bytes")
    suffix = path.suffix.casefold()
    if suffix == ".json" or raw.lstrip().startswith((b"[", b"{")):
        try:
            payload = json.loads(raw.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("invalid JSON input") from exc
        return raw, _json_rows(payload)
    try:
        text = raw.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
        headers = reader.fieldnames or []
        if not headers or len(headers) != len(set(headers)):
            raise ValueError("CSV must contain unique headers")
        rows: list[dict[str, Any]] = []
        for row in reader:
            if None in row:
                raise ValueError("CSV contains a row with extra columns")
            rows.append({str(key): value for key, value in row.items()})
            if len(rows) > MAX_INPUT_ROWS:
                raise ValueError(f"input exceeds {MAX_INPUT_ROWS} rows")
    except UnicodeDecodeError as exc:
        raise ValueError("input must be UTF-8 CSV or JSON") from exc
    return raw, rows


def _facebook_host(host: str) -> bool:
    normalized = (host or "").lower().removeprefix("www.")
    return normalized in _FACEBOOK_HOSTS or normalized.endswith(".facebook.com")


def _canonical_parts(raw_value: Any) -> tuple[Any, str, str]:
    raw = _scalar(raw_value).strip().rstrip(".,;:)]}>")
    if not raw:
        raise ValueError("missing_url")
    try:
        parsed = urlsplit(raw)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("malformed_url") from exc
    host = (parsed.hostname or "").lower().removeprefix("www.")
    if (
        parsed.scheme.lower() != "https"
        or not host
        or parsed.username
        or parsed.password
        or port is not None
        or not _facebook_host(host)
    ):
        raise ValueError("url_must_be_https_facebook_without_credentials_or_port")
    query: list[tuple[str, str]] = []
    for key, query_value in parse_qsl(parsed.query, keep_blank_values=True):
        lowered = key.casefold()
        if lowered in _TRACKING_KEYS or lowered.startswith(_TRACKING_PREFIXES):
            continue
        query.append((key, query_value))
    query.sort()
    canonical = urlunsplit(("https", "facebook.com", parsed.path.rstrip("/") or "/", urlencode(query), ""))
    return parsed, canonical, host


def canonical_group_url(value: Any) -> str:
    """Return a canonical Facebook Group URL or raise a redacted reason."""

    parsed, _, _ = _canonical_parts(value)
    match = re.fullmatch(r"/groups/([^/]+)", parsed.path.rstrip("/") or "/")
    if not match or match.group(1).casefold() in {"feed", "members", "about", "photos", "files"}:
        raise ValueError("invalid_group_url")
    # A group identity has no meaningful query component.  Removing it keeps
    # feed/referrer variants on the same collection boundary.
    return urlunsplit(("https", "facebook.com", parsed.path.rstrip("/") or "/", "", ""))


def _post_id_from_path(parsed: Any) -> str:
    path = parsed.path.rstrip("/")
    match = re.search(r"/groups/[^/]+/(?:posts|permalink)/([^/?]+)", path, re.IGNORECASE)
    if match:
        return match.group(1)[:MAX_POST_ID_LENGTH]
    if path.casefold().endswith(("/permalink.php", "/story.php")):
        query = {key.casefold(): value for key, value in parse_qsl(parsed.query, keep_blank_values=True)}
        for key in ("story_fbid", "fbid", "post_id", "id"):
            if query.get(key):
                return query[key][:MAX_POST_ID_LENGTH]
    match = re.search(r"/(?:posts|permalink)/([^/?]+)", path, re.IGNORECASE)
    return match.group(1)[:MAX_POST_ID_LENGTH] if match else ""


def _stable_post_url(parsed: Any, path: str, fallback: str) -> str:
    """Drop per-page-load query tokens so one post has one URL.

    Facebook appends ``__cft__``/``__tn__`` values that change on every load.
    Must match ``canonicalFacebookPostUrl`` in the extension and ``Code.gs``.
    """

    group = re.fullmatch(r"/groups/([^/]+)/(?:posts|permalink)/([^/]+)", path, re.IGNORECASE)
    if group:
        return f"https://facebook.com/groups/{group.group(1)}/posts/{group.group(2)}"
    if path.casefold().endswith(("/permalink.php", "/story.php")):
        query = dict(parse_qsl(parsed.query, keep_blank_values=False))
        if not query.get("story_fbid"):
            return fallback
        kept = sorted((key, query[key]) for key in ("id", "story_fbid") if query.get(key))
        return urlunsplit(("https", "facebook.com", path.casefold(), urlencode(kept), ""))
    return urlunsplit(("https", "facebook.com", path, "", ""))


def legacy_canonical_post_url(value: Any) -> str:
    """The pre-1.4 canonical form, which kept non-tracking query parameters.

    Snapshots written before the stable form remain valid for review; new
    imports always use ``canonical_post_url``.
    """

    return _canonical_parts(value)[1]


def legacy_post_id(value: Any) -> str:
    """The post_id the pre-1.4 importer derived for a legacy URL."""

    parsed, canonical, _ = _canonical_parts(value)
    return _post_id_from_path(parsed) or hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]


def canonical_post_url(value: Any) -> tuple[str, str]:
    """Return a canonical Facebook post URL and a stable post identifier."""

    parsed, canonical, _ = _canonical_parts(value)
    path = parsed.path.rstrip("/")
    valid_path = bool(
        re.fullmatch(r"/groups/[^/]+/(?:posts|permalink)/[^/]+", path, re.IGNORECASE)
        or path.casefold().endswith(("/permalink.php", "/story.php"))
        or re.fullmatch(r"/(?:story|posts|permalink)/[^/]+", path, re.IGNORECASE)
    )
    if not valid_path:
        raise ValueError("invalid_post_url")
    canonical = _stable_post_url(parsed, path, canonical)
    post_id = _post_id_from_path(parsed)
    if not post_id:
        # A direct URL with no visible ID is still deduplicable, but never use
        # arbitrary caller-supplied IDs as identity.
        post_id = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]
    return canonical, post_id


def _group_slug(value: str) -> str:
    parsed = urlsplit(value)
    match = re.fullmatch(r"/groups/([^/]+)", parsed.path.rstrip("/") or "/")
    return match.group(1).casefold() if match else ""


def _visibility(value: Any) -> str:
    text = _scalar(value).strip().casefold()
    if text in {"public", "public group", "open", "open group", "สาธารณะ", "กลุ่มสาธารณะ", "เปิด"}:
        return "public"
    if text in {"private", "private group", "closed", "closed group", "สมาชิกเท่านั้น", "กลุ่มส่วนตัว", "ส่วนตัว"}:
        return "private"
    return "unknown"


def _truthy(value: Any, *, default: bool = False) -> bool:
    text = _scalar(value).strip().casefold()
    if not text:
        return default
    return text in {"1", "true", "yes", "y", "complete", "ครบ"}


def _timestamp(value: Any, fallback: str) -> str:
    text = _bounded_text(value, 80)
    return text or fallback


def _candidate(details: dict[str, Any]) -> bool:
    return details.get("contact_role") in {"owner", "owner_or_agent"} or details.get("co_agent_status") == "yes"


def _quality_score(row: dict[str, Any]) -> int:
    score = 4 if _truthy(row.get("text_complete")) else 0
    score += min(len(_scalar(row.get("text"))), MAX_TEXT_LENGTH) // 500
    score += 3 if row.get("lead_review_status") == "co_agent_candidate" else 0
    score += {"high": 2, "medium": 1}.get(str(row.get("contact_confidence") or ""), 0)
    return score


def _deduplicate_rows(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    chosen: dict[tuple[str, str], dict[str, Any]] = {}
    order: list[tuple[str, str]] = []
    for row in rows:
        keys = [("url", str(row.get("post_url") or "")), ("id", str(row.get("post_id") or ""))]
        existing = next((chosen[key] for key in keys if key in chosen), None)
        if existing is None:
            order.append(keys[0])
            for key in keys:
                chosen[key] = row
            continue
        if _quality_score(row) > _quality_score(existing):
            for key, value in list(chosen.items()):
                if value is existing:
                    chosen[key] = row
    output: list[dict[str, Any]] = []
    seen: set[int] = set()
    for key in order:
        row = chosen[key]
        if id(row) in seen:
            continue
        seen.add(id(row))
        output.append(row)
    return output, max(0, len(rows) - len(output))


def _build_group_row(
    raw: dict[str, Any],
    captured_at: str,
    *,
    allow_private: bool,
    allow_unknown: bool,
    retention_until: str,
    terms_basis_ref: str,
) -> tuple[dict[str, Any] | None, str | None, str]:
    raw_post_url = _pick(raw, "post_url")
    url_hash = hashlib.sha256(raw_post_url.encode("utf-8")).hexdigest()
    try:
        post_url, post_id = canonical_post_url(raw_post_url)
    except ValueError as exc:
        return None, str(exc), url_hash
    try:
        group_url = canonical_group_url(_pick(raw, "group_url"))
    except ValueError as exc:
        # Keep the group identity supplied by the operator.  Deriving it from
        # a post path would silently turn a malformed or direct permalink into
        # a different collection boundary.
        return None, str(exc), hashlib.sha256(post_url.encode("utf-8")).hexdigest()
    if _group_slug(group_url):
        post_parsed = urlsplit(post_url)
        post_group_match = re.match(r"^/groups/([^/]+)/", post_parsed.path, re.IGNORECASE)
        if post_group_match and post_group_match.group(1).casefold() != _group_slug(group_url):
            return None, "group_url_mismatch", hashlib.sha256(post_url.encode("utf-8")).hexdigest()

    visibility = _visibility(_pick(raw, "visibility"))
    if visibility == "private" and not allow_private:
        return None, "nonpublic_visibility", hashlib.sha256(post_url.encode("utf-8")).hexdigest()
    if visibility == "unknown" and not allow_unknown:
        return None, "nonpublic_visibility", hashlib.sha256(post_url.encode("utf-8")).hexdigest()
    if visibility != "public" and (not retention_until or not terms_basis_ref):
        return None, "nonpublic_governance_required", hashlib.sha256(post_url.encode("utf-8")).hexdigest()

    text = _bounded_text(_pick(raw, "text"))
    if not text:
        return None, "missing_text", hashlib.sha256(post_url.encode("utf-8")).hexdigest()
    text_complete = _truthy(_pick(raw, "text_complete"), default=False)
    details = extract_contact_details(text, post_url)
    candidate = _candidate(details)
    if not text_complete:
        lead_review_status = "needs_human_review"
    elif candidate:
        lead_review_status = "co_agent_candidate"
    else:
        lead_review_status = "unqualified"
    details.update(
        {
            # CSV exports use the same capitalised boolean representation as
            # the existing property importer.  The validator accepts these
            # values without treating them as caller-supplied contact data.
            "contact_public": "True" if visibility == "public" else "False",
            "lead_review_status": lead_review_status,
            "review_decision": "pending",
            "reviewed_at": "",
            "reviewer_id": "",
            "outreach_status": "not_contacted",
            # If an operator supplies governance references, preserve them on
            # every accepted row so a later `--require-governance` validation
            # can assert one consistent retention policy.  Public rows still
            # remain public; the references do not grant outreach permission.
            "retention_until": retention_until,
            "terms_basis_ref": terms_basis_ref,
            "contact_source_url": post_url,
        }
    )
    source_platform = _pick(raw, "source_platform").casefold()
    if source_platform and source_platform != "facebook":
        return None, "source_platform_mismatch", hashlib.sha256(post_url.encode("utf-8")).hexdigest()
    capture_method = _bounded_text(_pick(raw, "capture_method"), 80) or "manual_browser_export"
    if capture_method not in _CAPTURE_METHODS:
        return None, "invalid_capture_method", hashlib.sha256(post_url.encode("utf-8")).hexdigest()
    row: dict[str, Any] = {
        "captured_at": _timestamp(_pick(raw, "captured_at"), captured_at),
        "group_url": group_url,
        "post_url": post_url,
        "post_id": post_id,
        "group_name": _bounded_text(_pick(raw, "group_name"), MAX_GROUP_NAME_LENGTH),
        "author_name": _bounded_text(_pick(raw, "author_name"), MAX_AUTHOR_NAME_LENGTH),
        "posted_at": _bounded_text(_pick(raw, "posted_at"), 80),
        "text": text,
        "visibility": visibility,
        "text_complete": text_complete,
        "capture_method": capture_method,
        "source_channel": "facebook_group",
        "source_platform": "facebook",
        **details,
    }
    # The importer owns the post identity and evidence.  Caller-supplied
    # contact columns are intentionally ignored and never merged into details.
    return row, None, hashlib.sha256(post_url.encode("utf-8")).hexdigest()


def import_facebook_group_rows(
    rows: Iterable[dict[str, Any]],
    *,
    captured_at: str | None = None,
    input_sha256: str = "",
    allow_private: bool = False,
    allow_unknown: bool = False,
    retention_until: str = "",
    terms_basis_ref: str = "",
    include_unqualified: bool = True,
) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, str]]]:
    """Normalise rows and return accepted rows, redacted stats, and quarantine."""

    timestamp = captured_at or _utc_now()
    retention = _safe_metadata(retention_until)
    terms_ref = _safe_metadata(terms_basis_ref)
    materialised = list(rows)
    stats: dict[str, Any] = {
        "input_rows": len(materialised),
        "candidate_rows": 0,
        "accepted_rows": 0,
        "quarantined_rows": 0,
        "duplicate_rows": 0,
    }
    accepted: list[dict[str, Any]] = []
    quarantine: list[dict[str, str]] = []
    for row_number, raw in enumerate(materialised, start=2):
        built, reason, url_hash = _build_group_row(
            raw,
            timestamp,
            allow_private=allow_private,
            allow_unknown=allow_unknown,
            retention_until=retention,
            terms_basis_ref=terms_ref,
        )
        if built is None:
            stats["quarantined_rows"] += 1
            quarantine.append(
                {
                    "row_number": str(row_number),
                    "reason": reason or "invalid_row",
                    "url_sha256": url_hash,
                    "input_sha256": input_sha256,
                }
            )
            continue
        candidate = _candidate(built)
        if not candidate and not include_unqualified:
            stats["quarantined_rows"] += 1
            quarantine.append(
                {
                    "row_number": str(row_number),
                    "reason": "missing_owner_or_coagent_signal",
                    "url_sha256": url_hash,
                    "input_sha256": input_sha256,
                }
            )
            continue
        accepted.append(built)

    deduplicated, duplicates = _deduplicate_rows(accepted)
    stats["duplicate_rows"] = duplicates
    stats["accepted_rows"] = len(deduplicated)
    stats["candidate_rows"] = sum(1 for row in deduplicated if _candidate(row))
    return deduplicated, stats, quarantine


def _write_csv(path: Path, rows: Iterable[dict[str, Any]], fieldnames: list[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})
    return path


def _write_history(path: Path, rows: list[dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists()
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=GROUP_FIELDNAMES, extrasaction="ignore")
        if not exists:
            writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in GROUP_FIELDNAMES})
    return path


def write_group_outputs(
    rows: list[dict[str, Any]],
    quarantine: list[dict[str, str]],
    stats: dict[str, Any],
    *,
    output_dir: Path,
    raw_input: bytes,
    input_path: Path,
    input_sha256: str,
    captured_at: str,
    retention_until: str = "",
    terms_basis_ref: str = "",
) -> dict[str, str]:
    """Write snapshot, history, redacted quarantine, raw bytes, and manifest."""

    output_dir.mkdir(parents=True, exist_ok=True)
    snapshot = _write_csv(output_dir / "facebook_group_posts.csv", rows, GROUP_FIELDNAMES)
    history = _write_history(output_dir / "facebook_group_posts_history.csv", rows)
    quarantine_path = _write_csv(
        output_dir / "facebook_group_posts_quarantine.csv", quarantine, QUARANTINE_FIELDNAMES
    )
    raw_path = output_dir / f"facebook_group_posts_raw_input{input_path.suffix.casefold() or '.csv'}"
    if raw_path.resolve() != input_path.resolve():
        raw_path.write_bytes(raw_input)
    manifest = {
        "schema_version": "facebook.group-post.v1",
        "contract": "contracts/facebook-group-post.v1.json",
        "source_mode": "user_selected_rendered_tab",
        "source_input_name": input_path.name,
        "source_input_sha256": input_sha256,
        "raw_input_path": str(raw_path),
        "captured_at": captured_at,
        "privacy_class": "group_visible_content",
        "human_review_required": True,
        "contact_public_rule": "true only when operator labels visibility=public",
        "retention_until": _safe_metadata(retention_until),
        "terms_basis_ref": _safe_metadata(terms_basis_ref),
        "stats": stats,
    }
    manifest_path = output_dir / "facebook_group_posts_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        "snapshot": str(snapshot),
        "history": str(history),
        "quarantine": str(quarantine_path),
        "raw_input": str(raw_path),
        "manifest": str(manifest_path),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="CSV or JSON exported from a user-selected rendered tab")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), type=Path)
    parser.add_argument("--limit", type=int, default=100, help="Maximum rows to inspect (1-500)")
    parser.add_argument("--allow-private", action="store_true", help="Accept rows labelled private after governance metadata is supplied")
    parser.add_argument("--allow-unknown", action="store_true", help="Accept rows with unknown visibility after governance metadata is supplied")
    parser.add_argument("--retention-until", default="", help="Approved deletion deadline for non-public rows")
    parser.add_argument("--terms-basis-ref", default="", help="Internal source-terms/PDPA decision reference for non-public rows")
    parser.add_argument("--candidates-only", action="store_true", help="Quarantine public posts without an owner/co-agent signal")
    parser.add_argument("--dry-run", action="store_true", help="Parse and report counts without writing files")
    args = parser.parse_args(argv)
    if args.limit < 1 or args.limit > MAX_INPUT_ROWS:
        parser.error(f"--limit must be between 1 and {MAX_INPUT_ROWS}")
    if not args.input.exists():
        parser.error(f"input file does not exist: {args.input}")
    try:
        raw, loaded = load_group_rows(args.input)
        bounded = loaded[: args.limit]
        input_sha256 = hashlib.sha256(raw).hexdigest()
        captured_at = _utc_now()
        rows, stats, quarantine = import_facebook_group_rows(
            bounded,
            captured_at=captured_at,
            input_sha256=input_sha256,
            allow_private=args.allow_private,
            allow_unknown=args.allow_unknown,
            retention_until=args.retention_until,
            terms_basis_ref=args.terms_basis_ref,
            include_unqualified=not args.candidates_only,
        )
        stats["limited_rows"] = len(bounded)
        stats["truncated_rows"] = max(0, len(loaded) - len(bounded))
        print(
            "facebook_group_import: "
            f"input={stats['input_rows']} inspected={stats['limited_rows']} "
            f"accepted={stats['accepted_rows']} candidates={stats['candidate_rows']} "
            f"quarantined={stats['quarantined_rows']} duplicates={stats['duplicate_rows']}"
        )
        if args.dry_run:
            return 0 if rows else 1
        paths = write_group_outputs(
            rows,
            quarantine,
            stats,
            output_dir=args.output_dir,
            raw_input=raw,
            input_path=args.input,
            input_sha256=input_sha256,
            captured_at=captured_at,
            retention_until=args.retention_until,
            terms_basis_ref=args.terms_basis_ref,
        )
        print(f"snapshot={paths['snapshot']}")
        print(f"history={paths['history']}")
        print(f"quarantine={paths['quarantine']}")
        print(f"manifest={paths['manifest']}")
        return 0 if rows else 1
    except (OSError, ValueError, UnicodeError, csv.Error) as exc:
        print(f"facebook_group_import: ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
