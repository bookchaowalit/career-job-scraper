#!/usr/bin/env python3
"""
Auto-Apply Pipeline — prepare application materials for high-scoring jobs (80+).

Generates tailored resume + cover letter, saves email draft, and logs status as
**prepared** (not submitted). This script does not send applications.

Usage:
    python3 auto_apply.py                        # Prepare drafts for score 80+ jobs
    python3 auto_apply.py --min-score 70         # Lower threshold
    python3 auto_apply.py --limit 5              # Max 5 preparations per run
    python3 auto_apply.py --dry-run              # Preview only
    python3 auto_apply.py --send-telegram        # Notify via Telegram
"""

import argparse
import csv
import json
import os
import sys
from datetime import datetime
from pathlib import Path

try:
    import httpx
except ImportError:
    raise SystemExit(
        "Missing dependency 'httpx'. "
        "Install via project venv: pip install -r requirements.txt "
        "(scripts must not pip-install at runtime)"
    )

from repo_paths import REPO_ROOT as ROOT, DATA_DIR, SCRIPTS_DIR, ensure_data_dirs, load_env
from safety import (
    STATUS_PREPARED,
    is_already_handled,
)

load_env()

MATCHED_CSV = DATA_DIR / "matched_jobs.csv"
APPLY_TRACKER = DATA_DIR / "apply_tracker.csv"
EMAIL_DRAFTS_DIR = DATA_DIR / "email_drafts"
RESUMES_DIR = DATA_DIR / "tailored_resumes"
AUTO_APPLY_LOG = DATA_DIR / "auto_apply_log.json"

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "5255551291")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")

sys.path.insert(0, str(SCRIPTS_DIR))

from job_target_policy import (  # noqa: E402
    HUMAN_VERIFICATION_FIELDS,
    SOURCE_EVIDENCE_FIELDS,
    is_qualified_for_preparation,
)

POLICY_FIELDS = [
    "qualification_status",
    "policy_version",
    "employment_type",
    "work_arrangement",
    "thailand_eligibility",
    "concurrent_employment",
    "engagement_boundary",
    "application_readiness",
    "qualification_reasons",
    *HUMAN_VERIFICATION_FIELDS,
    *SOURCE_EVIDENCE_FIELDS,
]

# Import previous employers blocklist
try:
    from send_application_emails import PREVIOUS_EMPLOYERS
except ImportError:
    PREVIOUS_EMPLOYERS = set()


def is_previous_employer(company: str) -> bool:
    """Check if company matches a previous employer (case-insensitive partial match)."""
    c = company.lower().strip()
    return any(pe in c or c in pe for pe in PREVIOUS_EMPLOYERS)


def load_csv(path: Path) -> list:
    if not path.exists():
        return []
    with open(path, "r") as f:
        return list(csv.DictReader(f))


def get_handled_urls() -> set:
    """URLs already prepared or submitted (skip re-preparation)."""
    tracker = load_csv(APPLY_TRACKER)
    return {
        row.get("url", "").lower()
        for row in tracker
        if is_already_handled(row.get("status"))
    }


def get_candidate_jobs(min_score: int = 80) -> list:
    """Get high-scoring jobs that have not been prepared/submitted yet."""
    matched = load_csv(MATCHED_CSV)
    if not matched:
        return []

    handled = get_handled_urls()

    # Also check auto_apply_log (prepared materials)
    already_prepared = set()
    if AUTO_APPLY_LOG.exists():
        with open(AUTO_APPLY_LOG, "r") as f:
            log = json.load(f)
            for entry in log.get("prepared", log.get("applied", [])):
                already_prepared.add(entry.get("url", "").lower())

    candidates = []
    for job in matched:
        if not is_qualified_for_preparation(job):
            continue
        url = job.get("url", "").lower()
        try:
            score = int(job.get("_score", job.get("score", 0)))
        except (ValueError, TypeError):
            score = 0

        if score < min_score:
            continue
        if url in handled or url in already_prepared:
            continue
        if not url:
            continue
        # Skip previous employers
        if is_previous_employer(job.get('company', '')):
            continue

        candidates.append({
            "title": job.get("title", ""),
            "company": job.get("company", ""),
            "url": job.get("url", ""),
            "score": score,
            "location": job.get("location", ""),
            "salary": job.get("salary", ""),
            "tags": job.get("tags", job.get("_matched", "")),
            "source": job.get("source", ""),
            "posted": job.get("posted", ""),
            **{field: job.get(field, "") for field in POLICY_FIELDS},
        })

    candidates.sort(key=lambda x: x["score"], reverse=True)
    return candidates


