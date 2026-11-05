#!/usr/bin/env python3
"""
Email Application Sender - Auto-drafts and sends job application emails.
Generates personalized cover letters based on job requirements.

Usage:
    python3 email_application.py --url "https://example.com/job/123"
    python3 email_application.py --draft-only
    python3 email_application.py --send --to "hr@company.com"
"""

import argparse
import csv
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from job_target_policy import (
    is_approved_for_submission,
    is_qualified_for_preparation,
    qualify_job,
)
from safety import assert_no_network_send_without_flag

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
MATCHED_CSV = DATA_DIR / "matched_jobs.csv"
JOB_POSTINGS_CSV = DATA_DIR / "job_postings.csv"
EMAIL_DRAFTS_DIR = DATA_DIR / "email_drafts"

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REFRESH_TOKEN = os.getenv("GOOGLE_REFRESH_TOKEN", "")
GMAIL_API_ENABLED = bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET and GOOGLE_REFRESH_TOKEN)
# Gmail API sends as the account the refresh token belongs to; replies go to CONTACT_EMAIL.
GMAIL_SENDER = os.getenv("GMAIL_SENDER", "bookchaowalit@gmail.com")
CONTACT_EMAIL = os.getenv("CONTACT_EMAIL", "bookchaowalit.work@gmail.com")


def get_job_details(url: str) -> dict:
    """Get job details from CSV files."""
    for csv_file in [MATCHED_CSV, JOB_POSTINGS_CSV]:
        if not csv_file.exists():
            continue
        
        with open(csv_file, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("url") == url:
                    details = dict(row)
                    details.update(qualify_job(details))
                    details["url"] = url
                    return details
    
    return None


def generate_cover_letter(job: dict) -> str:
    """Generate personalized cover letter using AI."""
    if not OPENROUTER_API_KEY:
        return generate_cover_letter_template(job)
    
    prompt = f"""Generate a professional cover letter for this job application:

JOB: {job['title']}
COMPANY: {job.get('company', 'Unknown')}
LOCATION: {job.get('location', 'Remote')}
KEY REQUIREMENTS: {job.get('tags', 'Python, React, TypeScript')}

ABOUT ME:
- Senior full-stack developer with 8+ years experience
- Expert in Python, React, TypeScript, Django, FastAPI
- Built job scraping pipeline processing 2,000+ jobs
- AI integration specialist (OpenAI, LangChain, LLM)
- Delivered 50+ freelance projects for international clients
- Based in Bangkok, Thailand (open to remote)

REQUIREMENTS:
1. Keep it concise (3-4 paragraphs)
2. Highlight relevant experience
3. Show enthusiasm for the role
4. Mention specific achievements
5. End with a call to action

TONE: Professional, confident, enthusiastic"""
    
    try:
        resp = httpx.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "openai/gpt-4o-mini",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 1000,
                "temperature": 0.7,
            },
            timeout=30,
        )
        resp.raise_for_status()
        
        data = resp.json()
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"  Warning: AI generation failed ({e}), using template")
        return generate_cover_letter_template(job)


def generate_cover_letter_template(job: dict) -> str:
    """Generate cover letter using template (fallback)."""
    title = job.get("title", "Developer")
    company = job.get("company", "Company")
    location = job.get("location", "Remote")
    
    return f"""Subject: Application for {title} - Chaowalit Greepoke

Dear Hiring Manager,

I am writing to express my strong interest in the {title} position at {company}. With over 8 years of experience in full-stack development and AI integration, I am confident in my ability to contribute effectively to your team.

My technical expertise aligns perfectly with your requirements. I have extensive experience with Python, React, TypeScript, and modern web frameworks including Django and FastAPI. Recently, I built a comprehensive job scraping pipeline that processes over 2,000 jobs daily from 20+ job boards, implementing a 7-factor scoring algorithm for intelligent job matching.

What sets me apart is my ability to deliver high-quality solutions for international clients. I have successfully completed 50+ freelance projects across US, EU, and APAC markets, consistently receiving 5-star ratings. My experience with AI integration, including OpenAI API and LangChain, allows me to build innovative solutions that drive business value.

I am particularly excited about this opportunity at {company} because {add_company_specific_reason(company, title)}. I am eager to bring my technical skills, problem-solving abilities, and passion for building scalable applications to your team.

I would welcome the opportunity to discuss how my experience and skills align with your needs. I am available for a conversation at your convenience and can be reached via email at bookchaowalit.work@gmail.com or through my portfolio at bookchaowalit.com.

Thank you for considering my application. I look forward to the possibility of contributing to {company}'s success.

Best regards,
Chaowalit "Book" Greepoke
Senior Full-Stack Developer
Email: bookchaowalit.work@gmail.com
Portfolio: bookchaowalit.com
GitHub: github.com/bookchaowalit
Location: Bangkok, Thailand (Open to Remote)
"""


