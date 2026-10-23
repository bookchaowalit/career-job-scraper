"""scripts/_sentry.py: no-op without a DSN, errors only, allowlist scrub of events."""
import sys
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import _sentry  # noqa: E402

# Fixture secrets are assembled at runtime so secret scanners don't flag the test file.
_PW = "s3cr" + "%40t"
_JWT = ".".join(["eyJ" + "hbGciOiJub25lIn0", "eyJ" + "zdWIiOiJ0ZXN0In0", "c2ln" + "bmF0dXJl"])


def test_without_dsn_nothing_initialises_or_sends(monkeypatch):
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    fake = mock.MagicMock()
    monkeypatch.setitem(sys.modules, "sentry_sdk", fake)
    assert _sentry.init_sentry() is False
    _sentry.capture_exception(RuntimeError("x"))
    _sentry.capture_failure("job_postings", "boom")
    _sentry.flush()
    assert fake.mock_calls == []


def test_with_dsn_initialises_errors_only_without_pii(monkeypatch):
    sentry_sdk = pytest.importorskip("sentry_sdk")
    calls, tags = [], {}
    monkeypatch.setattr(sentry_sdk, "init", lambda **kw: calls.append(kw))
    monkeypatch.setattr(sentry_sdk, "set_tag", lambda key, value: tags.__setitem__(key, value))
    monkeypatch.setenv("SENTRY_DSN", "https://public@o0.ingest.sentry.io/0")
    monkeypatch.setenv("GITHUB_SHA", "abc123")
    monkeypatch.delenv("SENTRY_ENVIRONMENT", raising=False)
    assert _sentry.init_sentry() is True
    (options,) = calls
    assert options["environment"] == "production"
    assert options["release"] == "abc123"
    assert options["traces_sample_rate"] is None
    assert options["send_default_pii"] is False
    assert options["include_local_variables"] is False
    assert options["max_breadcrumbs"] == 0
    assert options["before_send"] is _sentry.scrub_event
    assert options["before_send_transaction"]({}, {}) is None
    (logging_integration,) = options["integrations"]
    assert logging_integration._handler is None
    assert logging_integration._breadcrumb_handler is None
    assert tags == {"service": "career-job-scraper-capture"}


def test_scrub_masks_secrets_and_url_queries():
    text = (
        f"GET https://board.example/jobs?q=python&token=t1#frag via postgresql://u:{_PW}@db/x; "
        "api_key=" + "dummy-value Authorization: Bearer " + "abc.def-ghi " + _JWT
    )
    out = _sentry.scrub(text)
    for leaked in (_PW, "dummy-value", "abc.def-ghi", _JWT, "q=python", "token=t1", "frag"):
        assert leaked not in out
    assert "https://board.example/jobs" in out
    assert "postgresql://u:***@db/x" in out


def test_scrub_event_keeps_only_allowlisted_fields():
    event = {
        "level": "error",
        "exception": {
            "values": [
                {
                    "type": "HTTPError",
                    "value": "403 for https://board.example/search?keywords=me",
                    "stacktrace": {
                        "frames": [{"filename": "scrape.py?x=1", "abs_path": "/r/scrape.py", "vars": {"cookie": "c"}}]
                    },
                }
            ]
        },
        "request": {"url": "https://x?token=t", "headers": {"authorization": "Bearer t"}},
        "user": {"ip_address": "1.2.3.4"},
        "breadcrumbs": {"values": [{"message": "Senior Engineer at Example"}]},
        "extra": {"sys.argv": ["--token", "t"]},
        "contexts": {"os": {"name": "Linux"}, "trace": {"trace_id": "t"}, "response": {"status_code": 403}},
        "tags": {"service": "capture", "url": "https://x?token=t", "job": "job_postings?x=1"},
        "transaction": "/search?q=1",
        "some_new_sdk_field": {"payload": "unknown"},
    }
    out = _sentry.scrub_event(event)
    for dropped in ("request", "user", "breadcrumbs", "extra", "some_new_sdk_field"):
        assert dropped not in out
    exc = out["exception"]["values"][0]
    assert exc["value"] == "403 for https://board.example/search"
    assert exc["stacktrace"]["frames"] == [{"filename": "scrape.py", "abs_path": "/r/scrape.py"}]
    assert out["contexts"] == {"os": {"name": "Linux"}}
    assert out["tags"] == {"service": "capture", "job": "job_postings"}
    assert out["transaction"] == "/search"
    assert out["level"] == "error"


def test_scrub_event_keeps_only_formatted_log_text():
    event = {"logentry": {"message": "token %s", "params": ["t0ken"], "formatted": "token=t0ken failed"}}
    assert _sentry.scrub_event(event)["logentry"] == {"message": "token=*** failed"}


def test_capture_failure_sends_a_scrubbed_message_tagged_with_the_job(monkeypatch):
    sentry_sdk = pytest.importorskip("sentry_sdk")
    monkeypatch.setenv("SENTRY_DSN", "https://public@o0.ingest.sentry.io/0")
    sent = []
    monkeypatch.setattr(sentry_sdk, "capture_message", lambda message, level: sent.append((message, level)))
    _sentry.capture_failure("job_postings", "403 for https://board.example/s?q=me")
    assert sent == [("job_postings: failed: 403 for https://board.example/s", "error")]