def generate_cover_letter(job: dict) -> str:
    """Generate cover letter using AI or template fallback."""
    if not OPENROUTER_API_KEY:
        return _template_cover_letter(job)

    prompt = f"""Generate a concise professional cover letter for:

JOB: {job['title']}
COMPANY: {job.get('company', 'Unknown')}
LOCATION: {job.get('location', 'Remote')}
KEY REQUIREMENTS: {job.get('tags', 'Python, React, TypeScript')}

ABOUT ME:
- Senior full-stack developer, 8+ years experience
- Python, React, TypeScript, Django, FastAPI, Next.js
- Built job scraping pipeline processing 2,000+ jobs
- AI integration specialist (OpenAI, LangChain, LLM)
- 50+ freelance projects for international clients
- Bangkok, Thailand (open to remote)

REQUIREMENTS:
1. 3-4 paragraphs, concise
2. Highlight relevant experience for THIS role
3. Show enthusiasm
4. End with call to action
5. Sign as: Chaowalit "Book" Greepoke"""

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
                "max_tokens": 800,
                "temperature": 0.7,
            },
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"    AI cover letter failed ({e}), using template")
        return _template_cover_letter(job)


def _template_cover_letter(job: dict) -> str:
    """Template cover letter fallback."""
    title = job.get("title", "Developer")
    company = job.get("company", "Company")
    skills = job.get("tags", "Python, React, TypeScript")
    skill_list = [s.strip() for s in skills.split(",") if s.strip()][:5]

    return f"""Subject: Application for {title} - Chaowalit Greepoke

Dear Hiring Manager,

I am writing to express my strong interest in the {title} position at {company}. With over 8 years of experience in full-stack development and AI integration, I am confident in my ability to contribute effectively to your team.

My technical expertise aligns with your requirements. I have extensive experience with {', '.join(skill_list) if skill_list else 'Python, React, and TypeScript'}. Recently, I built a comprehensive job scraping pipeline that processes over 2,000 jobs daily from 20+ job boards, implementing a 7-factor scoring algorithm for intelligent job matching.

What sets me apart is my ability to deliver high-quality solutions for international clients. I have successfully completed 50+ freelance projects across US, EU, and APAC markets, consistently receiving 5-star ratings.

I would welcome the opportunity to discuss how my experience aligns with your needs. I can be reached at bookchaowalit.work@gmail.com or through my portfolio at bookchaowalit.com.

Best regards,
Chaowalit "Book" Greepoke
Senior Full-Stack Developer
Email: bookchaowalit.work@gmail.com
Portfolio: bookchaowalit.com
GitHub: github.com/bookchaowalit
Location: Bangkok, Thailand (Open to Remote)
"""