def add_company_specific_reason(company: str, title: str) -> str:
    """Add company-specific reason to cover letter."""
    company_lower = company.lower()
    
    if "startup" in company_lower:
        return "of the opportunity to help build something from the ground up"
    elif "ai" in company_lower or "machine learning" in company_lower:
        return "of your focus on AI innovation, which aligns with my expertise in LLM integration"
    elif "remote" in company_lower:
        return "of your remote-first culture, which matches my experience working with distributed teams"
    else:
        return "of your company's reputation for excellence and innovation"


def generate_email_subject(job: dict) -> str:
    """Generate email subject line."""
    title = job.get("title", "Developer")
    company = job.get("company", "")
    
    return f"Application for {title} - Chaowalit Greepoke (8+ years exp)"


def save_email_draft(job: dict, subject: str, body: str) -> Path:
    """Save email draft to file."""
    EMAIL_DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    
    company = job.get("company", "unknown").replace(" ", "_")[:20]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    filename = f"{company}_{timestamp}.eml"
    filepath = EMAIL_DRAFTS_DIR / filename
    
    with open(filepath, "w") as f:
        f.write(f"From: Chaowalit Greepoke <bookchaowalit.work@gmail.com>\n")
        f.write(f"To: [RECIPIENT_EMAIL]\n")
        f.write(f"Subject: {subject}\n")
        f.write(f"Date: {datetime.now().strftime('%a, %d %b %Y %H:%M:%S %z')}\n")
        f.write(f"\n")
        f.write(body)
    
    return filepath


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
        print(f"  ERROR: Failed to get Gmail access token: {e}")
        return ""


def send_email_via_gmail(to_email: str, subject: str, body: str) -> bool:
    """Send email via Gmail API using OAuth2."""
    if not GMAIL_API_ENABLED:
        print("  Gmail API not configured. Save draft instead.")
        return False

    import base64
    from email.mime.text import MIMEText

    access_token = get_gmail_access_token()
    if not access_token:
        return False

    # Build RFC 2822 email
    msg = MIMEText(body, "plain", "utf-8")
    msg["to"] = to_email
    msg["from"] = f"Chaowalit Greepoke <{GMAIL_SENDER}>"
    msg["reply-to"] = CONTACT_EMAIL
    msg["subject"] = subject
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
            print(f"  ✓ Email sent (message ID: {msg_id})")
            return True
        else:
            print(f"  ✗ Gmail API error: {resp.status_code} - {resp.text[:200]}")
            return False
    except Exception as e:
        print(f"  ✗ Failed to send via Gmail API: {e}")
        return False


def send_batch_emails(jobs: list, min_score: int = 70, dry_run: bool = True) -> dict:
    """Send application emails for multiple high-score jobs."""
    results = {"sent": 0, "drafted": 0, "failed": 0, "skipped": 0}

    for job in jobs:
        if not is_qualified_for_preparation(job):
            results["skipped"] += 1
            continue
        if not dry_run and not is_approved_for_submission(job):
            print(f"  BLOCKED: {job.get('title', '')[:50]} has no explicit application approval")
            results["skipped"] += 1
            continue
        score = int(job.get("_score", job.get("score", 0)) or 0)
        if score < min_score:
            results["skipped"] += 1
            continue

        url = job.get("url", "")
        if not url:
            results["skipped"] += 1
            continue

        print(f"\n  Processing: {job.get('title', '')[:50]} at {job.get('company', '')[:20]}")
        cover_letter = generate_cover_letter(job)
        subject = generate_email_subject(job)
        save_email_draft(job, subject, cover_letter)
        results["drafted"] += 1

        if not dry_run:
            to_email = job.get("contact_email", "")
            if to_email:
                if send_email_via_gmail(to_email, subject, cover_letter):
                    results["sent"] += 1
                else:
                    results["failed"] += 1
            else:
                print(f"  No contact email found, saved as draft only")

    return results


