"""Error reporting to Sentry for the hosted capture (scripts/cloud_capture.py).

A no-op unless SENTRY_DSN is set, so tests, local runs and forks never send anything.
Errors only: no tracing, no logs, no breadcrumbs.

This repository's own copy, adapted from book-job-data's ``_sentry.py`` (secret scrub) and the
allowlist scrub in ``~/work/b-tier-b/sentry-ref/sentry.ts``: an event keeps only what it needs
to locate a bug (exception type, scrubbed message, stack frames without local variables, the
platform contexts and our tags). Request data, user, breadcrumbs, extra, frame locals and any
URL query string or fragment are dropped, and URL passwords, bearer tokens, key=value secrets
and JWTs are masked in free text.
"""
from __future__ import annotations

import os
import re
from typing import Any

# Contexts that describe the platform only; everything else (trace, response, ...) is dropped.
SAFE_CONTEXTS = ("os", "runtime", "device", "app")
# Top-level event keys that are kept; anything else is dropped (allowlist, not denylist).
SAFE_KEYS = (
    "event_id", "timestamp", "platform", "level", "logger", "server_name", "release",
    "environment", "dist", "sdk", "modules", "fingerprint", "exception", "message",
    "logentry", "contexts", "tags", "threads", "debug_meta", "transaction",
)

# scheme://user:password@host -> scheme://user:***@host
_URL_PASSWORD = re.compile(r"(?P<head>[a-zA-Z][a-zA-Z0-9+.-]*://[^\s:/@]+:)[^\s@]+(?=@)")
_KV_SECRET = re.compile(r"(?i)\b(password|passwd|pwd|secret|token|api[_-]?key)(\s*[=:]\s*)\S+")
_BEARER = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+")
_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]*")
# ?query and #fragment after a URL or absolute path (job-board searches carry them).
_URL_QUERY = re.compile(r"((?:https?://|/)[^\s?#\"'<>()]*)[?#][^\s\"'<>()]*")


def _strip_query(value: str) -> str:
    return re.split(r"[?#]", value, maxsplit=1)[0]


def scrub(text: str) -> str:
    text = _URL_PASSWORD.sub(r"\g<head>***", text)
    text = _KV_SECRET.sub(r"\1\2***", text)
    text = _BEARER.sub("Bearer ***", text)
    text = _JWT.sub("***jwt***", text)
    return _URL_QUERY.sub(r"\1", text)


def _scrub_frames(container: Any) -> None:
    frames = ((container or {}).get("stacktrace") or {}).get("frames") or []
    for frame in frames:
        frame.pop("vars", None)
        for key in ("filename", "abs_path"):
            if isinstance(frame.get(key), str):
                frame[key] = _strip_query(frame[key])


def scrub_event(event: dict[str, Any], _hint: dict[str, Any] | None = None) -> dict[str, Any]:
    for key in list(event):
        if key not in SAFE_KEYS:
            del event[key]
    for exc in (event.get("exception") or {}).get("values") or []:
        if isinstance(exc.get("value"), str):
            exc["value"] = scrub(exc["value"])
        _scrub_frames(exc)
    for thread in (event.get("threads") or {}).get("values") or []:
        _scrub_frames(thread)
    if isinstance(event.get("message"), str):
        event["message"] = scrub(event["message"])
    logentry = event.get("logentry")
    if isinstance(logentry, dict):
        # Keep only the scrubbed formatted text, never the raw params.
        formatted = logentry.get("formatted") or logentry.get("message")
        event["logentry"] = {"message": scrub(str(formatted))} if formatted else {}
    contexts = event.get("contexts")
    if isinstance(contexts, dict):
        event["contexts"] = {k: contexts[k] for k in SAFE_CONTEXTS if k in contexts}
    if isinstance(event.get("transaction"), str):
        event["transaction"] = _strip_query(event["transaction"])
    tags = event.get("tags")
    if isinstance(tags, dict):
        tags.pop("url", None)
        for key, value in tags.items():
            if isinstance(value, str):
                tags[key] = _strip_query(value)
    for image in (event.get("debug_meta") or {}).get("images") or []:
        if isinstance(image.get("code_file"), str):
            image["code_file"] = _strip_query(image["code_file"])
    return event


def _dsn() -> str:
    return os.environ.get("SENTRY_DSN", "").strip()


def init_sentry(service: str = "career-job-scraper-capture") -> bool:
    """Start error reporting when SENTRY_DSN is set; return whether it is on."""
    dsn = _dsn()
    if not dsn:
        return False
    import sentry_sdk
    from sentry_sdk.integrations.logging import LoggingIntegration

    sentry_sdk.init(
        dsn=dsn,
        environment=os.environ.get("SENTRY_ENVIRONMENT", "production"),
        release=os.environ.get("GITHUB_SHA") or os.environ.get("SENTRY_RELEASE") or None,
        # None (not 0.0) disables tracing completely.
        traces_sample_rate=None,
        send_default_pii=False,
        include_local_variables=False,
        max_breadcrumbs=0,
        # sentry-sdk types events as a TypedDict; the scrubber treats them as plain dicts.
        before_send=scrub_event,  # type: ignore[arg-type]
        before_send_transaction=lambda _event, _hint: None,
        # Log text is free-form (job titles, scraper output): never an event or breadcrumb.
        integrations=[LoggingIntegration(level=None, event_level=None, sentry_logs_level=None)],
    )
    sentry_sdk.set_tag("service", service)
    return True


def capture_exception(exc: BaseException) -> None:
    """Report an exception the capture loop catches and turns into an exit code."""
    if not _dsn():
        return
    import sentry_sdk

    sentry_sdk.capture_exception(exc)


def capture_failure(job_name: str, error: str) -> None:
    """Report a job that returned a failed result (no exception to attach)."""
    if not _dsn():
        return
    import sentry_sdk

    with sentry_sdk.new_scope() as scope:
        scope.set_tag("job", job_name)
        scope.fingerprint = ["capture-job-failed", job_name]
        sentry_sdk.capture_message(f"{job_name}: failed: {scrub(error)}", level="error")


def flush() -> None:
    if not _dsn():
        return
    import sentry_sdk

    sentry_sdk.flush(5)
