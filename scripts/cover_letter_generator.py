#!/usr/bin/env python3
"""
AI Cover Letter Generator
Generates tailored cover letters per job using matched job data + resume profile.
"""

import argparse
import csv
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Paths
SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR.parent / "data"
OUTPUT_DIR = DATA_DIR / "cover_letters"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# User profile
USER = {
    "name": "Chaowalit 'Book' Greepoke",
    "title": "Senior Full-Stack Developer",
    "email": "bookchaowalit.work@gmail.com",
    "location": "Bangkok, Thailand (Open to Remote)",
    "phone": "+66-XXX-XXX-XXXX",
    "linkedin": "linkedin.com/in/bookchaowalit",
    "portfolio": "bookchaowalit.com",
    "summary": (
        "Senior Full-Stack Developer with 8+ years building scalable web applications, "
        "APIs, and cloud infrastructure. Expertise in React, Next.js, Node.js, Python, "
        "TypeScript, PostgreSQL, and AWS/GCP. Proven track record delivering production "
        "systems handling 100K+ users. Passionate about clean architecture, performance "
        "optimization, and developer experience."
    ),
    "top_skills": [
        "React", "Next.js", "TypeScript", "Node.js", "Python", "PostgreSQL",
        "AWS", "Docker", "GraphQL", "REST APIs", "Redis", "MongoDB",
        "CI/CD", "TailwindCSS", "Express.js", "FastAPI", "Prisma"
    ],
}

# AI setup
try:
    from openai import OpenAI
    client = OpenAI(
        api_key=os.getenv("OPENROUTER_API_KEY", ""),
        base_url="https://openrouter.ai/api/v1"
    )
    AI_AVAILABLE = True
except Exception:
    AI_AVAILABLE = False


def load_matched_jobs(limit=100):
    """Load matched jobs from CSV."""
    jobs = []
    csv_path = DATA_DIR / "matched_jobs.csv"
    if not csv_path.exists():
        return jobs
    try:
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader):
                if i >= limit:
                    break
                jobs.append(row)
    except Exception as e:
        print(f"  ⚠️  Error loading jobs: {e}")
    return jobs


def load_job_postings(limit=200):
    """Load job postings."""
    jobs = []
    csv_path = DATA_DIR / "job_postings.csv"
    if not csv_path.exists():
        return jobs
    try:
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader):
                if i >= limit:
                    break
                jobs.append(row)
    except Exception as e:
        print(f"  ⚠️  Error loading postings: {e}")
    return jobs


def find_job_by_id(job_id, matched=None, postings=None):
    """Find a specific job by ID."""
    if matched:
        for j in matched:
            jid = j.get("id", j.get("job_id", ""))
            if jid == job_id:
                return j
    if postings:
        for j in postings:
            jid = j.get("id", j.get("job_id", ""))
            if jid == job_id:
                return j
    return None


def generate_with_ai(job, style="professional"):
    """Generate cover letter using AI."""
    job_title = job.get("title", "Software Engineer")
    company = job.get("company", "Company")
    description = job.get("description", job.get("matched_keywords", ""))[:1500]
    location = job.get("location", "Remote")
    salary = job.get("salary_min", "")

    style_instructions = {
        "professional": "Write in a professional, confident tone. Focus on achievements and value proposition.",
        "startup": "Write in an energetic, passionate tone. Emphasize adaptability, ownership, and excitement for the mission.",
        "enterprise": "Write in a formal, structured tone. Highlight process, scale, and enterprise-grade experience.",
        "creative": "Write in a creative, personable tone. Show personality while demonstrating technical depth.",
    }

    prompt = f"""Generate a tailored cover letter for this job application.

JOB DETAILS:
- Title: {job_title}
- Company: {company}
- Location: {location}
- Description/Keywords: {description}

CANDIDATE PROFILE:
- Name: {USER['name']}
- Current Title: {USER['title']}
- Location: {USER['location']}
- Email: {USER['email']}
- Summary: {USER['summary']}
- Top Skills: {', '.join(USER['top_skills'])}

STYLE: {style_instructions.get(style, style_instructions['professional'])}

REQUIREMENTS:
1. Maximum 400 words
2. Opening: Hook that shows genuine interest in {company}
3. Body 1: Highlight 2-3 most relevant achievements/skills for THIS role
4. Body 2: Show understanding of the company's challenges/opportunities
5. Closing: Clear call to action
6. Use specific numbers and metrics where possible
7. Do NOT use generic phrases like "I am writing to express my interest"
8. Sign off as: Book Greepoke

Output ONLY the cover letter text, no markdown formatting."""

    if not AI_AVAILABLE:
        return generate_fallback(job, style)

    try:
        response = client.chat.completions.create(
            model="openai/gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=800,
            temperature=0.7,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"  ⚠️  AI error: {e}, using fallback template")
        return generate_fallback(job, style)