def generate_resume_snippet(job: dict) -> str:
    """Generate a tailored resume snippet for the job."""
    title = job.get("title", "Developer")
    company = job.get("company", "Company")
    skills = job.get("tags", "")
    skill_list = [s.strip() for s in skills.split(",") if s.strip()][:10]

    return f"""# Resume: {title} @ {company}
Generated: {datetime.now().strftime('%Y-%m-%d')} | Score: {job.get('score', 0)}

## CHAOWALIT GREepoke "BOOK"
**Senior Full-Stack Developer | AI Integration Specialist**
Email: bookchaowalit.work@gmail.com | GitHub: github.com/bookchaowalit

## PROFESSIONAL SUMMARY
Senior full-stack developer with 8+ years, specializing in {', '.join(skill_list[:3]) if skill_list else 'Python, React, TypeScript'}.
Expertise in scalable applications, AI solutions, and remote collaboration.

## CORE SKILLS
{', '.join(skill_list) if skill_list else 'Python, React, TypeScript, Django, FastAPI, Node.js'}

## EXPERIENCE
- Built job scraping pipeline processing 2,000+ jobs from 20+ boards
- AI-powered matching system with 7-factor scoring
- 50+ freelance projects for international clients (US, EU, APAC)
- Telegram bot for real-time job notifications
- Portfolio dashboard with 40+ domain projects
"""


def save_email_draft(job: dict, cover_letter: str) -> Path:
    """Save email draft to file."""
    EMAIL_DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    company = job.get("company", "unknown").replace(" ", "_")[:20]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{company}_auto_{timestamp}.eml"
    filepath = EMAIL_DRAFTS_DIR / filename

    with open(filepath, "w") as f:
        f.write(f"From: Chaowalit Greepoke <bookchaowalit.work@gmail.com>\n")
        f.write(f"To: [RECIPIENT]\n")
        f.write(f"Subject: Application for {job.get('title', 'Developer')} - Chaowalit Greepoke\n")
        f.write(f"Date: {datetime.now().strftime('%a, %d %b %Y %H:%M:%S %z')}\n\n")
        f.write(cover_letter)

    return filepath


def save_resume_snippet(job: dict, content: str) -> Path:
    """Save resume snippet to file."""
    RESUMES_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = f"{job['company']}_{job['title']}"[:50]
    safe_name = "".join(c if c.isalnum() or c in " -_" else "_" for c in safe_name)
    filename = f"{safe_name.replace(' ', '_')}_auto_resume.md"
    filepath = RESUMES_DIR / filename
    with open(filepath, "w") as f:
        f.write(content)
    return filepath


def log_auto_apply(job: dict, draft_path: Path, resume_path: Path):
    """Log preparation action (draft/resume only — not a live submission)."""
    log = {}
    if AUTO_APPLY_LOG.exists():
        with open(AUTO_APPLY_LOG, "r") as f:
            log = json.load(f)
    if "prepared" not in log:
        # Migrate legacy key if present
        log["prepared"] = list(log.get("applied", []))
    log["prepared"].append({
        "url": job.get("url", ""),
        "title": job.get("title", ""),
        "company": job.get("company", ""),
        "score": job.get("score", 0),
        "draft_file": str(draft_path),
        "resume_file": str(resume_path),
        "status": STATUS_PREPARED,
        "prepared_at": datetime.now().isoformat(),
    })
    # Keep legacy key empty/outdated intentionally; readers should prefer "prepared"
    log.setdefault("applied", [])
    with open(AUTO_APPLY_LOG, "w") as f:
        json.dump(log, f, indent=2)