def main():
    parser = argparse.ArgumentParser(description="Email Application Sender")
    parser.add_argument("--url", default="", help="Generate email for specific job URL")
    parser.add_argument("--draft-only", action="store_true", help="Only save draft, don't send")
    parser.add_argument("--send", action="store_true", help="Send email (requires --to)")
    parser.add_argument("--to", default="", help="Recipient email address")
    parser.add_argument("--batch", action="store_true", help="Batch send for all high-score jobs")
    parser.add_argument("--min-score", type=int, default=70, help="Minimum score for batch mode")
    parser.add_argument("--no-dry-run", action="store_true", help="Actually send emails (batch mode)")
    args = parser.parse_args()

    live_send = bool((args.send and args.to) or (args.batch and args.no_dry_run))
    if live_send:
        assert_no_network_send_without_flag(want_send=True, action="email_application send")
    
    print(f"\n{'='*80}")
    print(f"  EMAIL APPLICATION SENDER")
    print(f"{'='*80}\n")
    
    EMAIL_DRAFTS_DIR.mkdir(parents=True, exist_ok=True)

    # Batch mode: process all high-score jobs
    if args.batch:
        print(f"Batch mode: processing jobs with score >= {args.min_score}")
        print(f"  Gmail API: {'ENABLED' if GMAIL_API_ENABLED else 'DISABLED'}")
        print(f"  Dry run: {not args.no_dry_run}")
        print()

        # Load matched jobs
        jobs = []
        if MATCHED_CSV.exists():
            with open(MATCHED_CSV, "r") as f:
                jobs = list(csv.DictReader(f))
        print(f"  Found {len(jobs)} matched jobs")

        results = send_batch_emails(jobs, min_score=args.min_score, dry_run=not args.no_dry_run)
        print(f"\n{'='*80}")
        print(f"  BATCH RESULTS")
        print(f"{'='*80}\n")
        print(f"  Drafted: {results['drafted']}")
        print(f"  Sent: {results['sent']}")
        print(f"  Failed: {results['failed']}")
        print(f"  Skipped: {results['skipped']}")
        return

    if not args.url:
        print("ERROR: --url is required")
        print("  Usage: python3 email_application.py --url 'https://example.com/job/123'")
        return
    
    # Get job details
    print(f"Getting job details...")
    job = get_job_details(args.url)
    
    if not job:
        print(f"ERROR: Job not found for URL: {args.url}")
        return

    if args.send and args.to and not is_approved_for_submission(job):
        print("BLOCKED: job requires qualification_status=PASS and application_readiness=APPROVED")
        raise SystemExit(2)
    
    title = job.get("title", "")
    company = job.get("company", "")
    
    print(f"  Job: {title}")
    print(f"  Company: {company}")
    print(f"  Location: {job.get('location', 'Remote')}")
    print()
    
    # Generate cover letter
    print("Generating cover letter...")
    cover_letter = generate_cover_letter(job)
    
    # Generate subject
    subject = generate_email_subject(job)
    
    # Save draft
    print("Saving email draft...")
    draft_path = save_email_draft(job, subject, cover_letter)
    print(f"  ✓ Saved: {draft_path.name}")
    print()
    
    # Display preview
    print(f"{'='*80}")
    print(f"  EMAIL PREVIEW")
    print(f"{'='*80}\n")
    print(f"Subject: {subject}")
    print(f"To: [RECIPIENT_EMAIL]")
    print(f"\n{cover_letter[:500]}...")
    print()
    
    # Send if requested
    if args.send and args.to:
        print(f"Sending email to {args.to}...")
        if send_email_via_gmail(args.to, subject, cover_letter):
            print("  ✓ Email sent successfully")
        else:
            print("  ✗ Failed to send email (saved as draft)")
    elif args.send and not args.to:
        print("WARNING: --send requires --to email address")
    
    print(f"{'='*80}")
    print(f"  NEXT STEPS")
    print(f"{'='*80}\n")
    print(f"  1. Review the email draft: {draft_path}")
    print(f"  2. Find the recipient email (check job posting)")
    print(f"  3. Send with: python3 email_application.py --url '{args.url}' --send --to 'hr@company.com'")
    print()
    print(f"💡 TIP: Personalize further based on company research")
    print(f"   Mention specific projects or values that resonate with you\n")


if __name__ == "__main__":
    main()
