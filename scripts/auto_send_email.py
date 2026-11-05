#!/usr/bin/env python3
"""
Auto Send Email — reads follow-up email drafts from followup_emails/
and sends them via Gmail API. Tracks sent emails to avoid duplicates.

Usage:
    python3 auto_send_email.py                    # dry-run (preview only)
    python3 auto_send_email.py --send             # actually send
    python3 auto_send_email.py --send --limit 5   # send max 5
    python3 auto_send_email.py --send --date 20260705  # only emails from this date
    python3 auto_send_email.py --status           # show sent/pending summary
"""

import argparse
import base64
import csv
import json
import os
import sys
from datetime import datetime
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

try:
    import httpx
except ImportError:
    raise SystemExit(
        "Missing dependency 'httpx'. "
        "Install via project venv: pip install -r requirements.txt "
        "(scripts must not pip-install at runtime)"
    )

# ── Paths ────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
from repo_paths import REPO_ROOT as ROOT, DATA_DIR, load_env
from safety import assert_no_network_send_without_flag

load_env()
FOLLOWUP_EMAILS_DIR = DATA_DIR / "followup_emails"
SENT_LOG = DATA_DIR / "auto_send_log.json"
APPLY_TRACKER = DATA_DIR / "apply_tracker.csv"
JOB_POSTINGS_CSV = DATA_DIR / "job_postings.csv"
MATCHED_CSV = DATA_DIR / "matched_jobs.csv"
CONTACT_EMAILS_JSON = DATA_DIR / "contact_emails.json"
APPLICATION_SEND_LOG = DATA_DIR / "application_send_log.json"

# ── Resume attachment ────────────────────────────────────────────
RESUMES_DIR = DATA_DIR / "resumes"
DEFAULT_RESUME = RESUMES_DIR / "Resume_Chaowalit_Greepoke.pdf"

# ── Gmail OAuth ──────────────────────────────────────────────────
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REFRESH_TOKEN = os.getenv("GOOGLE_REFRESH_TOKEN", "")
# Gmail API sends as the account the refresh token belongs to; replies go to CONTACT_EMAIL.
GMAIL_SENDER = os.getenv("GMAIL_SENDER", "bookchaowalit@gmail.com")
CONTACT_EMAIL = os.getenv("CONTACT_EMAIL", "bookchaowalit.work@gmail.com")
GMAIL_API_ENABLED = bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET and GOOGLE_REFRESH_TOKEN)

# ── Telegram ─────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "5255551291")

# ── Previous employers blocklist ─────────────────────────────────
# Import from send_application_emails or define locally
try:
    from send_application_emails import PREVIOUS_EMPLOYERS
except ImportError:
    PREVIOUS_EMPLOYERS = {
        # Own companies
        'nexatech', 'nexa', 'nexter', 'nextshield', 'turfmapp',
        # Land/Property (specific names only)
        'landmaps', 'landaps', 'landy',
        # Siam Commercial / SC (specific entity names)
        'sc assets', 'scasset', 'scgroup', 'sc assets management',
        'sc asset management',
        'siam commercial assets', 'siam commercial group', 'siam commercial',
        'siam commercial asset management', 'siam commercial family office',
        # Thai Life / TLA
        'thai life', 'thailand life', 'thailand life assurance', 'thai life assurance',
        'tla asset', 'tla asset management', 'thai life asset', 'thai life asset management',
        # Bangchak
        'bangchak', 'bangchak corporate', 'bangchak corp', 'bcpg', 'greenovist',
        # Bangkok Bank / BBL
        'bangkok bank', 'bbl asset', 'bbl asset management', 'bblfm', 'bbl fam',
        'bbl family office', 'bbl fm',
        # TMB / Thanachart
        'tmb thanachart', 'thanachart', 'thanachart bank', 'tmbt', 'tmb thanachart bank',
        # SCB
        'scb asset', 'scbx', 'scb family office', 'scb fm',
        # Kasikorn
        'kasikorn', 'kasikorn bank', 'kbank',
        # Other banks
        'krungsri', 'krungthai', 'ktb', 'ttb', 'bpi',
        # MRC
        'mrc',
        # GULF / JP Morgan
        'gulf jp morgan', 'jp morgan', 'jpmorgan',
        # Minor
        'minor international',
        # Central
        'central food', 'central retail', 'crc',
        # Home Pro
        'home pro', 'hmpo',
        # Thai Oil
        'thaioil', 'thaioil digital',
        # PTT
        'ptt', 'pttep', 'pttepg',
        # EGAT
        'egat',
        # Amata
        'amata',
        # CP
        'cp all', 'cp all retail', 'cpall',
        # Others
        'osotspa', 'bekind', 'wha', 'scg', 'dubai holding', 'mubadala', 'mitsui', 'bts',
    }


