#!/usr/bin/env python3
"""
Application Follow-up Tracker - Sends reminders to follow up on applications.
Tracks application status and sends Telegram reminders.

Usage:
    python3 followup_tracker.py
    python3 followup_tracker.py --days 7
    python3 followup_tracker.py --send-telegram
"""

import argparse
import csv
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

try:
    import httpx
except ImportError:
    raise SystemExit(
        "Missing dependency 'httpx'. "
        "Install via project venv: pip install -r requirements.txt "
        "(scripts must not pip-install at runtime)"
    )

try:
    from dotenv import load_dotenv
    _root = Path(__file__).resolve().parents[1]
    load_dotenv(_root / ".env")
except ImportError:
    pass

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
APPLY_TRACKER = DATA_DIR / "apply_tracker.csv"
JOB_POSTINGS_CSV = DATA_DIR / "job_postings.csv"
MATCHED_CSV = DATA_DIR / "matched_jobs.csv"
FOLLOWUP_EMAILS_DIR = DATA_DIR / "followup_emails"
FOLLOWUP_LOG = DATA_DIR / "followup_log.json"

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "5255551291")


def load_apply_tracker() -> list:
    """Load apply tracker CSV."""
    if not APPLY_TRACKER.exists():
        return []
    
    entries = []
    with open(APPLY_TRACKER, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            entries.append(row)
    
    return entries


def get_job_details(url: str) -> dict:
    """Get job details from job_postings.csv or matched_jobs.csv."""
    for csv_file in [MATCHED_CSV, JOB_POSTINGS_CSV]:
        if not csv_file.exists():
            continue
        
        with open(csv_file, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("url") == url:
                    return {
                        "title": row.get("title", ""),
                        "company": row.get("company", ""),
                        "location": row.get("location", ""),
                        "url": url,
                    }
    
    return {"title": "Unknown", "company": "Unknown", "location": "", "url": url}


def find_applications_needing_followup(days: int = 7) -> list:
    """Find applications that need follow-up (applied or notified, stuck > N days)."""
    entries = load_apply_tracker()
    cutoff = datetime.now() - timedelta(days=days)
    
    followup_needed = []
    
    for entry in entries:
        status = entry.get("status", "")
        updated_at = entry.get("updated_at", "")
        
        # Follow up on "applied" (no response) or "notified" (haven't applied yet)
        if status not in ("applied", "notified"):
            continue
        
        # Parse updated_at
        try:
            applied_date = datetime.strptime(updated_at, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
        
        # Check if it's been `days` since last update
        if applied_date < cutoff:
            # Check if already followed up recently
            note = entry.get("note", "")
            if "followed up" in note.lower():
                continue
            
            job_details = get_job_details(entry["url"])
            
            followup_needed.append({
                "url": entry["url"],
                "title": job_details["title"],
                "company": job_details["company"],
                "location": job_details["location"],
                "applied_date": applied_date.strftime("%Y-%m-%d"),
                "days_since": (datetime.now() - applied_date).days,
                "status": status,
                "note": note,
            })
    
    # Sort by days since (most urgent first)
    followup_needed.sort(key=lambda x: x["days_since"], reverse=True)
    
    return followup_needed


def mark_as_followed_up(url: str):
    """Mark application as followed up."""
    if not APPLY_TRACKER.exists():
        return
    
    entries = []
    with open(APPLY_TRACKER, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("url") == url:
                row["note"] = f"{row.get('note', '')} | Followed up on {datetime.now().strftime('%Y-%m-%d')}".strip(" |")
            entries.append(row)
    
    fieldnames = ["url", "status", "note", "updated_at"]
    with open(APPLY_TRACKER, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for entry in entries:
            writer.writerow(entry)


def send_telegram_message(message: str) -> bool:
    """Send message via Telegram Bot API."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("ERROR: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set")
        return False
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    
    try:
        resp = httpx.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        return True
    except Exception as e:
        print(f"ERROR: Telegram send failed: {e}")
        return False


def generate_followup_message(followup_list: list) -> str:
    """Generate Telegram message for follow-up reminders."""
    if not followup_list:
        return ""
    
    # Separate by type
    applied_stuck = [f for f in followup_list if f["status"] == "applied"]
    notified_stuck = [f for f in followup_list if f["status"] == "notified"]
    
    lines = [
        f"🔔 <b>FOLLOW-UP REMINDER</b>",
        f"",
        f"You have <b>{len(followup_list)}</b> application(s) needing attention:",
        f"",
    ]
    
    if applied_stuck:
        lines.append(f"📤 <b>APPLIED — No response ({len(applied_stuck)}):</b>")
        for i, item in enumerate(applied_stuck[:5], 1):
            title = item["title"][:40]
            company = item["company"][:30]
            days = item["days_since"]
            url = item["url"]
            lines.append(f"  <b>{i}.</b> {title}")
            lines.append(f"     🏢 {company} | 📅 {days}d ago")
            lines.append(f"     🔗 <a href=\"{url}\">View</a>")
        lines.append("")
    
    if notified_stuck:
        lines.append(f"📬 <b>NOTIFIED — Haven't applied yet ({len(notified_stuck)}):</b>")
        for i, item in enumerate(notified_stuck[:5], 1):
            title = item["title"][:40]
            company = item["company"][:30]
            days = item["days_since"]
            url = item["url"]
            lines.append(f"  <b>{i}.</b> {title}")
            lines.append(f"     🏢 {company} | 📅 {days}d since notified")
            lines.append(f"     🔗 <a href=\"{url}\">Apply Now</a>")
        lines.append("")
    
    lines.append("💡 <b>Action items:</b>")
    if applied_stuck:
        lines.append("• Send follow-up email reiterating interest")
        lines.append("• Check if application portal has updates")
    if notified_stuck:
        lines.append("• Apply to notified jobs before they close")
        lines.append("• Update status in tracker after applying")
    
    return "\n".join(lines)


def generate_followup_email(item: dict) -> str:
    """Generate a follow-up email draft for a stuck application."""
    title = item.get("title", "the position")
    company = item.get("company", "your team")
    applied_date = item.get("applied_date", "recently")
    days = item.get("days_since", 7)

    email = f"""Subject: Following Up — {title} Application

Dear Hiring Team at {company},

I hope this message finds you well. I applied for the {title} position on {applied_date} and wanted to follow up to reiterate my strong interest in the role.

With {days} days since my application, I remain very enthusiastic about the opportunity to contribute to {company}. My background in full-stack development, cloud architecture, and building scalable systems aligns well with what your team is building.

I would welcome the chance to discuss how my experience can add value to your projects. Please let me know if there's any additional information I can provide.

Thank you for your time and consideration.

Best regards,
Chaowalit "Book" Greepoke
Senior Full-Stack Developer
bookchaowalit.work@gmail.com
bookchaowalit.com
"""
    return email


def save_followup_email(item: dict, email_content: str) -> Path:
    """Save follow-up email draft to file."""
    FOLLOWUP_EMAILS_DIR.mkdir(parents=True, exist_ok=True)
    company = item.get("company", "unknown").replace(" ", "_").replace("/", "_")[:30]
    filename = f"followup_{company}_{datetime.now().strftime('%Y%m%d')}.txt"
    filepath = FOLLOWUP_EMAILS_DIR / filename
    filepath.write_text(email_content)
    return filepath


def generate_followup_emails(followup_list: list) -> list:
    """Generate follow-up emails for all stuck applications."""
    generated = []
    for item in followup_list:
        email_content = generate_followup_email(item)
        filepath = save_followup_email(item, email_content)
        generated.append({
            "url": item["url"],
            "company": item["company"],
            "title": item["title"],
            "email_path": str(filepath),
            "generated_at": datetime.now().isoformat(),
        })
        print(f"  Generated: {filepath.name}")
    return generated


def load_followup_log_for_update():
    """Return the shared follow-up log in dict form, or ``None`` if unusable.

    ``send_followup_emails`` reads the same file to decide who was already
    followed up, and it accepts the legacy list format (a bare list of sent
    entries). Normalize that form here the same way instead of treating it as
    corrupt: renaming it would make the sender see no log and send duplicate
    follow-ups. An unreadable file is left in place (the sender refuses to run
    on it) and ``None`` is returned so this run is simply not logged.
    """
    import json
    if not FOLLOWUP_LOG.exists():
        return {"runs": []}
    try:
        data = json.loads(FOLLOWUP_LOG.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = None
    if isinstance(data, list):
        return {"runs": [], "sent": data}
    if isinstance(data, dict) and isinstance(data.setdefault("runs", []), list):
        return data
    print(f"  WARNING: {FOLLOWUP_LOG.name} is unreadable; left it untouched and skipped logging this run")
    return None


def log_followup_run(followup_list: list, emails_generated: list):
    """Log follow-up run to JSON."""
    import json
    log = load_followup_log_for_update()
    if log is None:
        return
    log["runs"].append({
        "timestamp": datetime.now().isoformat(),
        "followup_count": len(followup_list),
        "emails_generated": len(emails_generated),
        "companies": [item["company"] for item in followup_list[:10]],
    })
    log["runs"] = log["runs"][-50:]  # Keep last 50 runs
    tmp = FOLLOWUP_LOG.with_name(f"{FOLLOWUP_LOG.name}.tmp")
    tmp.write_text(json.dumps(log, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, FOLLOWUP_LOG)


def main():
    parser = argparse.ArgumentParser(description="Application Follow-up Tracker")
    parser.add_argument("--days", type=int, default=7, help="Follow up after N days (default: 7)")
    parser.add_argument("--send-telegram", action="store_true", help="Send reminder via Telegram")
    parser.add_argument("--remind", action="store_true", help="Same as --send-telegram (alias)")
    parser.add_argument("--mark-done", action="store_true", help="Mark all as followed up")
    parser.add_argument("--generate-emails", action="store_true", help="Generate follow-up email drafts")
    args = parser.parse_args()
    
    print(f"\n{'='*80}")
    print(f"  APPLICATION FOLLOW-UP TRACKER")
    print(f"{'='*80}\n")
    
    # Find applications needing follow-up
    print(f"Finding applications older than {args.days} days...")
    followup_list = find_applications_needing_followup(args.days)
    
    if not followup_list:
        print(f"  ✓ No applications need follow-up")
        print(f"  (Checked {len(load_apply_tracker())} applications)\n")
        return
    
    print(f"  Found {len(followup_list)} applications needing follow-up\n")
    
    # Display results
    print(f"{'='*80}")
    print(f"  APPLICATIONS NEEDING FOLLOW-UP")
    print(f"{'='*80}\n")
    
    for i, item in enumerate(followup_list, 1):
        print(f"{i:2d}. {item['title'][:50]}")
        print(f"    🏢 {item['company']}")
        print(f"    📅 Applied: {item['applied_date']} ({item['days_since']} days ago)")
        print(f"    🔗 {item['url']}")
        print()
    
    # Send Telegram message
    if args.send_telegram or args.remind:
        print("Sending Telegram reminder...")
        message = generate_followup_message(followup_list)
        if send_telegram_message(message):
            print("  ✓ Telegram reminder sent")
        else:
            print("  ✗ Failed to send Telegram reminder")
    
    # Mark as followed up
    if args.mark_done:
        print("Marking all as followed up...")
        for item in followup_list:
            mark_as_followed_up(item["url"])
        print(f"  ✓ Marked {len(followup_list)} applications as followed up")
    
    # Generate follow-up emails
    emails_generated = []
    if args.generate_emails:
        print("\nGenerating follow-up email drafts...")
        emails_generated = generate_followup_emails(followup_list)
        print(f"  ✓ Generated {len(emails_generated)} email drafts in {FOLLOWUP_EMAILS_DIR}")
        log_followup_run(followup_list, emails_generated)
    
    # Summary
    print(f"\n{'='*80}")
    print(f"  SUMMARY")
    print(f"{'='*80}\n")
    print(f"  Applications needing follow-up: {len(followup_list)}")
    print(f"  Oldest application: {followup_list[0]['days_since']} days ago")
    print(f"  Most recent: {followup_list[-1]['days_since']} days ago")
    print()
    print(f"💡 TIP: Run with --send-telegram to get reminders")
    print(f"   Run with --mark-done after following up\n")


if __name__ == "__main__":
    main()
