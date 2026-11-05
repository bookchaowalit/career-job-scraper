#!/usr/bin/env python3
"""
Send follow-up emails for previously sent job applications via Gmail API.

Reads application_send_log.json for all sent applications, generates personalized
follow-up emails using the checking_in template, and sends them via Gmail API.

Usage:
    python3 scripts/send_followup_emails.py                    # Dry run
    python3 scripts/send_followup_emails.py --send             # Actually send
    python3 scripts/send_followup_emails.py --send --limit 10  # Send first 10
    python3 scripts/send_followup_emails.py --company "Agoda"  # Specific company
"""

import base64
import csv
import json
import os
import sys
import time
from datetime import datetime
from email.mime.text import MIMEText
from pathlib import Path

# Add scripts to path for imports
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from repo_paths import DATA_DIR, load_env
from safety import assert_no_network_send_without_flag

load_env()

from email_templates import is_thai_company
from send_application_emails import is_non_hiring_email

# Paths
SEND_LOG_FILE = DATA_DIR / "application_send_log.json"
FOLLOWUP_LOG_FILE = DATA_DIR / "followup_log.json"
TRACKER_FILE = DATA_DIR / "apply_tracker.csv"

# User profile
USER = {
    "name": 'Chaowalit "Book" Greepoke',
    "name_th": 'เชาวลิต "บุ๊ค" กรีโภค',
    "email": "bookchaowalit.work@gmail.com",
    "phone": "+66 65-416-9146",
    "portfolio": "bookchaowalit.com",
    "linkedin": "linkedin.com/in/chaowalit-greepoke",
}

# Follow-up delay: minimum days after original send before following up
MIN_DAYS_SINCE_SEND = 2
# Gmail API sends as the account the refresh token belongs to; replies go to CONTACT_EMAIL.
CONTACT_EMAIL = os.getenv("CONTACT_EMAIL", "bookchaowalit.work@gmail.com")


def load_gmail_service():
    """Load Gmail API service using OAuth2 refresh token from .env."""
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
    except ImportError:
        print("ERROR: google packages not installed. Run:")
        print("  pip3 install --user google-api-python-client google-auth-httplib2 google-auth-oauthlib")
        sys.exit(1)

    refresh_token = os.getenv("GOOGLE_REFRESH_TOKEN", "")
    client_id = os.getenv("GOOGLE_CLIENT_ID", "")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "")

    if not (refresh_token and client_id and client_secret):
        print("ERROR: Gmail OAuth credentials not found in .env")
        sys.exit(1)

    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri='https://oauth2.googleapis.com/token',
        client_id=client_id,
        client_secret=client_secret,
        scopes=['https://mail.google.com/']
    )
    creds.refresh(Request())
    return build('gmail', 'v1', credentials=creds)


def load_send_log() -> list:
    """Load application send log."""
    if SEND_LOG_FILE.exists():
        return json.loads(SEND_LOG_FILE.read_text())
    return []


