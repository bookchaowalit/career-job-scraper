#!/usr/bin/env python3
"""
Auto-Tailor Pipeline — Auto-generate tailored resumes for high-scoring jobs.

Connects tailor_resume.py to the pipeline:
  1. Reads matched_jobs.csv for jobs scoring 40+
  2. Checks apply_tracker.csv to skip already-tailored jobs
  3. Generates tailored resume drafts (AI or template fallback)
  4. Saves to tailored_resumes/ directory
  5. Optionally notifies via Telegram when resumes are ready

Usage:
    python3 auto_tailor.py                    # Generate for all score 40+ jobs
    python3 auto_tailor.py --min-score 50     # Only jobs scoring 50+
    python3 auto_tailor.py --limit 3          # Max 3 resumes per run
    python3 auto_tailor.py --send-telegram    # Notify when done
    python3 auto_tailor.py --dry-run          # Show what would be generated
"""

import argparse
import csv
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from job_target_policy import is_qualified_for_preparation

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
SCRIPTS_DIR = ROOT / "scripts"

MATCHED_CSV = DATA_DIR / "matched_jobs.csv"
APPLY_TRACKER = DATA_DIR / "apply_tracker.csv"
RESUMES_DIR = DATA_DIR / "tailored_resumes"
TAILOR_LOG = DATA_DIR / "tailor_log.json"

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "5255551291")

# Import tailor_resume functions
sys.path.insert(0, str(SCRIPTS_DIR))


def load_csv(path: Path) -> list:
    if not path.exists():
        return []
    with open(path, "r") as f:
        return list(csv.DictReader(f))


def get_already_tailored() -> set:
    """Get URLs that already have tailored resumes."""
    tailored = set()
    if RESUMES_DIR.exists():
        for f in RESUMES_DIR.glob("*.md"):
            # Extract URL from filename (encoded)
            name = f.stem.replace("_resume", "").replace("_", " ")
            tailored.add(name.lower())
    # Also check tailor_log.json
    if TAILOR_LOG.exists():
        with open(TAILOR_LOG, "r") as f:
            log = json.load(f)
            for entry in log.get("tailored", []):
                tailored.add(entry.get("url", "").lower())
    return tailored


def get_applied_urls() -> set:
    """Get URLs that have been applied to."""
    tracker = load_csv(APPLY_TRACKER)
    return {row.get("url", "").lower() for row in tracker
            if row.get("status") in ("applied", "tailored")}


def get_candidate_jobs(min_score: int = 40) -> list:
    """Get high-scoring jobs that need tailored resumes."""
    matched = load_csv(MATCHED_CSV)
    if not matched:
        return []

    tailored = get_already_tailored()
    applied = get_applied_urls()

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
        if url in tailored or url in applied:
            continue
        if not url:
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
        })

    candidates.sort(key=lambda x: x["score"], reverse=True)
    return candidates


def generate_resume_for_job(job: dict) -> str:
    """Generate a tailored resume for a job. Uses AI if available, else template."""
    try:
        from tailor_resume import generate_tailored_resume, generate_tailored_resume_template
        # Try AI first, fall back to template
        result = generate_tailored_resume(job)
        return result
    except ImportError:
        return generate_template_resume(job)


def generate_template_resume(job: dict) -> str:
    """Generate a template-based tailored resume (no AI needed)."""
    title = job.get("title", "Developer")
    company = job.get("company", "Company")
    skills = job.get("tags", "")
    skill_list = [s.strip() for s in skills.split(",") if s.strip()][:10]
    location = job.get("location", "Remote")
    salary = job.get("salary", "")

    now = datetime.now().strftime("%Y-%m-%d")

    resume = f"""# Tailored Resume: {title} @ {company}
Generated: {now} | Score: {job.get('score', 0)} | URL: {job.get('url', '')}

---

## CHAOWALIT GREepoke "BOOK"
**Senior Full-Stack Developer | AI Integration Specialist**
Bangkok, Thailand | Remote-Ready
Email: bookchaowalit.work@gmail.com | GitHub: github.com/bookchaowalit

---

## PROFESSIONAL SUMMARY

Senior full-stack developer with 8+ years of experience, specializing in
{', '.join(skill_list[:3]) if skill_list else 'Python, React, and TypeScript'}.
Proven expertise building scalable applications and integrating AI solutions.
Delivering high-quality results for international clients across US, EU, and APAC.

**Tailored for:** {title} at {company}
**Location:** {location}
{'**Salary Range:** ' + salary if salary else ''}

---

## CORE SKILLS (Prioritized for this role)

{'Primary: ' + ', '.join(skill_list[:5]) if skill_list else ''}

- **Languages:** Python, JavaScript, TypeScript, Go, SQL
- **Frontend:** React, Next.js, Vue.js, Tailwind CSS, Redux
- **Backend:** Django, FastAPI, Node.js, Express, GraphQL, REST APIs
- **Database:** PostgreSQL, MySQL, MongoDB, Redis, Elasticsearch
- **Cloud & DevOps:** AWS, GCP, Docker, Kubernetes, Terraform, CI/CD
- **AI/ML:** OpenAI API, LangChain, LLM integration, RAG systems

---

## EXPERIENCE HIGHLIGHTS

- Built job scraping pipeline processing 2,000+ jobs from 20+ boards
- Developed AI-powered matching system with 7-factor scoring algorithm
- Integrated Telegram bot for real-time job notifications
- Created portfolio dashboard showcasing 40+ domain projects
- Delivered freelance projects for international clients (US, EU, APAC)

---

## WHY I'M A GREAT FIT

This role at {company} aligns with my expertise in {', '.join(skill_list[:3]) if skill_list else 'full-stack development'}.
I bring proven experience in remote collaboration, delivering high-quality code,
and building scalable solutions that drive business results.

---

## LANGUAGES
- Thai (Native)
- English (Professional)

---

*This resume was auto-generated by Solo Empire pipeline. Review before sending.*
"""
    return resume


