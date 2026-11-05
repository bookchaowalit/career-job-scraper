#!/usr/bin/env python3
"""
AI Resume & Cover Letter Generator - Uses OpenRouter API to generate
tailored resume and cover letter for specific job postings.

Usage:
    python3 ai_resume_generator.py --url "https://boards.greenhouse.io/..."
    python3 ai_resume_generator.py --url "https://..." --output resume.md
    python3 ai_resume_generator.py --job-file job_description.json
    python3 ai_resume_generator.py --list  # list available models
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

try:
    from dotenv import load_dotenv
    _root = Path(__file__).resolve().parents[1]
    load_dotenv(_root / ".env")
except ImportError:
    pass

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
JOB_DESC_CSV = DATA_DIR / "job_descriptions.csv"
MATCHED_CSV = DATA_DIR / "matched_jobs.csv"
OUTPUT_DIR = DATA_DIR / "generated_resumes"

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1/chat/completions"

# Free models available on OpenRouter (as of 2026)
FREE_MODELS = [
    "google/gemma-3-27b-it:free",
    "meta-llama/llama-4-maverick:free",
    "deepseek/deepseek-chat-v3-0324:free",
    "qwen/qwen3-235b-a22b:free",
]

DEFAULT_MODEL = "google/gemma-3-27b-it:free"

# User profile for resume generation
USER_PROFILE = """
Chaowalit "Book" Greepoke
Full-Stack Developer | Remote-First

CONTACT:
- Email: bookchaowalit.work@gmail.com
- Portfolio: https://bookchaowalit.com
- Location: Thailand (open to remote worldwide)

SKILLS:
- Frontend: React, Next.js, TypeScript, Vue.js, Tailwind CSS, Redux, HTML/CSS
- Backend: Python, Node.js, FastAPI, Django, Flask, Express, REST APIs, GraphQL
- Database: PostgreSQL, MySQL, Redis, MongoDB
- Cloud/DevOps: AWS, GCP, Docker, Linux, Git, CI/CD
- AI/ML: OpenAI API, LLMs, data analytics, prompt engineering
- Other: Agile/Scrum, remote work, full-stack development

EXPERIENCE HIGHLIGHTS:
- Full-stack web application development (React + Python/Node.js)
- API design and development (REST, GraphQL)
- Database design and optimization
- AI/LLM integration into production applications
- Remote-first work across multiple timezones
- Freelance project delivery for international clients

PROJECTS:
- Job scraping pipeline: 20+ job boards, AI matching, Telegram notifications
- Solo empire dashboard: multi-domain business management platform
- Chrome extension: auto-fill for 26+ job application platforms
"""


def list_models():
    """List available free models on OpenRouter."""
    if not OPENROUTER_API_KEY:
        print("ERROR: OPENROUTER_API_KEY not set in .env")
        print("Get your key at https://openrouter.ai")
        return

    print("\nAvailable FREE models on OpenRouter:")
    for model in FREE_MODELS:
        print(f"  • {model}")
    print(f"\nDefault model: {DEFAULT_MODEL}")
    print("\nTo use a different model, pass --model <model_name>")


def get_job_description_from_url(url: str) -> dict:
    """Get job description from CSV by URL."""
    if not JOB_DESC_CSV.exists():
        return {}

    with open(JOB_DESC_CSV, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("url") == url:
                return {
                    "url": url,
                    "title": row.get("page_title", ""),
                    "description": row.get("description", ""),
                    "skills": row.get("skills", ""),
                }

    # Try matched_jobs.csv for basic info
    if MATCHED_CSV.exists():
        with open(MATCHED_CSV, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("url") == url:
                    return {
                        "url": url,
                        "title": row.get("title", ""),
                        "company": row.get("company", ""),
                        "location": row.get("location", ""),
                        "description": "",
                        "skills": "",
                    }

    return {"url": url, "title": "", "description": "", "skills": ""}


def generate_with_openrouter(prompt: str, model: str = DEFAULT_MODEL) -> str:
    """Call OpenRouter API to generate text."""
    if not OPENROUTER_API_KEY:
        return "ERROR: OPENROUTER_API_KEY not set. Add it to .env"

    try:
        resp = httpx.post(
            OPENROUTER_BASE_URL,
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://bookchaowalit.com",
                "X-Title": "Book Job Pipeline",
            },
            json={
                "model": model,
                "messages": [
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.7,
                "max_tokens": 4000,
            },
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        return f"ERROR: OpenRouter API call failed: {e}"


def generate_tailored_resume(job_desc: dict, model: str = DEFAULT_MODEL) -> str:
    """Generate a tailored resume for a specific job."""
    prompt = f"""You are a professional resume writer. Generate a tailored resume for this job posting.

JOB TITLE: {job_desc.get('title', 'Software Developer')}
JOB DESCRIPTION:
{job_desc.get('description', 'No description available')[:3000]}