def is_previous_employer(company: str) -> bool:
    """Check if company matches a previous employer (case-insensitive).
    
    Uses forward substring match (PE entry in company name) to catch subsidiaries.
    Reverse match (company in PE entry) only when company covers >= 50% of PE entry
    to prevent short names like 'GT' matching 'krungthai'.
    """
    c = company.lower().strip()
    for pe in PREVIOUS_EMPLOYERS:
        if pe in c:  # Forward: PE entry is substring of company name
            return True
        if c in pe and len(c) >= len(pe) * 0.5:  # Reverse with length check
            return True
    return False


# ── Helpers ──────────────────────────────────────────────────────

def load_sent_log() -> dict:
    """Load the sent email tracking log."""
    if SENT_LOG.exists():
        try:
            return json.loads(SENT_LOG.read_text())
        except Exception:
            pass
    return {"sent": [], "failed": [], "drafts_created": []}


def save_sent_log(log: dict):
    """Persist the sent email tracking log."""
    SENT_LOG.write_text(json.dumps(log, indent=2, ensure_ascii=False))


def load_applied_companies() -> set:
    """Load set of company names (lowercase) that received an application email."""
    if not APPLICATION_SEND_LOG.exists():
        return set()
    try:
        entries = json.loads(APPLICATION_SEND_LOG.read_text())
        return {e['company'].lower() for e in entries if e.get('status') == 'sent'}
    except Exception:
        return set()


def is_already_sent(filename: str, log: dict) -> bool:
    """Check if this email file was already sent or drafted."""
    sent_ids = {e["file"] for e in log.get("sent", [])}
    draft_ids = {e["file"] for e in log.get("drafts_created", [])}
    return filename in sent_ids or filename in draft_ids


def parse_email_file(filepath: Path) -> dict:
    """Parse an email draft file → {subject, body}."""
    content = filepath.read_text(encoding="utf-8")
    subject = ""
    body = content

    if content.startswith("Subject:"):
        parts = content.split("\n\n", 1)
        subject = parts[0].replace("Subject:", "").strip()
        body = parts[1] if len(parts) > 1 else ""

    return {"subject": subject, "body": body}


def extract_company_from_filename(filename: str) -> str:
    """Extract company name from filename like followup_Airbnb_20260705.txt."""
    name = Path(filename).stem  # followup_Airbnb_20260705
    parts = name.split("_")
    # Remove 'followup' prefix and date suffix
    if parts and parts[0].lower() == "followup":
        parts = parts[1:]
    # Remove date (last part if it's all digits)
    if parts and parts[-1].isdigit():
        parts = parts[:-1]
    return " ".join(parts).replace(" ", " ").strip()


def extract_date_from_filename(filename: str) -> str:
    """Extract date string from filename like followup_Airbnb_20260705.txt."""
    name = Path(filename).stem
    parts = name.split("_")
    if parts and parts[-1].isdigit() and len(parts[-1]) == 8:
        return parts[-1]
    return ""


