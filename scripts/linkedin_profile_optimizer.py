#!/usr/bin/env python3
"""
LinkedIn Profile Optimizer
Generate AI-optimized LinkedIn profile sections using pipeline data.
"""

import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# Paths
SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR.parent / "data"
LINKEDIN_DIR = DATA_DIR / "linkedin_profile"
LINKEDIN_DIR.mkdir(parents=True, exist_ok=True)

MATCHED_JOBS = DATA_DIR / "matched_jobs.csv"
SKILLS_REPORT = DATA_DIR / "skills_gap_report.json"

# OpenRouter
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")


def load_matched_jobs(top_n=50):
    """Load top matched jobs for skill extraction."""
    if not MATCHED_JOBS.exists():
        return []
    jobs = []
    with open(MATCHED_JOBS, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            jobs.append(row)
    jobs.sort(key=lambda x: int(x.get("score", 0)), reverse=True)
    return jobs[:top_n]


def load_skills_report():
    """Load skills gap report."""
    if not SKILLS_REPORT.exists():
        return {}
    try:
        return json.loads(SKILLS_REPORT.read_text())
    except Exception:
        return {}


def call_openrouter(prompt, max_tokens=1500):
    """Call OpenRouter API for AI generation."""
    try:
        from openai import OpenAI
        client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=OPENROUTER_API_KEY,
        )
        response = client.chat.completions.create(
            model="openai/gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=0.7,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"⚠️  OpenRouter error: {e}")
        return None


def extract_top_skills(jobs):
    """Extract most demanded skills from matched jobs."""
    skill_count = {}
    frameworks = ["react", "node.js", "typescript", "python", "next.js", "aws", "docker",
                  "postgresql", "mongodb", "redis", "graphql", "rest", "kubernetes",
                  "tailwindcss", "redux", "express", "fastapi", "golang", "rust", "java"]
    
    for job in jobs:
        text = " ".join(str(v) for v in job.values() if v).lower()
        for skill in frameworks:
            if skill in text:
                skill_count[skill] = skill_count.get(skill, 0) + 1
    
    sorted_skills = sorted(skill_count.items(), key=lambda x: x[1], reverse=True)
    return sorted_skills


def generate_about_section(skills, jobs):
    """Generate optimized LinkedIn About section."""
    top_skills = [s[0] for s in skills[:15]]
    
    prompt = f"""Write a compelling LinkedIn "About" section for Chaowalit "Book" Greepoke.

Profile:
- Senior Full-Stack Developer, 8+ years experience
- Based in Bangkok, Thailand (open to remote)
- Expert in: {', '.join(top_skills[:10])}
- Built a 21-step automated job matching pipeline with AI scoring
- Experience at Nexatech (2020-present), Freelance (2018-2020)
- Strong in React, Next.js, TypeScript, Node.js, Python, PostgreSQL, AWS, Docker
- Passionate about automation, AI-powered tools, and scalable architecture

Requirements:
- 3-4 paragraphs, professional but personable
- Highlight technical expertise and leadership
- Mention passion for building automation tools
- Include a call-to-action at the end
- Max 2000 characters
- Do NOT use emojis or bullet points
"""
    result = call_openrouter(prompt, max_tokens=800)
    if result:
        return result
    
    # Fallback
    return f"""Senior Full-Stack Developer with 8+ years building scalable web applications. Expert in {', '.join(top_skills[:8])}. 

I specialize in designing and delivering production systems that serve thousands of users. My recent work includes building a 21-step automated job matching pipeline with AI-powered scoring, integrating 14+ job boards and generating tailored application materials automatically.

Currently at Nexatech, leading full-stack development with React/Next.js, Node.js, and cloud infrastructure. Previously freelanced and delivered 20+ client projects across web and mobile.

Open to connecting with fellow engineers, tech leads, and companies building interesting products. Open to remote opportunities globally.

Skills: {', '.join(top_skills)}"""


def generate_experience_section(jobs):
    """Generate optimized Experience section."""
    prompt = """Write a LinkedIn Experience section for Chaowalit "Book" Greepoke.

Format each role with:
- Title, Company, Dates
- 4-5 bullet points with achievements (use metrics where possible)

Roles:
1. Senior Full-Stack Developer | Nexatech | 2020 - Present
   - Built production web apps serving 100K+ users
   - Led migration from jQuery to React/Next.js
   - Set up CI/CD with GitHub Actions and Docker
   - Mentored junior developers
   - Built 21-step automated job pipeline with AI matching

2. Full-Stack Developer | Freelance | 2018 - 2020
   - Delivered 20+ client projects
   - E-commerce platforms, SaaS dashboards, API integrations
   - Managed client relationships independently

3. Junior Developer | Tech Startup | 2016 - 2018
   - React and Node.js applications
   - Database optimization
   - Agile development

Make it achievement-focused with metrics. Max 1500 characters total."""
    
    result = call_openrouter(prompt, max_tokens=600)
    if result:
        return result
    
    return """Senior Full-Stack Developer | Nexatech | 2020 - Present
• Built and maintained production web applications serving 100K+ users
• Led frontend migration from legacy jQuery to React/Next.js, improving performance by 40%
• Architected RESTful APIs and GraphQL endpoints handling 10K+ daily requests
• Set up CI/CD pipelines with GitHub Actions and Docker, reducing deployment time by 60%
• Built 21-step automated job matching pipeline with AI scoring, processing 1,600+ jobs

Full-Stack Developer | Freelance | 2018 - 2020
• Delivered 20+ client projects across web and mobile platforms
• Built e-commerce platforms generating $50K+ in annual revenue
• Managed client relationships and project timelines independently

Junior Developer | Tech Startup | 2016 - 2018
• Developed responsive web applications with React and Node.js
• Optimized database queries, reducing load times by 35%"""


def generate_headline():
    """Generate optimized LinkedIn headline."""
    return 'Senior Full-Stack Developer | React, Next.js, TypeScript, Node.js, Python | Building Scalable Web Apps & AI-Powered Automation'


def generate_skills_section(skills):
    """Generate skills list."""
    top = [s[0].title() for s in skills[:20]]
    return "\n".join(f"• {s}" for s in top)


def send_telegram(message):
    """Send Telegram notification."""
    try:
        import requests
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"⚠️  Telegram error: {e}")


