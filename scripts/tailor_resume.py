#!/usr/bin/env python3
"""
Auto-Tailor Resume - Generates customized resumes for job applications.
Uses AI to match your profile with job requirements.

Usage:
    python3 tailor_resume.py --url "https://example.com/job/123"
    python3 tailor_resume.py --title "Senior Python Developer"
    python3 tailor_resume.py --all-top 5
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
MATCHED_CSV = DATA_DIR / "matched_jobs.csv"
JOB_POSTINGS_CSV = DATA_DIR / "job_postings.csv"
DESCRIPTIONS_CSV = DATA_DIR / "job_descriptions.csv"
RESUMES_DIR = DATA_DIR / "tailored_resumes"

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")

# Your profile
YOUR_PROFILE = """
Name: Chaowalit "Book" Greepoke
Title: Senior Full-Stack Developer | AI Integration Specialist
Location: Bangkok, Thailand (Open to Remote)

SUMMARY:
Senior full-stack developer with 8+ years of experience building scalable web applications
and integrating AI/ML solutions. Expert in Python, React, TypeScript, and cloud infrastructure.
Proven track record delivering high-quality solutions for international clients.

CORE SKILLS:
- Languages: Python, JavaScript, TypeScript, Go, SQL
- Frontend: React, Next.js, Vue.js, Tailwind CSS, Redux
- Backend: Django, FastAPI, Node.js, Express, GraphQL, REST APIs
- Database: PostgreSQL, MySQL, MongoDB, Redis, Elasticsearch
- Cloud & DevOps: AWS, GCP, Docker, Kubernetes, Terraform, CI/CD
- AI/ML: OpenAI API, LangChain, LLM integration, RAG systems, Prompt Engineering
- Testing: Jest, Pytest, Cypress, E2E Testing
- Other: Git, Agile/Scrum, Linux, Microservices, WebSockets

EXPERIENCE HIGHLIGHTS:
- Built job scraping pipeline processing 2,000+ jobs from 20+ boards
- Developed AI-powered matching system with 7-factor scoring algorithm
- Integrated Telegram bot for real-time job notifications
- Created portfolio dashboard showcasing 40+ domain projects
- Delivered freelance projects for international clients (US, EU, APAC)

EDUCATION:
- Bachelor's Degree in Computer Science (or equivalent experience)
- Continuous learner: AI/ML, Cloud Architecture, System Design

CERTIFICATIONS:
- AWS Certified (if applicable)
- OpenAI API Certification (if applicable)

LANGUAGES:
- Thai (Native)
- English (Professional)
"""


def get_job_from_url(url: str) -> dict:
    """Get job details from URL."""
    # Try job_descriptions.csv first
    if DESCRIPTIONS_CSV.exists():
        with open(DESCRIPTIONS_CSV, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("url") == url:
                    return {
                        "title": row.get("page_title", ""),
                        "company": "",
                        "description": row.get("description", ""),
                        "skills": row.get("skills", ""),
                        "url": url,
                    }
    
    # Try matched_jobs.csv
    if MATCHED_CSV.exists():
        with open(MATCHED_CSV, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("url") == url:
                    return {
                        "title": row.get("title", ""),
                        "company": row.get("company", ""),
                        "description": "",
                        "skills": row.get("tags", ""),
                        "url": url,
                    }
    
    # Try job_postings.csv
    if JOB_POSTINGS_CSV.exists():
        with open(JOB_POSTINGS_CSV, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("url") == url:
                    return {
                        "title": row.get("title", ""),
                        "company": row.get("company", ""),
                        "description": "",
                        "skills": row.get("tags", ""),
                        "url": url,
                    }
    
    return None


def get_top_jobs(top_n: int = 5) -> list:
    """Get top N jobs from matched_jobs.csv."""
    if not MATCHED_CSV.exists():
        return []
    
    jobs = []
    with open(MATCHED_CSV, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            jobs.append({
                "title": row.get("title", ""),
                "company": row.get("company", ""),
                "description": "",
                "skills": row.get("tags", ""),
                "url": row.get("url", ""),
                "score": float(row.get("_score", 0)),
            })
    
    jobs.sort(key=lambda x: x["score"], reverse=True)
    return jobs[:top_n]


def generate_tailored_resume(job: dict) -> str:
    """Generate tailored resume using AI."""
    if not OPENROUTER_API_KEY:
        print("ERROR: OPENROUTER_API_KEY not set")
        return generate_tailored_resume_template(job)
    
    prompt = f"""You are an expert resume writer. Generate a tailored resume for this job:

