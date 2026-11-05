"""Contact email moved to the work address on 2026-11-05.

Résumés, cover letters, proposals and follow-ups give the work address. The
Gmail API senders still send from the account their refresh token belongs to
(``GMAIL_SENDER``, personal by default until a work-account token exists), and
set Reply-To to the work address so replies land there.
"""
import importlib
import re
import sys
from pathlib import Path

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


def test_auto_send_email_sets_reply_to_work_address():
    sys.path.insert(0, str(SCRIPTS))
    try:
        mod = importlib.import_module("auto_send_email")
    finally:
        sys.path.remove(str(SCRIPTS))
    msg = mod._build_mime("hr@example.com", "Hello", "Body", attach_resume=False)
    assert msg["reply-to"] == WORK_EMAIL