REQUIRED SKILLS: {job_desc.get('skills', 'Not specified')}

MY PROFILE:
{USER_PROFILE}

INSTRUCTIONS:
1. Rewrite my resume to emphasize skills and experience that match THIS specific job
2. Keep it honest - only use my actual experience, but frame it to match the job
3. Include: Contact info, Summary (2-3 lines tailored to job), Skills (prioritized by job relevance), Experience highlights, Projects
4. Use bullet points, keep it concise and professional
5. Output in Markdown format
6. Maximum 1 page equivalent (~400 words)

Generate the tailored resume now:"""

    return generate_with_openrouter(prompt, model)


def generate_cover_letter(job_desc: dict, model: str = DEFAULT_MODEL) -> str:
    """Generate a tailored cover letter for a specific job."""
    prompt = f"""You are a professional cover letter writer. Generate a tailored cover letter for this job posting.

JOB TITLE: {job_desc.get('title', 'Software Developer')}
JOB DESCRIPTION:
{job_desc.get('description', 'No description available')[:3000]}

REQUIRED SKILLS: {job_desc.get('skills', 'Not specified')}

MY PROFILE:
{USER_PROFILE}

INSTRUCTIONS:
1. Write a concise, compelling cover letter (3-4 paragraphs)
2. Opening: Express genuine interest in the specific role and company
3. Body: Highlight 2-3 key achievements/skills that directly match the job requirements
4. Close: Call to action, express enthusiasm for interview
5. Keep it professional but personable - not generic
6. Use my actual experience, framed for this job
7. Output in Markdown format
8. Maximum 350 words

Generate the cover letter now:"""

    return generate_with_openrouter(prompt, model)


def save_output(content: str, filename: str):
    """Save generated content to file."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    filepath = OUTPUT_DIR / filename
    with open(filepath, "w") as f:
        f.write(content)
    print(f"  ✓ Saved: {filepath}")
    return str(filepath)


def main():
    parser = argparse.ArgumentParser(description="AI Resume & Cover Letter Generator")
    parser.add_argument("--url", default="", help="Job URL to generate for")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="OpenRouter model to use")
    parser.add_argument("--output", default="", help="Custom output filename")
    parser.add_argument("--resume-only", action="store_true", help="Generate resume only")
    parser.add_argument("--cover-only", action="store_true", help="Generate cover letter only")
    parser.add_argument("--list", action="store_true", help="List available models")
    args = parser.parse_args()

    if args.list:
        list_models()
        return

    if not args.url:
        print("ERROR: --url is required")
        print("Usage: python3 ai_resume_generator.py --url 'https://...'")
        print("       python3 ai_resume_generator.py --list")
        return

    if not OPENROUTER_API_KEY:
        print("ERROR: OPENROUTER_API_KEY not set in .env")
        print("Get your free key at https://openrouter.ai")
        return

    print(f"\n{'='*80}")
    print(f"  AI RESUME & COVER LETTER GENERATOR")
    print(f"{'='*80}\n")

    # Get job description
    print(f"Fetching job description for: {args.url}")
    job_desc = get_job_description_from_url(args.url)

    if not job_desc.get("title") and not job_desc.get("description"):
        print(f"  ✗ No job data found for this URL")
        print(f"  Tip: Run scrape_job_descriptions.py first to collect descriptions")
        return

    print(f"  ✓ Job: {job_desc.get('title', 'Unknown')[:60]}")
    if job_desc.get("description"):
        print(f"  ✓ Description: {len(job_desc['description'])} chars")
    else:
        print(f"  ⚠ No description available - results may be generic")

    # Generate timestamp for filenames
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = args.output or f"job_{ts}"

    # Generate resume
    if not args.cover_only:
        print(f"\nGenerating tailored resume (model: {args.model})...")
        resume = generate_tailored_resume(job_desc, args.model)
        if not resume.startswith("ERROR"):
            save_output(resume, f"{base_name}_resume.md")
            print(f"\n--- RESUME PREVIEW ---")
            print(resume[:500])
            print("...")
        else:
            print(f"  ✗ {resume}")

    # Generate cover letter
    if not args.resume_only:
        print(f"\nGenerating tailored cover letter (model: {args.model})...")
        cover = generate_cover_letter(job_desc, args.model)
        if not cover.startswith("ERROR"):
            save_output(cover, f"{base_name}_cover.md")
            print(f"\n--- COVER LETTER PREVIEW ---")
            print(cover[:500])
            print("...")
        else:
            print(f"  ✗ {cover}")

    print(f"\n{'='*80}")
    print(f"  GENERATION COMPLETE")
    print(f"{'='*80}")
    print(f"\n  Files saved in: {OUTPUT_DIR}")
    print(f"  Review and customize before sending!\n")


if __name__ == "__main__":
    main()