JOB TITLE: {job['title']}
COMPANY: {job.get('company', 'Unknown')}
JOB DESCRIPTION: {job.get('description', 'N/A')}
REQUIRED SKILLS: {job.get('skills', 'N/A')}

MY PROFILE:
{YOUR_PROFILE}

TASK:
1. Analyze the job requirements
2. Tailor my resume to highlight matching skills and experience
3. Emphasize achievements relevant to this role
4. Use keywords from the job description
5. Keep it concise (1-2 pages)

OUTPUT FORMAT:
- Professional summary (2-3 sentences)
- Core skills (bullet points, prioritize job requirements)
- Experience highlights (3-5 bullet points, most relevant first)
- Education & Certifications
- Languages

Make it ATS-friendly and compelling."""
    
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
                "max_tokens": 2000,
                "temperature": 0.7,
            },
            timeout=30,
        )
        resp.raise_for_status()
        
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        return content
    except Exception as e:
        print(f"  Warning: AI generation failed ({e}), using template")
        return generate_tailored_resume_template(job)


def generate_tailored_resume_template(job: dict) -> str:
    """Generate tailored resume using template (fallback)."""
    job_title = job.get("title", "Developer")
    company = job.get("company", "Company")
    skills = job.get("skills", "")
    
    # Extract key skills
    skill_list = [s.strip() for s in skills.split(",") if s.strip()][:10]
    
    resume = f"""
CHAOWALIT GREepoke "BOOK"
Senior Full-Stack Developer | AI Integration Specialist
Bangkok, Thailand | Remote-Ready
Email: bookchaowalit.work@gmail.com | GitHub: github.com/bookchaowalit

═══════════════════════════════════════════════════════════════════════

PROFESSIONAL SUMMARY
────────────────────
Senior full-stack developer with 8+ years of experience, specializing in
{', '.join(skill_list[:3]) if skill_list else 'Python, React, and TypeScript'}.
Proven expertise building scalable applications and integrating AI solutions.
Delivering high-quality results for international clients across US, EU, and APAC.

═══════════════════════════════════════════════════════════════════════

CORE SKILLS
───────────
"""
    
    # Add skills based on job requirements
    if skill_list:
        resume += f"Primary: {', '.join(skill_list[:5])}\n"
    
    resume += """
Technical: Python, JavaScript, TypeScript, React, Next.js, Django, FastAPI
Database: PostgreSQL, MySQL, MongoDB, Redis, Elasticsearch
Cloud: AWS, GCP, Docker, Kubernetes, CI/CD
AI/ML: OpenAI API, LangChain, LLM Integration, RAG Systems
Testing: Jest, Pytest, Cypress, E2E Testing

═══════════════════════════════════════════════════════════════════════

EXPERIENCE HIGHLIGHTS
─────────────────────
"""
    
    # Tailor experience to job
    if "python" in job_title.lower() or "backend" in job_title.lower():
        resume += """
• Built job scraping pipeline processing 2,000+ jobs from 20+ job boards
  - Python, async/await, data parsing, CSV/JSON handling
  - Implemented 7-factor scoring algorithm for job matching

• Developed AI-powered matching system with Telegram integration
  - FastAPI backend, PostgreSQL database, real-time notifications
  - Automated application tracking and follow-up reminders
"""
    elif "react" in job_title.lower() or "frontend" in job_title.lower():
        resume += """
• Created portfolio dashboard showcasing 40+ domain projects
  - React, Next.js, TypeScript, Tailwind CSS
  - Interactive knowledge atlas with 500+ articles across 40 categories

• Built real-time job notification interface
  - React components, Telegram bot integration
  - Inline buttons for application tracking
"""
    else:
        resume += """
• Delivered 50+ freelance projects for international clients
  - Full-stack development, API integration, database design
  - Consistent 5-star ratings on Upwork and Freelancer

