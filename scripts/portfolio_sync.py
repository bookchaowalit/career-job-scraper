#!/usr/bin/env python3
"""
Portfolio Sync — Push matched jobs + skills data to portfolio site.

Generates JSON data files that can be consumed by a portfolio website:
  - Top matched jobs showcase
  - Skills & expertise data
  - Company intelligence highlights
  - Activity stats

Usage:
    python3 portfolio_sync.py                    # Generate all portfolio data
    python3 portfolio_sync.py --output ./public  # Custom output directory
    python3 portfolio_sync.py --dry-run          # Preview only
    python3 portfolio_sync.py --send-telegram    # Notify via Telegram
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

# ── Paths ────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
PORTFOLIO_DATA_DIR = DATA_DIR / "portfolio_data"

# Source data files
MATCHED_CSV = DATA_DIR / "matched_jobs.csv"
COMPANY_INTEL_CSV = DATA_DIR / "company_intel.csv"
SKILLS_GAP_CSV = DATA_DIR / "skills_gap.csv"
SALARY_CSV = DATA_DIR / "salary_benchmark.csv"
APPLY_TRACKER_CSV = DATA_DIR / "apply_tracker.csv"
ALL_JOBS_CSV = DATA_DIR / "all_jobs.csv"
DEEP_DESC_CSV = DATA_DIR / "job_descriptions_deep.csv"

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# ── Profile ──────────────────────────────────────────────────────────────────
PROFILE = {
    "name": "Chaowalit \"Book\" Greepoke",
    "title": "Senior Full-Stack Developer",
    "email": "bookchaowalit.work@gmail.com",
    "website": "bookchaowalit.com",
    "github": "github.com/bookchaowalit",
    "location": "Bangkok, Thailand",
    "open_to": ["Remote", "Relocation"],
    "summary": (
        "Senior Full-Stack Developer with 8+ years of experience building "
        "scalable web applications, cloud infrastructure, and data pipelines. "
        "Passionate about clean code, automation, and delivering impactful solutions."
    ),
}


def load_matched_jobs(min_score=8, limit=50):
    """Load top matched jobs for portfolio showcase."""
    if not MATCHED_CSV.exists():
        return []
    jobs = []
    with open(MATCHED_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                score = float(row.get("_score", row.get("score", 0)))
            except (ValueError, TypeError):
                score = 0
            if score >= min_score:
                jobs.append({
                    "title": row.get("title", ""),
                    "company": row.get("company", ""),
                    "location": row.get("location", ""),
                    "score": score,
                    "source": row.get("source", ""),
                    "url": row.get("url", ""),
                    "salary": row.get("salary", ""),
                    "matched_at": row.get("matched_at", ""),
                })
    jobs.sort(key=lambda x: x["score"], reverse=True)
    return jobs[:limit]


def load_company_intel(limit=20):
    """Load company intelligence highlights."""
    if not COMPANY_INTEL_CSV.exists():
        return []
    companies = []
    with open(COMPANY_INTEL_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            companies.append({
                "company": row.get("company", ""),
                "industry": row.get("industry", ""),
                "size": row.get("size", ""),
                "tech_stack": row.get("tech_stack", ""),
                "remote_policy": row.get("remote_policy", ""),
                "funding": row.get("funding", ""),
            })
    return companies[:limit]


def load_skills_data():
    """Load skills gap analysis data."""
    skills = {"have": [], "gaps": [], "trending": []}
    if not SKILLS_GAP_CSV.exists():
        return skills
    with open(SKILLS_GAP_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            skill = row.get("skill", "")
            status = row.get("status", "").lower()
            if status == "gap":
                skills["gaps"].append(skill)
            elif status == "have":
                skills["have"].append(skill)
            else:
                skills["trending"].append(skill)
    return skills


def load_activity_stats():
    """Load pipeline activity statistics."""
    stats = {
        "total_jobs_scraped": 0,
        "total_matched": 0,
        "total_applied": 0,
        "total_companies": 0,
        "total_deep_scrapes": 0,
        "last_updated": datetime.now().isoformat(),
    }
    # Count CSVs
    for csv_path, key in [
        (ALL_JOBS_CSV, "total_jobs_scraped"),
        (MATCHED_CSV, "total_matched"),
        (APPLY_TRACKER_CSV, "total_applied"),
        (COMPANY_INTEL_CSV, "total_companies"),
        (DEEP_DESC_CSV, "total_deep_scrapes"),
    ]:
        if csv_path.exists():
            try:
                with open(csv_path, "r", encoding="utf-8") as f:
                    stats[key] = sum(1 for _ in csv.DictReader(f))
            except Exception:
                pass
    return stats


def generate_portfolio_json(jobs, companies, skills, stats):
    """Generate the main portfolio data JSON."""
    data = {
        "profile": PROFILE,
        "generated_at": datetime.now().isoformat(),
        "stats": stats,
        "top_opportunities": [
            {
                "title": j["title"],
                "company": j["company"],
                "location": j["location"],
                "score": j["score"],
                "source": j["source"],
            }
            for j in jobs[:20]
        ],
        "companies_interested": companies[:15],
        "skills": {
            "core": PROFILE.get("summary", "").split(".")[0] if PROFILE.get("summary") else "",
            "technical": [
                "Python", "JavaScript", "TypeScript", "React", "Next.js",
                "Node.js", "Django", "FastAPI", "AWS", "Docker",
                "PostgreSQL", "MongoDB", "Redis", "GraphQL", "CI/CD",
            ],
            "gaps": skills.get("gaps", [])[:10],
            "learning": skills.get("trending", [])[:10],
        },
        "availability": {
            "status": "Open to opportunities",
            "type": ["Full-time remote", "Contract", "Freelance"],
            "location_preference": "Remote / Bangkok / Relocation OK",
            "notice_period": "2 weeks",
        },
    }
    return data


def generate_jobs_showcase_json(jobs):
    """Generate a jobs showcase JSON for portfolio widget."""
    showcase = {
        "title": "Active Job Matches",
        "description": "High-quality job matches from my automated pipeline",
        "last_updated": datetime.now().isoformat(),
        "jobs": [
            {
                "title": j["title"],
                "company": j["company"],
                "location": j["location"],
                "match_score": j["score"],
                "source": j["source"],
                "url": j["url"],
            }
            for j in jobs[:30]
        ],
    }
    return showcase


def generate_skills_badge_json(skills):
    """Generate skills badge data for portfolio."""
    badge = {
        "title": "Skills & Expertise",
        "last_updated": datetime.now().isoformat(),
        "core_skills": [
            {"name": s, "level": "expert"} for s in [
                "Python", "JavaScript", "TypeScript", "React", "Node.js",
                "AWS", "Docker", "PostgreSQL",
            ]
        ],
        "strong_skills": [
            {"name": s, "level": "advanced"} for s in [
                "Next.js", "Django", "FastAPI", "MongoDB", "Redis",
                "GraphQL", "CI/CD", "Terraform",
            ]
        ],
        "learning_now": [
            {"name": s, "level": "learning"} for s in skills.get("gaps", [])[:8]
        ],
    }
    return badge


def save_portfolio_data(data_dict, output_dir, dry_run=False):
    """Save all portfolio data files."""
    output_path = Path(output_dir) if output_dir else PORTFOLIO_DATA_DIR
    output_path.mkdir(parents=True, exist_ok=True)

    files = {
        "portfolio.json": data_dict["main"],
        "jobs_showcase.json": data_dict["jobs"],
        "skills_badge.json": data_dict["skills"],
    }

    for filename, content in files.items():
        filepath = output_path / filename
        if dry_run:
            print(f"  [DRY-RUN] Would write {filepath}")
        else:
            filepath.write_text(json.dumps(content, indent=2, default=str))
            print(f"  [OK] {filepath}")

    return output_path


def build_telegram_message(data_dict):
    """Build Telegram notification message."""
    main = data_dict["main"]
    stats = main.get("stats", {})
    lines = [
        "<b>🌐 Portfolio Sync Complete</b>",
        f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        f"📊 Jobs Scraped: {stats.get('total_jobs_scraped', 0):,}",
        f"🎯 Matched: {stats.get('total_matched', 0):,}",
        f"📝 Applied: {stats.get('total_applied', 0)}",
        f"🏢 Companies: {stats.get('total_companies', 0)}",
        "",
        f"🔝 Top Match: {main['top_opportunities'][0]['title'] if main.get('top_opportunities') else '—'}",
        f"   at {main['top_opportunities'][0]['company'] if main.get('top_opportunities') else '—'}",
    ]
    return "\n".join(lines)


def send_telegram(message):
    """Send message to Telegram."""
    try:
        resp = httpx.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=15,
        )
        if resp.status_code == 200:
            print("[OK] Telegram notification sent")
        else:
            print(f"[WARN] Telegram returned {resp.status_code}")
    except Exception as e:
        print(f"[WARN] Telegram error: {e}")


def main():
    parser = argparse.ArgumentParser(description="Portfolio Data Sync")
    parser.add_argument("--output", type=str, default=None, help="Output directory")
    parser.add_argument("--min-score", type=float, default=8, help="Min job score")
    parser.add_argument("--limit", type=int, default=50, help="Max jobs to include")
    parser.add_argument("--dry-run", action="store_true", help="Preview without saving")
    parser.add_argument("--send-telegram", action="store_true", help="Send Telegram summary")
    args = parser.parse_args()

    print("=" * 60)
    print("  Portfolio Data Sync")
    print("=" * 60)

    # Load data
    print("\nLoading pipeline data...")
    jobs = load_matched_jobs(min_score=args.min_score, limit=args.limit)
    print(f"  Matched jobs: {len(jobs)}")

    companies = load_company_intel(limit=20)
    print(f"  Companies: {len(companies)}")

    skills = load_skills_data()
    print(f"  Skills: {len(skills['have'])} have, {len(skills['gaps'])} gaps")

    stats = load_activity_stats()
    print(f"  Total jobs scraped: {stats['total_jobs_scraped']:,}")

    # Generate data
    print("\nGenerating portfolio data...")
    main_data = generate_portfolio_json(jobs, companies, skills, stats)
    jobs_data = generate_jobs_showcase_json(jobs)
    skills_data = generate_skills_badge_json(skills)

    data_dict = {"main": main_data, "jobs": jobs_data, "skills": skills_data}

    # Save
    output_dir = args.output or str(PORTFOLIO_DATA_DIR)
    print(f"\nSaving to {output_dir}...")
    save_portfolio_data(data_dict, output_dir, dry_run=args.dry_run)

    # Telegram
    if args.send_telegram:
        msg = build_telegram_message(data_dict)
        send_telegram(msg)

    print("\n[DONE] Portfolio sync complete")


if __name__ == "__main__":
    main()