def generate_fallback(job, style="professional"):
    """Generate cover letter from template when AI unavailable."""
    job_title = job.get("title", "Software Engineer")
    company = job.get("company", "Company")
    location = job.get("location", "")
    keywords = job.get("matched_keywords", job.get("description", "")[:200])

    letter = f"""Dear Hiring Manager,

I'm excited to apply for the {job_title} position at {company}. As a Senior Full-Stack Developer with 8+ years of experience building scalable web applications and cloud infrastructure, I believe I can make an immediate impact on your team.

My technical background aligns well with your requirements. I've built and maintained production systems serving 100K+ users using React, Next.js, TypeScript, Node.js, Python, and PostgreSQL. My recent work includes developing a comprehensive job matching pipeline that automates discovery, scraping, and AI-powered matching across 14+ job boards — demonstrating both technical depth and ownership mentality.

What draws me to {company} specifically is the opportunity to work on challenges that combine technical complexity with real-world impact. I thrive in environments where clean architecture, performance optimization, and developer experience are valued — and where I can contribute to both product decisions and technical strategy.

Key qualifications I bring:
• Full-stack expertise across the modern web stack (React/Next.js + Node.js/Python)
• Cloud infrastructure experience (AWS, Docker, CI/CD pipelines)
• Track record of delivering production-grade systems at scale
• Strong communication skills and experience working in distributed teams

I'm based in Bangkok, Thailand, and open to remote opportunities. I'd welcome the chance to discuss how my experience can contribute to {company}'s goals.

Best regards,
Book Greepoke
{USER['email']}
{USER['portfolio']}
"""
    return letter


def save_cover_letter(job_id, company, letter, style):
    """Save cover letter to file."""
    safe_company = "".join(c if c.isalnum() else "_" for c in company)[:30]
    filename = f"{job_id}_{safe_company}_{style}.txt"
    filepath = OUTPUT_DIR / filename
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(letter)
    return filepath


def list_cover_letters():
    """List all generated cover letters."""
    files = sorted(OUTPUT_DIR.glob("*.txt"))
    if not files:
        print("\n📄 No cover letters generated yet.")
        print(f"   Output dir: {OUTPUT_DIR}")
        return

    print(f"\n📄 Cover Letters ({len(files)} files)")
    print("=" * 70)
    for f in files:
        size = f.stat().st_size
        name = f.stem
        print(f"  📝 {name}")
        print(f"     Size: {size:,} bytes | File: {f.name}")
    print("=" * 70)


def batch_generate(jobs, style="professional", limit=10):
    """Generate cover letters for multiple jobs."""
    generated = 0
    for job in jobs[:limit]:
        job_id = job.get("id", job.get("job_id", f"job_{generated}"))
        company = job.get("company", "Unknown")
        title = job.get("title", "Engineer")

        print(f"  Generating for {company} — {title}...")
        letter = generate_with_ai(job, style)
        filepath = save_cover_letter(job_id, company, letter, style)
        print(f"  ✅ Saved: {filepath.name}")
        generated += 1

    return generated


def main():
    parser = argparse.ArgumentParser(description="AI Cover Letter Generator")
    parser.add_argument("--generate", action="store_true", help="Generate cover letter for a job")
    parser.add_argument("--job-id", type=str, help="Job ID to generate for")
    parser.add_argument("--style", type=str, default="professional",
                        choices=["professional", "startup", "enterprise", "creative"],
                        help="Cover letter style")
    parser.add_argument("--batch", action="store_true", help="Generate for top matched jobs")
    parser.add_argument("--limit", type=int, default=5, help="Batch generation limit")
    parser.add_argument("--list", action="store_true", help="List generated letters")
    parser.add_argument("--read", type=str, help="Read a specific letter")
    parser.add_argument("--preview", action="store_true", help="Preview without saving")
    args = parser.parse_args()

    if args.list:
        list_cover_letters()
        return

    if args.read:
        filepath = OUTPUT_DIR / args.read
        if not filepath.exists():
            # Try partial match
            matches = list(OUTPUT_DIR.glob(f"*{args.read}*"))
            if matches:
                filepath = matches[0]
            else:
                print(f"❌ Letter not found: {args.read}")
                return
        print(f"\n{'=' * 70}")
        print(filepath.read_text())
        print(f"{'=' * 70}")
        return

    if args.generate or args.batch:
        matched = load_matched_jobs()
        postings = load_job_postings()

        if not matched and not postings:
            print("❌ No job data found. Run the pipeline first.")
            return

        if args.generate and args.job_id:
            job = find_job_by_id(args.job_id, matched, postings)
            if not job:
                print(f"❌ Job {args.job_id} not found")
                return
            company = job.get("company", "Unknown")
            title = job.get("title", "Engineer")
            print(f"\n🎯 Generating cover letter for: {company} — {title}")
            print(f"   Style: {args.style}")
            letter = generate_with_ai(job, args.style)
            if args.preview:
                print(f"\n{'=' * 70}")
                print(letter)
                print(f"{'=' * 70}")
            else:
                filepath = save_cover_letter(args.job_id, company, letter, args.style)
                print(f"✅ Saved: {filepath}")
        elif args.batch:
            print(f"\n📦 Batch generating {args.limit} cover letters (style: {args.style})...")
            count = batch_generate(matched or postings, args.style, args.limit)
            print(f"\n✅ Generated {count} cover letters in {OUTPUT_DIR}")
        else:
            print("❌ Use --job-id with --generate, or use --batch")
            return

    if not any([args.list, args.read, args.generate, args.batch]):
        parser.print_help()


if __name__ == "__main__":
    main()
