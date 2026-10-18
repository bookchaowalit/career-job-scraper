#!/usr/bin/env python3
"""Import user-selected public property rows into a review-only lead CSV.

The input is a CSV or JSON export produced from a page the operator opened
manually (for example a Chrome extension export).  This command never fetches
the input URLs, reads browser cookies, logs in to a social network, or sends
outreach.  It only normalises the supplied text and keeps rows with explicit
owner/co-agent evidence by default.

Examples::

    python scripts/import_property_leads.py \
        --input /path/from/chrome-extension.csv \
        --output-dir data/exported

    python scripts/import_property_leads.py \
        --input tests/fixtures/property_owner_coagent_export.csv \
        --output-dir /tmp/property-owner-coagent-sample

The generated CSV uses the property.v1 field set.  Contact values are emitted
only when they were present in the supplied public text and every row starts
with ``review_decision=pending`` and ``outreach_status=not_contacted``.
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

from property.lead_extraction import CONTACT_FIELDS, SOCIAL_HOSTS, enrich_listing  # noqa: E402
from property.listing_config import PROPERTY_CAPTURE_SOURCE_HOSTS  # noqa: E402


DEFAULT_OUTPUT_DIR = ROOT / "data" / "exported"
MAX_INPUT_BYTES = 10_000_000
MAX_INPUT_ROWS = 500
MAX_TEXT_LENGTH = 5_000

IMPORT_FIELDNAMES = [
    "scraped_at",
    "captured_at",
    "title",
    "type",
    "listing_type",
    "url",
    "price_raw",
    "price",
    "bedrooms",
    "bathrooms",
    "area_sqm",
    "location",
    "description",
    "social_query",
    "date",
    "source_channel",
    "source_platform",
    *CONTACT_FIELDS,
]

QUARANTINE_FIELDNAMES = ["row_number", "reason", "url_sha256", "input_sha256"]

# Instant Data Scraper and small custom extensions use different column names.
# Keys are normalised before lookup, so spaces, hyphens, and underscores are
# interchangeable.  Only these bounded text fields are used as evidence.
FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "title": (
        "title",
        "name",
        "listing title",
        "property title",
        "headline",
        "หัวข้อ",
        "ชื่อประกาศ",
    ),
    "url": (
        "url",
        "link",
        "href",
        "listing url",
        "property url",
        "source url",
        "ลิงก์",
    ),
    "description": (
        "description",
        "snippet",
        "summary",
        "content",
        "text",
        "details",
        "รายละเอียด",
    ),
    "contact_text": (
        "contact",
        "contact text",
        "contact details",
        "seller",
        "owner",
        "agent",
        "publisher",
        "ผู้ขาย",
        "เจ้าของ",
        "นายหน้า",
    ),
    "location": (
        "location",
        "address",
        "area",
        "district",
        "province",
        "ที่ตั้ง",
        "ทำเล",
    ),
    "price_raw": (
        "price",
        "price raw",
        "price/month",
        "rent",
        "ราคา",
        "ค่าเช่า",
    ),
    "bedrooms": (
        "bedrooms",
        "beds",
        "bed",
        "ห้องนอน",
    ),
    "bathrooms": (
        "bathrooms",
        "baths",
        "bath",
        "ห้องน้ำ",
    ),
    "area_sqm": (
        "area sqm",
        "sqm",
        "size",
        "พื้นที่",
        "ตรม",
        "ตร.ม.",
    ),
    "listing_type": ("listing type", "property type", "ประเภท", "ชนิด"),
    "type": ("type", "listing type", "property type", "ประเภท"),
    "social_query": ("social query", "query", "ค้นหา", "คำค้น"),
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
_NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}
_SOCIAL_SOURCE_HOSTS = dict(SOCIAL_HOSTS)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def _safe_metadata(value: Any, limit: int = 200) -> str:
    """Keep governance metadata as a short reference, never a pasted notice."""

    return re.sub(r"\s+", " ", _scalar(value)).strip()[:limit]


def _normalise_key(value: Any) -> str:
    return re.sub(r"[^0-9a-zก-๙]+", "", str(value or "").casefold())


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


def _row_lookup(row: dict[str, Any]) -> dict[str, str]:
    return {_normalise_key(key): _scalar(value).strip() for key, value in row.items()}


def _pick(row: dict[str, Any], field: str) -> str:
    lookup = _row_lookup(row)
    aliases = FIELD_ALIASES.get(field, (field,))
    for alias in aliases:
        value = lookup.get(_normalise_key(alias), "").strip()
        if value:
            return value
    return ""


def _host_platform(host: str) -> str:
    normalized = (host or "").lower().removeprefix("www.")
    for domain, platform in {**PROPERTY_CAPTURE_SOURCE_HOSTS, **_SOCIAL_SOURCE_HOSTS}.items():
        if normalized == domain or normalized.endswith(f".{domain}"):
            return platform
    return ""


def canonical_source_url(value: Any) -> tuple[str, str]:
    """Return a canonical HTTPS URL and its allowlisted platform.

    The importer does not follow redirects.  Removing fragments and known
    tracking parameters makes extension exports idempotent while preserving
    meaningful query parameters used by a listing page.
    """

    raw = _scalar(value).strip().rstrip(".,;:)]}>")
    try:
        parsed = urlsplit(raw)
        host = (parsed.hostname or "").lower().removeprefix("www.")
        # Accessing .port raises ValueError for malformed ports.
        port = parsed.port
    except ValueError as exc:
        raise ValueError("malformed_url") from exc
    if (
        parsed.scheme.lower() != "https"
        or not host
        or parsed.username
        or parsed.password
        or port is not None
    ):
        raise ValueError("url_must_be_https_without_credentials_or_port")
    platform = _host_platform(host)
    if not platform:
        raise ValueError("source_host_not_allowlisted")
    if platform in _SOCIAL_SOURCE_HOSTS.values():
        # Collapse mobile/locale subdomains so the same public post is not
        # retained twice when an extension exports both desktop and mobile
        # links.
        for domain, social_platform in _SOCIAL_SOURCE_HOSTS.items():
            if social_platform == platform and (host == domain or host.endswith(f".{domain}")):
                host = domain
                break
    path = parsed.path.rstrip("/") or "/"
    query: list[tuple[str, str]] = []
    for key, query_value in parse_qsl(parsed.query, keep_blank_values=True):
        lowered = key.casefold()
        if lowered in _TRACKING_KEYS or lowered.startswith(_TRACKING_PREFIXES):
            continue
        query.append((key, query_value))
    query.sort()
    canonical = urlunsplit(("https", host, path, urlencode(query), ""))
    return canonical, platform


def _number(value: Any, *, area: bool = False) -> str:
    text = _bounded_text(value, 100).casefold()
    if not text:
        return ""
    pattern = r"(?<![\d.])(?P<value>\d+(?:[,.]\d+)?|one|two|three|four|five)"
    match = re.search(pattern, text)
    if not match:
        return ""
    raw = match.group("value").replace(",", "")
    numeric = _NUMBER_WORDS.get(raw, raw)
    try:
        number = float(numeric)
    except (TypeError, ValueError):
        return ""
    if number < 0 or number > (100_000 if area else 100):
        return ""
    return str(int(number)) if number.is_integer() else str(number)


def _price(value: Any) -> tuple[str, str]:
    text = _bounded_text(value, 160)
    if not text:
        return "", ""
    million = re.search(r"(?P<value>\d+(?:[,.]\d+)?)\s*(?:ล้าน|m(?:illion)?)\b", text, re.IGNORECASE)
    if million:
        number = float(million.group("value").replace(",", "")) * 1_000_000
        return million.group(0), str(int(number) if number.is_integer() else number)
    match = re.search(r"(?P<value>\d[\d,]*(?:\.\d+)?)", text)
    if not match:
        return "", ""
    number = float(match.group("value").replace(",", ""))
    if number <= 0 or number > 10_000_000_000:
        return "", ""
    return match.group(0), str(int(number) if number.is_integer() else number)


def _evidence_text(row: dict[str, Any]) -> str:
    fields = (
        "title",
        "description",
        "contact_text",
        "location",
        "social_query",
        "contact_name",
        "contact_role",
        "co_agent_status",
        "contact_phone",
        "contact_email",
        "contact_line",
        "contact_facebook",
        "contact_instagram",
        "contact_tiktok",
        "notes",
        "seller",
        "owner",
        "agent",
        "publisher",
    )
    return " ".join(_bounded_text(row.get(field), 1_000) for field in fields if row.get(field))[:MAX_TEXT_LENGTH]


def _candidate(row: dict[str, Any]) -> bool:
    return row.get("contact_role") in {"owner", "owner_or_agent"} or row.get(
        "co_agent_status"
    ) == "yes"


def _quality_score(row: dict[str, Any]) -> int:
    score = {
        "owner_or_agent": 5,
        "owner": 4,
        "agent": 2,
        "unknown": 0,
    }.get(str(row.get("contact_role") or "unknown"), 0)
    score += {"yes": 4, "no": 1, "unknown": 0}.get(
        str(row.get("co_agent_status") or "unknown"), 0
    )
    score += {"high": 2, "medium": 1, "low": 0}.get(
        str(row.get("contact_confidence") or "low"), 0
    )
    score += sum(
        bool(row.get(field))
        for field in (
            "contact_name",
            "contact_phone",
            "contact_email",
            "contact_line",
            "contact_social_urls",
        )
    )
    return score


def _normalised_fingerprint_part(value: Any) -> str:
    return re.sub(r"[^0-9a-zก-๙]+", "", _scalar(value).casefold())


def _fingerprint(row: dict[str, Any]) -> str:
    title = _normalised_fingerprint_part(row.get("title"))
    if len(title) < 8:
        return ""
    location = _normalised_fingerprint_part(row.get("location"))
    price = _normalised_fingerprint_part(row.get("price"))
    area = _normalised_fingerprint_part(row.get("area_sqm"))
    bedrooms = _normalised_fingerprint_part(row.get("bedrooms"))
    if not (location or price or area or bedrooms):
        return ""
    return "|".join((title, location, price, area, bedrooms))


def deduplicate_rows(rows: Iterable[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    """Deduplicate URLs and strong listing fingerprints, retaining best evidence."""

    materialised = list(rows)
    chosen: dict[tuple[str, str], dict[str, Any]] = {}
    order: list[tuple[str, str]] = []
    for row in materialised:
        keys = [("url", str(row.get("url") or ""))]
        fingerprint = _fingerprint(row)
        if fingerprint:
            keys.append(("fingerprint", fingerprint))
        existing_key = next((key for key in keys if key in chosen), None)
        if existing_key is None:
            primary = keys[0]
            chosen[primary] = row
            order.append(primary)
            if len(keys) > 1:
                chosen[keys[1]] = row
            continue
        existing = chosen[existing_key]
        if _quality_score(row) > _quality_score(existing):
            # Replace all aliases that pointed to the weaker row.
            for key in list(chosen):
                if chosen[key] is existing:
                    chosen[key] = row
        # A repeated URL/fingerprint is one output record either way.

    output: list[dict[str, Any]] = []
    seen_identity: set[int] = set()
    for key in order:
        row = chosen[key]
        identity = id(row)
        if identity in seen_identity:
            continue
        seen_identity.add(identity)
        output.append(row)
    return output, max(0, len(materialised) - len(output))


def _deduplicate_materialised(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    """Materialised wrapper that keeps duplicate accounting deterministic."""

    # ``deduplicate_rows`` accepts an iterable for callers, while this wrapper
    # avoids consuming a generator a second time when calculating statistics.
    return deduplicate_rows(rows)


def _json_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        rows = None
        for key in ("rows", "items", "results", "records", "data"):
            candidate = payload.get(key)
            if isinstance(candidate, list):
                rows = candidate
                break
        if rows is None and ("url" in payload or "link" in payload):
            rows = [payload]
        if rows is None:
            raise ValueError("JSON input must be a list or contain rows/items/results/records/data")
    else:
        raise ValueError("JSON input must be a list or object")
    if len(rows) > MAX_INPUT_ROWS:
        raise ValueError(f"input exceeds {MAX_INPUT_ROWS} rows")
    if not all(isinstance(row, dict) for row in rows):
        raise ValueError("JSON rows must be objects")
    return [dict(row) for row in rows]


def load_rows(path: Path) -> tuple[bytes, list[dict[str, Any]]]:
    """Read bounded CSV/JSON bytes without making any network request."""

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


def _build_row(raw: dict[str, Any], captured_at: str) -> tuple[dict[str, Any] | None, str | None, str]:
    """Build one property.v1 row, returning row, rejection reason, and URL hash."""

    raw_url = _pick(raw, "url")
    url_hash = hashlib.sha256(raw_url.encode("utf-8")).hexdigest()
    try:
        url, platform = canonical_source_url(raw_url)
    except ValueError as exc:
        return None, str(exc), url_hash
    title = _bounded_text(_pick(raw, "title"), 240)
    if not title:
        return None, "missing_title", hashlib.sha256(url.encode("utf-8")).hexdigest()
    description = _bounded_text(_pick(raw, "description"), MAX_TEXT_LENGTH)
    location = _bounded_text(_pick(raw, "location"), 240)
    price_raw, price = _price(_pick(raw, "price_raw"))
    if not price_raw:
        # Some exports include price only in the description/title.
        fallback_price_text = f"{title} {description}"
        if re.search(r"฿|\bTHB\b|บาท|ล้าน|/\s*(?:month|เดือน)|ราคา|rent", fallback_price_text, re.IGNORECASE):
            price_raw, price = _price(fallback_price_text)
    listing_type = _bounded_text(_pick(raw, "listing_type") or _pick(raw, "type"), 100)
    if not listing_type:
        listing_type = "property_owner_coagent"
    evidence_row = dict(raw)
    evidence_row.update(
        {
            "title": title,
            "description": description,
            "location": location,
            "contact_text": _pick(raw, "contact_text"),
            "social_query": _pick(raw, "social_query"),
        }
    )
    evidence_text = _evidence_text(evidence_row)
    listing: dict[str, Any] = {
        "scraped_at": captured_at,
        "captured_at": captured_at,
        "title": title,
        "type": "social_property_lead" if platform in _SOCIAL_SOURCE_HOSTS.values() else listing_type,
        "listing_type": listing_type,
        "url": url,
        "price_raw": price_raw,
        "price": price,
        "bedrooms": _number(_pick(raw, "bedrooms")),
        "bathrooms": _number(_pick(raw, "bathrooms")),
        "area_sqm": _number(_pick(raw, "area_sqm"), area=True),
        "location": location,
        "description": description,
        "social_query": _bounded_text(_pick(raw, "social_query"), 240),
        "date": captured_at[:10],
        "source_channel": "social_search" if platform in _SOCIAL_SOURCE_HOSTS.values() else "listing",
        "source_platform": platform,
    }
    enriched = enrich_listing(listing, text=evidence_text, source_url=url)
    if platform in _SOCIAL_SOURCE_HOSTS.values():
        social_field = f"contact_{platform}"
        enriched[social_field] = enriched.get(social_field) or url
        enriched["contact_social_urls"] = enriched.get("contact_social_urls") or url
    return enriched, None, hashlib.sha256(url.encode("utf-8")).hexdigest()


def import_property_rows(
    rows: Iterable[dict[str, Any]],
    *,
    captured_at: str | None = None,
    include_unqualified: bool = False,
    retention_until: str = "",
    terms_basis_ref: str = "",
    input_sha256: str = "",
) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, str]]]:
    """Normalise rows and return accepted rows, redacted stats, and quarantine."""

    timestamp = captured_at or _utc_now()
    retention_until = _safe_metadata(retention_until)
    terms_basis_ref = _safe_metadata(terms_basis_ref)
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
        built, reason, url_hash = _build_row(raw, timestamp)
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
        if _candidate(built):
            stats["candidate_rows"] += 1
        elif not include_unqualified:
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
        if retention_until:
            built["retention_until"] = retention_until
        if terms_basis_ref:
            built["terms_basis_ref"] = terms_basis_ref
        accepted.append(built)

    deduplicated, duplicates = _deduplicate_materialised(accepted)
    stats["duplicate_rows"] = duplicates
    stats["accepted_rows"] = len(deduplicated)
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
        writer = csv.DictWriter(handle, fieldnames=IMPORT_FIELDNAMES, extrasaction="ignore")
        if not exists:
            writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in IMPORT_FIELDNAMES})
    return path


def write_outputs(
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
    """Write normalized snapshot, append-only history, quarantine, raw bytes, and manifest."""

    output_dir.mkdir(parents=True, exist_ok=True)
    snapshot = _write_csv(output_dir / "property_owner_coagent_leads.csv", rows, IMPORT_FIELDNAMES)
    history = _write_history(output_dir / "property_owner_coagent_history.csv", rows)
    quarantine_path = _write_csv(
        output_dir / "property_owner_coagent_quarantine.csv", quarantine, QUARANTINE_FIELDNAMES
    )
    raw_path = output_dir / f"property_owner_coagent_raw_input{input_path.suffix.casefold() or '.csv'}"
    if raw_path.resolve() != input_path.resolve():
        raw_path.write_bytes(raw_input)
    manifest = {
        "schema_version": "property.v1",
        "contract": "contracts/property-capture.v1.json",
        "source_mode": "user_provided_public_export",
        "source_input_name": input_path.name,
        "source_input_sha256": input_sha256,
        "raw_input_path": str(raw_path),
        "captured_at": captured_at,
        "privacy_class": "public_source_with_terms",
        "human_review_required": True,
        "retention_until": retention_until,
        "terms_basis_ref": terms_basis_ref,
        "stats": stats,
    }
    manifest_path = output_dir / "property_owner_coagent_manifest.json"
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
    parser.add_argument("--input", required=True, type=Path, help="CSV or JSON exported from a user-selected public page")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), type=Path)
    parser.add_argument("--limit", type=int, default=100, help="Maximum rows to inspect (1-500)")
    parser.add_argument(
        "--include-unqualified",
        action="store_true",
        help="Keep rows without explicit owner/co-agent evidence for manual review",
    )
    parser.add_argument("--retention-until", default="", help="Approved deletion deadline (optional)")
    parser.add_argument("--terms-basis-ref", default="", help="Internal source-terms/PDPA decision reference (optional)")
    parser.add_argument("--dry-run", action="store_true", help="Parse and report counts without writing files")
    args = parser.parse_args(argv)
    if args.limit < 1 or args.limit > MAX_INPUT_ROWS:
        parser.error(f"--limit must be between 1 and {MAX_INPUT_ROWS}")
    if not args.input.exists():
        parser.error(f"input file does not exist: {args.input}")
    try:
        raw, loaded = load_rows(args.input)
        bounded = loaded[: args.limit]
        input_sha256 = hashlib.sha256(raw).hexdigest()
        captured_at = _utc_now()
        retention_until = _safe_metadata(args.retention_until)
        terms_basis_ref = _safe_metadata(args.terms_basis_ref)
        rows, stats, quarantine = import_property_rows(
            bounded,
            captured_at=captured_at,
            include_unqualified=args.include_unqualified,
            retention_until=retention_until,
            terms_basis_ref=terms_basis_ref,
            input_sha256=input_sha256,
        )
        stats["limited_rows"] = len(bounded)
        stats["truncated_rows"] = max(0, len(loaded) - len(bounded))
        print(
            "property_owner_coagent_import: "
            f"input={stats['input_rows']} inspected={stats['limited_rows']} "
            f"accepted={stats['accepted_rows']} candidates={stats['candidate_rows']} "
            f"quarantined={stats['quarantined_rows']} duplicates={stats['duplicate_rows']}"
        )
        if args.dry_run:
            return 0 if rows else 1
        if not rows:
            print("No owner/co-agent rows were accepted; inspect the quarantine CSV after a non-dry run.")
            # Still write the redacted quarantine and manifest so the failure is
            # visible and replayable.
        paths = write_outputs(
            rows,
            quarantine,
            stats,
            output_dir=args.output_dir,
            raw_input=raw,
            input_path=args.input,
            input_sha256=input_sha256,
            captured_at=captured_at,
            retention_until=retention_until,
            terms_basis_ref=terms_basis_ref,
        )
        print(f"snapshot={paths['snapshot']}")
        print(f"history={paths['history']}")
        print(f"quarantine={paths['quarantine']}")
        print(f"manifest={paths['manifest']}")
        return 0 if rows else 1
    except (OSError, ValueError, UnicodeError, csv.Error) as exc:
        print(f"property_owner_coagent_import: ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