def build_company_email_index() -> dict:
    """
    Build a lookup: company_name → {url, contact_email, source}.
    Merges apply_tracker + job_postings + matched_jobs + contact_emails.json.
    """
    index = {}

    # 1) apply_tracker.csv — has url, company
    if APPLY_TRACKER.exists():
        with open(APPLY_TRACKER, "r") as f:
            for row in csv.DictReader(f):
                company = row.get("company", "").strip()
                url = row.get("url", "").strip()
                if company:
                    key = company.lower()
                    index.setdefault(key, {"company": company, "url": url, "contact_email": ""})

    # 2) job_postings.csv — has company, url
    if JOB_POSTINGS_CSV.exists():
        with open(JOB_POSTINGS_CSV, "r") as f:
            for row in csv.DictReader(f):
                company = row.get("company", "").strip()
                url = row.get("url", "").strip()
                if company:
                    key = company.lower()
                    if key not in index:
                        index[key] = {"company": company, "url": url, "contact_email": ""}

    # 3) matched_jobs.csv — has company, url
    if MATCHED_CSV.exists():
        with open(MATCHED_CSV, "r") as f:
            for row in csv.DictReader(f):
                company = row.get("company", "").strip()
                url = row.get("url", "").strip()
                if company:
                    key = company.lower()
                    if key not in index:
                        index[key] = {"company": company, "url": url, "contact_email": ""}

    # 4) contact_emails.json — scraped contact emails
    if CONTACT_EMAILS_JSON.exists():
        try:
            contacts = json.loads(CONTACT_EMAILS_JSON.read_text())
            for company, data in contacts.items():
                key = company.lower()
                best_email = data.get("best", "")
                if best_email and key in index:
                    index[key]["contact_email"] = best_email
                    index[key]["email_source"] = data.get("domain", "")
                elif best_email:
                    # Add new entry if not exists
                    index[key] = {
                        "company": company,
                        "url": "",
                        "contact_email": best_email,
                        "email_source": data.get("domain", ""),
                    }
        except Exception as e:
            print(f"  ⚠️  Failed to load contact_emails.json: {e}")

    return index


def find_contact_email(company: str, index: dict) -> str:
    """Try to find a contact/careers email for a company."""
    entry = index.get(company.lower(), {})
    email = entry.get("contact_email", "")
    if email:
        return email
    return ""


# ── Gmail API ────────────────────────────────────────────────────

def get_gmail_access_token() -> str:
    """Get a fresh Gmail access token using OAuth2 refresh token."""
    try:
        resp = httpx.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "refresh_token": GOOGLE_REFRESH_TOKEN,
                "grant_type": "refresh_token",
            },
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()["access_token"]
    except Exception as e:
        print(f"  ❌ Failed to get Gmail access token: {e}")
        return ""


def _build_mime(to_email: str, subject: str, body: str, attach_resume: bool = True):
    """Build a MIME message, optionally attaching the resume PDF."""
    pdf_path = DEFAULT_RESUME if (attach_resume and DEFAULT_RESUME.exists()) else None

    if pdf_path:
        msg = MIMEMultipart()
        msg.attach(MIMEText(body, "plain", "utf-8"))
        with open(pdf_path, "rb") as f:
            att = MIMEApplication(f.read(), _subtype="pdf")
            att.add_header("Content-Disposition", "attachment", filename=pdf_path.name)
            msg.attach(att)
    else:
        msg = MIMEText(body, "plain", "utf-8")

    msg["to"] = to_email
    msg["from"] = f"Chaowalit Greepoke <{GMAIL_SENDER}>"
    msg["reply-to"] = CONTACT_EMAIL
    msg["subject"] = subject
    return msg


def send_email_via_gmail(access_token: str, to_email: str, subject: str, body: str) -> dict:
    """Send email via Gmail API with resume attachment. Returns {success, message_id, error}."""
    msg = _build_mime(to_email, subject, body)
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")

    try:
        resp = httpx.post(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            json={"raw": raw},
            timeout=30,
        )
        if resp.status_code == 200:
            msg_id = resp.json().get("id", "")
            return {"success": True, "message_id": msg_id, "error": ""}
        else:
            return {"success": False, "message_id": "", "error": f"HTTP {resp.status_code}: {resp.text[:200]}"}
    except Exception as e:
        return {"success": False, "message_id": "", "error": str(e)}


def create_gmail_draft(access_token: str, to_email: str, subject: str, body: str) -> dict:
    """Create a Gmail draft with resume attachment. Returns {success, draft_id, error}."""
    msg = _build_mime(to_email, subject, body)
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")

    try:
        resp = httpx.post(
            "https://gmail.googleapis.com/gmail/v1/users/me/drafts",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            json={
                "message": {
                    "raw": raw,
                }
            },
            timeout=30,
        )
        if resp.status_code == 200:
            draft_id = resp.json().get("id", "")
            return {"success": True, "draft_id": draft_id, "error": ""}
        else:
            return {"success": False, "draft_id": "", "error": f"HTTP {resp.status_code}: {resp.text[:200]}"}
    except Exception as e:
        return {"success": False, "draft_id": "", "error": str(e)}