def log_apply_status(url: str, status: str, note: str = "", job: dict | None = None):
    """Update the tracker without dropping qualification evidence."""
    required_fields = ["url", "title", "company", "status", "note", "updated_at", *POLICY_FIELDS]
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entries = []
    found = False
    existing_fields = []
    if APPLY_TRACKER.exists():
        with open(APPLY_TRACKER, "r") as f:
            reader = csv.DictReader(f)
            existing_fields = list(reader.fieldnames or [])
            for row in reader:
                if row.get("url") == url:
                    row["status"] = status
                    row["note"] = note
                    row["updated_at"] = now
                    if job:
                        for field in required_fields:
                            if job.get(field) not in (None, ""):
                                row[field] = job[field]
                    found = True
                entries.append(row)
    if not found:
        entry = {"url": url, "status": status, "note": note, "updated_at": now}
        if job:
            for field in required_fields:
                if job.get(field) not in (None, ""):
                    entry[field] = job[field]
        entries.append(entry)
    fieldnames = list(dict.fromkeys(existing_fields + required_fields))
    with open(APPLY_TRACKER, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for entry in entries:
            writer.writerow(entry)


def send_telegram(message: str) -> bool:
    """Send message to Telegram."""
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
        print("  ✓ Telegram notification sent")
        return True
    except Exception as e:
        print(f"  ✗ Telegram failed: {e}")
        return False


def build_telegram_message(prepared: list) -> str:
    """Build Telegram summary of prepared (not submitted) applications."""
    lines = [
        f"<b>📝 AUTO-PREPARE COMPLETE</b>",
        f"<b>{datetime.now().strftime('%Y-%m-%d %H:%M')}</b>",
        "",
        f"Prepared {len(prepared)} draft(s) — NOT submitted:",
        "",
    ]
    for job in prepared:
        lines.append(f"  <b>{job['title'][:40]}</b>")
        lines.append(f"  🏢 {job['company'][:30]} | Score: {job['score']}")
        lines.append(f"  📧 Draft + Resume ready")
        if job.get("url"):
            lines.append(f"  🔗 <a href=\"{job['url']}\">View Job</a>")
        lines.append("")

    lines.append("─────────────────")
    lines.append(f"<i>Review drafts in: data/email_drafts/</i>")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Prepare application drafts for high-scoring jobs (does NOT submit)"
    )
    parser.add_argument("--min-score", type=int, default=80, help="Minimum score to prepare (default: 80)")
    parser.add_argument("--limit", type=int, default=3, help="Max preparations per run (default: 3)")
    parser.add_argument("--send-telegram", action="store_true", help="Notify via Telegram")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be prepared")
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"  AUTO-PREPARE PIPELINE (drafts only — not submitted)")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  DATA_DIR: {DATA_DIR}")
    print(f"{'='*60}\n")

    candidates = get_candidate_jobs(min_score=args.min_score)
    print(f"  Found {len(candidates)} candidate jobs (score >= {args.min_score})")

    if not candidates:
        print("  No jobs need preparation. All done!")
        return

    to_process = candidates[:args.limit]

    if args.dry_run:
        print(f"\n  DRY RUN — Would prepare drafts for:")
        for job in to_process:
            print(f"    • [{job['score']}] {job['title'][:40]} @ {job['company'][:30]}")
            print(f"      {job['url'][:80]}")
        return

    ensure_data_dirs("email_drafts", "tailored_resumes")

    # Process each job — materials only; status = prepared (not submitted)
    prepared = []
    for job in to_process:
        print(f"\n  ▶ Preparing: {job['title'][:40]} @ {job['company'][:30]}...")

        # Generate cover letter
        print(f"    Generating cover letter...")
        cover_letter = generate_cover_letter(job)

        # Generate resume snippet
        print(f"    Generating resume snippet...")
        resume = generate_resume_snippet(job)

        # Save files
        draft_path = save_email_draft(job, cover_letter)
        resume_path = save_resume_snippet(job, resume)
        print(f"    ✓ Draft: {draft_path.name}")
        print(f"    ✓ Resume: {resume_path.name}")

        # Log status as prepared — never "submitted" / "auto_applied"
        log_auto_apply(job, draft_path, resume_path)
        log_apply_status(
            job["url"],
            STATUS_PREPARED,
            f"score={job['score']}, draft={draft_path.name}",
            job=job,
        )

        job["draft_file"] = str(draft_path)
        job["resume_file"] = str(resume_path)
        prepared.append(job)

    print(f"\n{'='*60}")
    print(f"  SUMMARY: Prepared {len(prepared)} job(s) (NOT submitted)")
    print(f"  Status written: {STATUS_PREPARED}")
    print(f"  Drafts: {EMAIL_DRAFTS_DIR}")
    print(f"  Resumes: {RESUMES_DIR}")
    print(f"{'='*60}\n")

    if args.send_telegram and prepared:
        msg = build_telegram_message(prepared)
        send_telegram(msg)


if __name__ == "__main__":
    main()
