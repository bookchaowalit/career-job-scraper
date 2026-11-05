"""Contact email moved to the work address on 2026-11-05.

Résumés, cover letters, proposals and follow-ups give the work address. The
Gmail API senders still send from the account their refresh token belongs to
(``GMAIL_SENDER``, personal by default until a work-account token exists), and
set Reply-To to the work address so replies land there.
"""
import base64
import email
import importlib
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
WORK_EMAIL = "bookchaowalit.work@gmail.com"
PERSONAL = "bookchaowalit@gmail.com"
SENDER_DEFAULT = re.compile(r'^GMAIL_SENDER = os\.getenv\("GMAIL_SENDER", "bookchaowalit@gmail\.com"\)$')


def test_personal_address_only_as_gmail_sender_default():
    hits = []
    for path in sorted(SCRIPTS.rglob("*.py")):
        for no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if PERSONAL in line and not SENDER_DEFAULT.match(line.strip()):
                hits.append(f"{path.relative_to(ROOT)}:{no}")
    assert hits == []


def _script(name):
    sys.path.insert(0, str(SCRIPTS))
    try:
        return importlib.import_module(name)
    finally:
        sys.path.remove(str(SCRIPTS))


def _parse_raw(payload):
    return email.message_from_bytes(base64.urlsafe_b64decode(payload["raw"]))


# Every Gmail API MIME builder sends with the personal-account token, so each
# one must set Reply-To or replies keep going to the personal inbox.
@pytest.mark.parametrize(
    "build",
    [
        lambda: _script("auto_send_email")._build_mime("hr@example.com", "Hi", "Body", attach_resume=False),
        lambda: _parse_raw(_script("send_followup_emails").create_message("hr@example.com", "Hi", "Body")),
        lambda: _parse_raw(
            _script("send_application_emails").create_message_with_attachment("hr@example.com", "Hi", "Body", None)
        ),
    ],
    ids=["auto_send_email", "send_followup_emails", "send_application_emails"],
)
def test_gmail_builders_set_reply_to_work_address(build):
    assert build()["reply-to"] == WORK_EMAIL