def load_followup_log() -> dict:
    """Load follow-up log.

    The log is the only record of who was already followed up. If it exists
    but cannot be read, refuse to continue: treating it as empty would send
    duplicate follow-ups and then overwrite the saved history.
    """
    if not FOLLOWUP_LOG_FILE.exists():
        return {"runs": [], "sent": []}
    try:
        data = json.loads(FOLLOWUP_LOG_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise RuntimeError(
            f"{FOLLOWUP_LOG_FILE} is unreadable ({e}); fix or move it before sending follow-ups"
        ) from e
    # Old format: list of individual entries
    if isinstance(data, list):
        return {"runs": [], "sent": data}
    if isinstance(data, dict):
        data.setdefault("runs", [])
        data.setdefault("sent", [])
        return data
    raise RuntimeError(f"{FOLLOWUP_LOG_FILE} is not a JSON object or list; refusing to overwrite it")


def save_followup_log(log: dict):
    """Save follow-up log."""
    with open(FOLLOWUP_LOG_FILE, 'w') as f:
        json.dump(log, f, indent=2, ensure_ascii=False)


def get_already_followed_up(followup_log: dict) -> set:
    """Get set of (company, to) tuples already followed up."""
    already = set()
    # Check sent entries
    for entry in followup_log.get("sent", []):
        key = (entry.get("company", "").lower(), entry.get("to", "").lower())
        already.add(key)
    # Check runs
    for run in followup_log.get("runs", []):
        for entry in run.get("entries", []):
            key = (entry.get("company", "").lower(), entry.get("to", "").lower())
            already.add(key)
    return already


def generate_followup_email_en(company: str, title: str, sent_date: str) -> dict:
    """Generate English follow-up email."""
    subject = f"Following Up - {title} Application at {company}"
    body = f"""Hi {company} Hiring Team,

I hope you're doing well. I'm following up on my application for the {title} position at {company}, which I submitted on {sent_date}.

I remain very interested in this opportunity and would love to know if there are any updates on the hiring timeline. My background in full-stack development, cloud infrastructure, and system design aligns well with what your team is looking for.

Please let me know if there's anything else I can provide to support my application — happy to send additional work samples or schedule a call at your convenience.

Thank you for your time and consideration.

Best regards,
{USER['name']}
{USER['phone']}
{USER['email']}
{USER['linkedin']}
{USER['portfolio']}"""
    return {"subject": subject, "body": body, "language": "en"}


def generate_followup_email_th(company: str, title: str, sent_date: str) -> dict:
    """Generate Thai follow-up email."""
    subject = f"ติดตามใบสมัคร - ตำแหน่ง {title} ที่ {company}"
    body = f"""สวัสดีครับ ทีมงาน {company},

ผมชื่อ {USER['name_th']} ครับ ผมได้สมัครตำแหน่ง {title} ที่ {company} เมื่อ {sent_date} และอยากติดตามสถานะใบสมัคร

ผมยังสนใจตำแหน่งนี้มากและอยากทราบว่ามีความคืบหน้าอย่างไรบ้าง หากต้องการข้อมูลเพิ่มเติม หรือต้องการนัดพูดคุย สามารถแจ้งได้ทันทีครับ

ขอบคุณสำหรับเวลาและการพิจารณาครับ

ขอแสดงความนับถือ,
{USER['name_th']}
{USER['phone']}
{USER['email']}
{USER['portfolio']}"""
    return {"subject": subject, "body": body, "language": "th"}


def generate_followup_email(company: str, title: str, sent_date: str) -> dict:
    """Generate follow-up email, choosing Thai or English based on company."""
    if is_thai_company(company):
        return generate_followup_email_th(company, title, sent_date)
    else:
        return generate_followup_email_en(company, title, sent_date)


def create_message(to, subject, body) -> dict:
    """Create a MIME message for Gmail API (no attachment for follow-ups)."""
    message = MIMEText(body, 'plain', 'utf-8')
    message['to'] = to
    message['reply-to'] = CONTACT_EMAIL
    message['subject'] = subject
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')
    return {'raw': raw}


def send_email(service, to, subject, body) -> dict:
    """Send an email via Gmail API."""
    try:
        message = create_message(to, subject, body)
        result = service.users().messages().send(userId='me', body=message).execute()
        return {
            'success': True,
            'message_id': result.get('id'),
            'to': to,
            'subject': subject,
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'to': to,
            'subject': subject,
        }


def update_tracker_note(company: str, note_text: str):
    """Update apply_tracker.csv notes for matching company."""
    if not TRACKER_FILE.exists():
        return

    entries = []
    updated = 0
    with open(TRACKER_FILE, 'r') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        for row in reader:
            row_company = row.get('company', '').strip()
            if row_company.lower() == company.lower():
                existing_note = row.get('note', '')
                if 'follow-up sent' not in existing_note.lower():
                    row['note'] = f"{existing_note} | {note_text}".strip(" |")
                    updated += 1
            entries.append(row)

    if updated > 0 and fieldnames:
        with open(TRACKER_FILE, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for entry in entries:
                writer.writerow(entry)

    return updated


def get_bounced_emails(send_log: list) -> set:
    """Get set of bounced email addresses."""
    return {
        e.get('to', '').lower()
        for e in send_log
        if e.get('status') == 'bounced'
    }


def build_followup_candidates(send_log: list, followup_log: dict, company_filter: str = None) -> list:
    """
    Build list of follow-up candidates from sent applications.
    
    Filters:
    - Only status='sent' entries
    - Skip bounced emails
    - Skip already followed up
    - Skip if sent too recently (< MIN_DAYS_SINCE_SEND days)
    - Deduplicate by (company, to)
    """
    bounced = get_bounced_emails(send_log)
    already_done = get_already_followed_up(followup_log)
    
    candidates = []
    seen = set()
    cutoff = datetime.now()
    
    for entry in send_log:
        if entry.get('status') != 'sent':
            continue
        
        to = entry.get('to', '').lower()
        company = entry.get('company', '')
        title = entry.get('title', '')
        
        if not company or not title or not to:
            continue
        
        # Skip bounced
        if to in bounced:
            continue
        
        # Skip non-hiring emails (info/support/hello/contact)
        if is_non_hiring_email(to):
            continue
        
        # Skip already followed up
        if (company.lower(), to) in already_done:
            continue
        
        # Skip if too recent
        sent_at_str = entry.get('sent_at', '')
        try:
            sent_at = datetime.fromisoformat(sent_at_str)
            days_since = (cutoff - sent_at).days
            if days_since < MIN_DAYS_SINCE_SEND:
                continue
        except (ValueError, TypeError):
            days_since = 999  # Unknown date, allow follow-up
        
        # Deduplicate by (company, to)
        key = (company.lower(), to)
        if key in seen:
            continue
        seen.add(key)
        
        # Company filter
        if company_filter and company_filter.lower() not in company.lower():
            continue
        
        # Format sent date nicely
        try:
            sent_date_display = sent_at.strftime('%B %d, %Y')
        except Exception:
            sent_date_display = 'recently'
        
        candidates.append({
            'company': company,
            'title': title,
            'to': to,
            'sent_at': sent_at_str,
            'days_since': days_since,
            'sent_date_display': sent_date_display,
            'original_subject': entry.get('subject', ''),
        })
    
    return candidates


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Send follow-up emails for job applications")
    parser.add_argument("--send", action="store_true", help="Actually send emails (default is dry run)")
    parser.add_argument("--company", type=str, help="Filter by company name")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of emails to send")
    parser.add_argument("--delay", type=float, default=3.0, help="Delay between sends in seconds (default: 3)")
    args = parser.parse_args()

    # Block live send before candidate lookup or any side effects
    # (consistent with send_application_emails / auto_send_email)
    if args.send:
        assert_no_network_send_without_flag(want_send=True, action="follow-up email send")

    print(f"\n{'='*70}")
    print(f"  {'DRY RUN' if not args.send else 'SENDING'} FOLLOW-UP EMAILS")
    print(f"  DATA_DIR: {DATA_DIR}")
    print(f"{'='*70}\n")

    # Load data
    send_log = load_send_log()
    followup_log = load_followup_log()

    sent_count = sum(1 for e in send_log if e.get('status') == 'sent')
    bounced_count = sum(1 for e in send_log if e.get('status') == 'bounced')
    print(f"Application send log: {sent_count} sent, {bounced_count} bounced")

    # Build candidates
    candidates = build_followup_candidates(send_log, followup_log, company_filter=args.company)
    print(f"Follow-up candidates: {len(candidates)}")

    if args.limit > 0:
        candidates = candidates[:args.limit]
        print(f"Limited to {len(candidates)} candidates")

    if not candidates:
        print("\nNo candidates need follow-up.")
        return

    # Display candidates
    print(f"\n{'='*70}")
    for i, c in enumerate(candidates, 1):
        is_thai = is_thai_company(c['company'])
        lang = 'TH' if is_thai else 'EN'
        print(f"{i:3d}. [{lang}] {c['company'][:30]:30s} | {c['title'][:35]:35s} | {c['days_since']}d ago")
        print(f"     To: {c['to']}")
    print(f"{'='*70}")

    if not args.send:
        print(f"\nDry run complete. {len(candidates)} follow-ups would be sent.")
        print(f"Live send requires --send + BOOK_JOB_LIVE_SEND_ENABLED=1")
        print(f"+ BOOK_JOB_SEND_UNLOCK=I_UNDERSTAND_LIVE_SEND")
        return

    # Send (gate already enforced above when --send)
    print(f"\nSending {len(candidates)} follow-up emails (delay: {args.delay}s)...")
    service = load_gmail_service()

    sent = 0
    failed = 0
    run_entries = []
    run_start = datetime.now()

    for i, c in enumerate(candidates):
        company = c['company']
        title = c['title']
        to = c['to']

        # Generate email
        email = generate_followup_email(company, title, c['sent_date_display'])

        print(f"\n{i+1}/{len(candidates)} → {to} ({company[:25]})")
        print(f"   Subject: {email['subject'][:60]}")

        # Send
        result = send_email(service, to, email['subject'], email['body'])

        entry = {
            'company': company,
            'title': title,
            'to': to,
            'subject': email['subject'],
            'language': email['language'],
            'original_sent_at': c['sent_at'],
            'followup_at': datetime.now().isoformat(),
            'days_since_original': c['days_since'],
        }

        if result['success']:
            entry['status'] = 'sent'
            entry['message_id'] = result.get('message_id', '')
            sent += 1
            print(f"   ✓ Sent (ID: {result.get('message_id', 'N/A')})")

            # Update tracker
            updated = update_tracker_note(company, f"Follow-up sent {datetime.now().strftime('%Y-%m-%d')}")
            if updated:
                print(f"   ✓ Tracker updated ({updated} rows)")
        else:
            entry['status'] = 'failed'
            entry['error'] = result.get('error', 'unknown')
            failed += 1
            print(f"   ✗ Failed: {entry['error']}")

        run_entries.append(entry)

        # Delay (except after last)
        if i < len(candidates) - 1:
            time.sleep(args.delay)

    # Save follow-up log
    followup_log = load_followup_log()  # Reload in case of concurrent writes
    if "sent" not in followup_log:
        followup_log["sent"] = []
    followup_log["sent"].extend(run_entries)
    followup_log["runs"].append({
        "timestamp": run_start.isoformat(),
        "followup_count": len(candidates),
        "sent": sent,
        "failed": failed,
        "entries": run_entries,
    })
    # Keep last 100 runs
    followup_log["runs"] = followup_log["runs"][-100:]
    # Keep last 1000 sent entries
    followup_log["sent"] = followup_log["sent"][-1000:]
    save_followup_log(followup_log)

    # Summary
    print(f"\n{'='*70}")
    print(f"  FOLLOW-UP CAMPAIGN COMPLETE")
    print(f"{'='*70}")
    print(f"  Total candidates: {len(candidates)}")
    print(f"  Sent: {sent}")
    print(f"  Failed: {failed}")
    print(f"  Log: {FOLLOWUP_LOG_FILE}")
    print()


if __name__ == "__main__":
    main()