• Built comprehensive job scraping and matching pipeline
  - 20 job boards, 12 keywords, AI-powered matching
  - Automated notifications and application tracking
"""
    
    resume += f"""
═══════════════════════════════════════════════════════════════════════

EDUCATION & CERTIFICATIONS
──────────────────────────
• Bachelor's Degree in Computer Science (or equivalent experience)
• Continuous learner: AI/ML, Cloud Architecture, System Design
• AWS Certified (if applicable)

═══════════════════════════════════════════════════════════════════════

LANGUAGES
─────────
• Thai (Native)
• English (Professional Working Proficiency)

═══════════════════════════════════════════════════════════════════════

PROJECTS & PORTFOLIO
────────────────────
• Solo Empire Dashboard: bookchaowalit.com
• 40+ domain-specific knowledge bases
• Open source contributions on GitHub

References available upon request.
"""
    
    return resume.strip()


def save_resume(job: dict, resume_content: str) -> Path:
    """Save tailored resume to file."""
    RESUMES_DIR.mkdir(parents=True, exist_ok=True)
    
    # Generate filename
    company = job.get("company", "unknown").replace(" ", "_").replace("/", "_")[:20]
    title = job.get("title", "developer").replace(" ", "_")[:30]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    filename = f"{company}_{title}_{timestamp}.md"
    filepath = RESUMES_DIR / filename
    
    with open(filepath, "w") as f:
        f.write(f"# Tailored Resume for {job.get('title', 'Developer')}\n")
        f.write(f"**Company:** {job.get('company', 'Unknown')}\n")
        f.write(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"**Job URL:** {job.get('url', 'N/A')}\n\n")
        f.write("---\n\n")
        f.write(resume_content)
    
    return filepath


def main():
    parser = argparse.ArgumentParser(description="Auto-Tailor Resume Generator")
    parser.add_argument("--url", default="", help="Generate resume for specific job URL")
    parser.add_argument("--title", default="", help="Generate resume for job with this title")
    parser.add_argument("--all-top", type=int, default=0, help="Generate for top N jobs")
    args = parser.parse_args()
    
    print(f"\n{'='*80}")
    print(f"  AUTO-TAILOR RESUME GENERATOR")
    print(f"{'='*80}\n")
    
    RESUMES_DIR.mkdir(parents=True, exist_ok=True)
    
    jobs_to_process = []
    
    if args.url:
        job = get_job_from_url(args.url)
        if job:
            jobs_to_process.append(job)
        else:
            print(f"ERROR: Job not found for URL: {args.url}")
            return
    elif args.title:
        # Search by title
        for csv_file in [MATCHED_CSV, JOB_POSTINGS_CSV]:
            if not csv_file.exists():
                continue
            with open(csv_file, "r") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if args.title.lower() in row.get("title", "").lower():
                        jobs_to_process.append({
                            "title": row.get("title", ""),
                            "company": row.get("company", ""),
                            "description": row.get("description", ""),
                            "skills": row.get("tags", ""),
                            "url": row.get("url", ""),
                        })
                        break
            if jobs_to_process:
                break
    elif args.all_top > 0:
        jobs_to_process = get_top_jobs(args.all_top)
    else:
        # Default: top 3 jobs
        jobs_to_process = get_top_jobs(3)
    
    if not jobs_to_process:
        print("ERROR: No jobs found to process")
        return
    
    print(f"Generating tailored resumes for {len(jobs_to_process)} job(s)...\n")
    
    for i, job in enumerate(jobs_to_process, 1):
        title = job.get("title", "")[:50]
        company = job.get("company", "Unknown")
        
        print(f"{i}. {title}")
        print(f"   🏢 {company}")
        
        # Generate resume
        resume_content = generate_tailored_resume(job)
        
        # Save resume
        filepath = save_resume(job, resume_content)
        print(f"   ✓ Saved: {filepath.name}")
        print()
    
    print(f"{'='*80}")
    print(f"  SUMMARY")
    print(f"{'='*80}\n")
    print(f"  Generated {len(jobs_to_process)} tailored resume(s)")
    print(f"  Saved to: {RESUMES_DIR}/")
    print()
    print(f"💡 TIP: Review each resume before submitting")
    print(f"   Customize further based on specific job requirements\n")


if __name__ == "__main__":
    main()