def optimize_profile(send_telegram_flag=False):
    """Generate full optimized LinkedIn profile."""
    print(f"\n{'='*60}")
    print(f"  LINKEDIN PROFILE OPTIMIZER")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")
    
    # Load data
    print("📊 Loading matched jobs...")
    jobs = load_matched_jobs(50)
    print(f"   Loaded {len(jobs)} jobs")
    
    print("🔍 Extracting top skills...")
    skills = extract_top_skills(jobs)
    print(f"   Found {len(skills)} skills")
    for skill, count in skills[:10]:
        print(f"     • {skill}: {count} jobs")
    
    # Generate sections
    print("\n🤖 Generating AI-optimized sections...")
    
    print("  → About section...")
    about = generate_about_section(skills, jobs)
    
    print("  → Experience section...")
    experience = generate_experience_section(jobs)
    
    print("  → Headline...")
    headline = generate_headline()
    
    print("  → Skills...")
    skills_text = generate_skills_section(skills)
    
    # Compile full profile
    profile = f"""# LinkedIn Profile — Chaowalit "Book" Greepoke
*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}*

---

## Headline
{headline}

---

## About
{about}

---

## Experience
{experience}

---

## Top Skills
{skills_text}

---

## Additional Info
- Location: Bangkok, Thailand (Open to Remote)
- Email: bookchaowalit.work@gmail.com
- Website: bookchaowalit.com
- Languages: Thai (Native), English (Professional)
"""
    
    # Save
    output_file = LINKEDIN_DIR / "linkedin_profile_optimized.md"
    output_file.write_text(profile)
    print(f"\n✅ Profile saved: {output_file}")
    
    # Save individual sections as JSON
    sections = {
        "headline": headline,
        "about": about,
        "experience": experience,
        "skills": [s[0].title() for s in skills[:20]],
        "generated_at": datetime.now().isoformat(),
    }
    json_file = LINKEDIN_DIR / "linkedin_sections.json"
    json_file.write_text(json.dumps(sections, indent=2))
    print(f"✅ Sections JSON: {json_file}")
    
    # Telegram
    if send_telegram_flag:
        msg = f"🔗 *LinkedIn Profile Optimized*\n\n"
        msg += f"Headline: {headline[:80]}...\n\n"
        msg += f"Top Skills: {', '.join(s[0] for s in skills[:8])}\n\n"
        msg += f"Profile saved with AI-generated About, Experience, and Skills sections."
        send_telegram(msg)
        print("📱 Telegram notification sent")
    
    print(f"\n{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(description="LinkedIn Profile Optimizer")
    parser.add_argument("--send-telegram", action="store_true", help="Send Telegram notification")
    args = parser.parse_args()
    
    optimize_profile(send_telegram_flag=args.send_telegram)


if __name__ == "__main__":
    main()