# ── Telegram ─────────────────────────────────────────────────────

def send_telegram(message: str) -> bool:
    """Send Telegram notification."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        resp = httpx.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }, timeout=10)
        resp.raise_for_status()
        return True
    except Exception:
        return False


# ── Main Logic ───────────────────────────────────────────────────

def get_pending_emails(date_filter: str = "") -> list:
    """Get list of unsent email files, optionally filtered by date."""
    if not FOLLOWUP_EMAILS_DIR.exists():
        print("❌ followup_emails/ directory not found")
        return []

    log = load_sent_log()
    applied_companies = load_applied_companies()
    pending = []

    for filepath in sorted(FOLLOWUP_EMAILS_DIR.glob("followup_*.txt")):
        filename = filepath.name

        # Skip already sent/drafted
        if is_already_sent(filename, log):
            continue

        # Date filter
        if date_filter:
            file_date = extract_date_from_filename(filename)
            if file_date != date_filter:
                continue

        company = extract_company_from_filename(filename)

        # Skip previous employers
        if is_previous_employer(company):
            continue

        # Skip companies that never received an application email
        if company.lower() not in applied_companies:
            continue

        email_data = parse_email_file(filepath)

        pending.append({
            "file": filename,
            "path": filepath,
            "company": company,
            "subject": email_data["subject"],
            "body": email_data["body"],
            "date": extract_date_from_filename(filename),
        })

    return pending


def show_status():
    """Show sent/pending summary."""
    log = load_sent_log()
    pending = get_pending_emails()

    sent_count = len(log.get("sent", []))
    draft_count = len(log.get("drafts_created", []))
    failed_count = len(log.get("failed", []))

    print(f"\n{'='*60}")
    print(f"  AUTO SEND EMAIL — STATUS")
    print(f"{'='*60}\n")
    print(f"  ✅ Sent:           {sent_count}")
    print(f"  📝 Drafts created: {draft_count}")
    print(f"  ❌ Failed:         {failed_count}")
    print(f"  ⏳ Pending:        {len(pending)}")
    print()

    if log.get("sent"):
        print(f"  Last 5 sent:")
        for entry in log["sent"][-5:]:
            print(f"    • {entry['company']} — {entry.get('sent_at', '?')[:10]}")
        print()

    if pending:
        print(f"  Pending emails:")
        for p in pending[:10]:
            print(f"    • {p['company']} ({p['file']})")
        if len(pending) > 10:
            print(f"    ... and {len(pending) - 10} more")
    print()


def run_auto_send(dry_run: bool = True, limit: int = 0, date_filter: str = "",
                  send_telegram: bool = False):
    """Main auto-send logic."""
    pending = get_pending_emails(date_filter)

    if not pending:
        print("✅ No pending emails to process")
        return

    if limit > 0:
        pending = pending[:limit]

    print(f"\n{'='*60}")
    mode = "DRY RUN" if dry_run else "LIVE SEND"
    print(f"  AUTO SEND EMAIL — {mode}")
    print(f"{'='*60}\n")
    print(f"  Processing {len(pending)} email(s)\n")

    # Build company → email lookup
    company_index = build_company_email_index()

    # Get Gmail access token (only if actually sending)
    access_token = ""
    if not dry_run and GMAIL_API_ENABLED:
        access_token = get_gmail_access_token()
        if not access_token:
            print("❌ Could not get Gmail access token. Aborting send.")
            return

    log = load_sent_log()
    results = {"sent": 0, "drafts": 0, "skipped_no_email": 0, "failed": 0}
    telegram_lines = []

    for i, item in enumerate(pending, 1):
        company = item["company"]
        subject = item["subject"]
        body = item["body"]
        filename = item["file"]

        print(f"  {i}. {company}")
        print(f"     Subject: {subject[:60]}")

        # Find contact email
        to_email = find_contact_email(company, company_index)

        if not to_email:
            # No contact email → create Gmail draft (user fills in To: and sends)
            if not dry_run and access_token:
                # Create draft with user's own email as placeholder To:
                result = create_gmail_draft(
                    access_token, GMAIL_SENDER, subject, body
                )
                if result["success"]:
                    print(f"     📝 Gmail draft created (ID: {result['draft_id']})")
                    log.setdefault("drafts_created", []).append({
                        "file": filename,
                        "company": company,
                        "draft_id": result["draft_id"],
                        "created_at": datetime.now().isoformat(),
                    })
                    results["drafts"] += 1
                    telegram_lines.append(f"📝 Draft: {company}")
                else:
                    print(f"     ❌ Draft failed: {result['error']}")
                    log.setdefault("failed", []).append({
                        "file": filename,
                        "company": company,
                        "error": result["error"],
                        "at": datetime.now().isoformat(),
                    })
                    results["failed"] += 1
            else:
                print(f"     ⏭️  No contact email — will create draft in live mode")
                results["skipped_no_email"] += 1
        else:
            # Have contact email → send directly
            print(f"     To: {to_email}")
            if not dry_run and access_token:
                result = send_email_via_gmail(access_token, to_email, subject, body)
                if result["success"]:
                    print(f"     ✅ Sent (ID: {result['message_id']})")
                    log.setdefault("sent", []).append({
                        "file": filename,
                        "company": company,
                        "to": to_email,
                        "message_id": result["message_id"],
                        "sent_at": datetime.now().isoformat(),
                    })
                    results["sent"] += 1
                    telegram_lines.append(f"✅ Sent: {company} → {to_email}")
                else:
                    print(f"     ❌ Failed: {result['error']}")
                    log.setdefault("failed", []).append({
                        "file": filename,
                        "company": company,
                        "to": to_email,
                        "error": result["error"],
                        "at": datetime.now().isoformat(),
                    })
                    results["failed"] += 1
            else:
                print(f"     🔍 [dry-run] Would send to {to_email}")
                results["sent"] += 1

        print()

    # Save log
    if not dry_run:
        save_sent_log(log)

    # Summary
    print(f"{'='*60}")
    print(f"  RESULTS")
    print(f"{'='*60}\n")
    print(f"  ✅ Sent:           {results['sent']}")
    print(f"  📝 Drafts created: {results['drafts']}")
    print(f"  ⏭️  Skipped (no email): {results['skipped_no_email']}")
    print(f"  ❌ Failed:         {results['failed']}")
    print()

    if dry_run:
        print("  💡 This was a dry run. Use --send to actually send/create drafts.")
        print()

    # Telegram notification
    if send_telegram and not dry_run and telegram_lines:
        msg = f"📧 <b>AUTO SEND EMAIL</b>\n\n"
        msg += "\n".join(telegram_lines[:15])
        if len(telegram_lines) > 15:
            msg += f"\n... and {len(telegram_lines) - 15} more"
        msg += f"\n\n✅ {results['sent']} sent | 📝 {results['drafts']} drafts | ❌ {results['failed']} failed"
        send_telegram(msg)
        print("  📱 Telegram notification sent")
        print()


def main():
    parser = argparse.ArgumentParser(
        description="Auto Send Email — send follow-up drafts via Gmail API"
    )
    parser.add_argument("--send", action="store_true",
                        help="Actually send emails (default is dry-run)")
    parser.add_argument("--limit", type=int, default=0,
                        help="Max emails to process (0 = all)")
    parser.add_argument("--date", type=str, default="",
                        help="Filter by date in filename (e.g. 20260705)")
    parser.add_argument("--status", action="store_true",
                        help="Show sent/pending summary")
    parser.add_argument("--send-telegram", action="store_true",
                        help="Send Telegram notification after sending")
    parser.add_argument("--reset", action="store_true",
                        help="Reset the sent log (allow re-sending)")
    args = parser.parse_args()

    if args.status:
        show_status()
        return

    if args.reset:
        if SENT_LOG.exists():
            SENT_LOG.unlink()
        print("✅ Sent log reset")
        return

    if args.send:
        assert_no_network_send_without_flag(want_send=True, action="auto_send_email")

    dry_run = not args.send
    run_auto_send(
        dry_run=dry_run,
        limit=args.limit,
        date_filter=args.date,
        send_telegram=args.send_telegram,
    )


if __name__ == "__main__":
    main()