def save_resume(job: dict, content: str) -> Path:
    """Save tailored resume to file."""
    RESUMES_DIR.mkdir(parents=True, exist_ok=True)

    # Create safe filename
    safe_name = f"{job['company']}_{job['title']}"[:50]
    safe_name = "".join(c if c.isalnum() or c in " -_" else "_" for c in safe_name)
    safe_name = safe_name.replace(" ", "_")
    filename = f"{safe_name}_resume.md"
    filepath = RESUMES_DIR / filename

    with open(filepath, "w") as f:
        f.write(content)

    return filepath


def log_tailor(job: dict, filepath: Path):
    """Log tailored resume to track what's been done."""
    log = {}
    if TAILOR_LOG.exists():
        with open(TAILOR_LOG, "r") as f:
            log = json.load(f)

    if "tailored" not in log:
        log["tailored"] = []

    log["tailored"].append({
        "url": job.get("url", ""),
        "title": job.get("title", ""),
        "company": job.get("company", ""),
        "score": job.get("score", 0),
        "file": str(filepath),
        "generated_at": datetime.now().isoformat(),
    })

    with open(TAILOR_LOG, "w") as f:
        json.dump(log, f, indent=2)


def build_telegram_message(generated: list) -> str:
    """Build Telegram notification about new tailored resumes."""
    lines = []
    lines.append(f"<b>📝 AUTO-TAILORED RESUMES READY</b>")
    lines.append(f"<b>{datetime.now().strftime('%Y-%m-%d %H:%M')}</b>")
    lines.append("")
    lines.append(f"Generated {len(generated)} resume(s):")
    lines.append("")

    for job in generated:
        lines.append(f"  <b>{job['title'][:40]}</b>")
        lines.append(f"  🏢 {job['company'][:30]} | Score: {job['score']}")
        lines.append(f"  📁 {Path(job['file']).name}")
        lines.append("")

    lines.append("─────────────────")
    lines.append(f"<i>Review in: data/tailored_resumes/</i>")

    return "\n".join(lines)


def send_telegram(message: str):
    """Send message to Telegram."""
    import httpx
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
        print("✓ Telegram notification sent")
        return True
    except Exception as e:
        print(f"✗ Telegram failed: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Auto-Tailor Resume Pipeline")
    parser.add_argument("--min-score", type=int, default=40, help="Minimum score to auto-tailor (default: 40)")
    parser.add_argument("--limit", type=int, default=3, help="Max resumes to generate per run (default: 3)")
    parser.add_argument("--send-telegram", action="store_true", help="Notify via Telegram when done")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be generated")
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"  AUTO-TAILOR RESUME PIPELINE")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")

    candidates = get_candidate_jobs(min_score=args.min_score)
    print(f"  Found {len(candidates)} candidate jobs (score >= {args.min_score})")

    if not candidates:
        print("  No jobs need tailored resumes. All done!")
        return

    # Limit
    to_process = candidates[:args.limit]

    if args.dry_run:
        print(f"\n  DRY RUN — Would generate resumes for:")
        for job in to_process:
            print(f"    • [{job['score']}] {job['title'][:40]} @ {job['company'][:30]}")
        return

    # Generate resumes
    generated = []
    for job in to_process:
        print(f"\n  ▶ Generating resume: {job['title'][:40]} @ {job['company'][:30]}...")
        content = generate_resume_for_job(job)
        filepath = save_resume(job, content)
        log_tailor(job, filepath)
        job["file"] = str(filepath)
        generated.append(job)
        print(f"    ✓ Saved: {filepath.name}")

    print(f"\n{'='*60}")
    print(f"  SUMMARY: Generated {len(generated)} tailored resume(s)")
    print(f"  Location: {RESUMES_DIR}")
    print(f"{'='*60}\n")

    if args.send_telegram and generated:
        msg = build_telegram_message(generated)
        send_telegram(msg)


if __name__ == "__main__":
    main()
