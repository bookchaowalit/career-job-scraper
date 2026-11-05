#!/usr/bin/env python3
"""
Multi-Resume Strategy Manager
Create and manage multiple resume variants.
Auto-select best variant per job based on job requirements.
"""

import argparse
import csv
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

try:
    from scripts.json_store import load_json_for_update
except ImportError:  # run as a script from scripts/
    from json_store import load_json_for_update

# Paths
SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR.parent / "data"
RESUMES_DIR = DATA_DIR / "resume_variants"
RESUMES_DIR.mkdir(parents=True, exist_ok=True)

# Resume variants registry
REGISTRY_FILE = RESUMES_DIR / "resume_registry.json"

# Predefined resume variants
DEFAULT_VARIANTS = {
    "fullstack": {
        "name": "Full-Stack Developer",
        "filename": "resume_fullstack.md",
        "focus": "Full-stack web development with React, Node.js, TypeScript, Python",
        "tags": ["react", "node.js", "typescript", "python", "next.js", "postgresql", "aws", "docker"],
        "summary": (
            "Senior Full-Stack Developer with 8+ years building scalable web applications. "
            "Expert in React, Next.js, TypeScript, Node.js, Python, PostgreSQL, and cloud "
            "infrastructure (AWS, Docker). Delivered production systems serving 100K+ users. "
            "Strong in both frontend UX and backend architecture."
        ),
        "highlight_projects": [
            "Job Matching Pipeline — 21-step automated scraping & AI matching system",
            "Portfolio Website — Next.js with MDX blog, project showcase",
            "Trading Bot — Python/Go grid trading system with risk management",
        ],
        "highlight_skills": [
            "React/Next.js", "TypeScript", "Node.js/Express", "Python/FastAPI",
            "PostgreSQL", "AWS", "Docker", "GraphQL", "REST APIs", "CI/CD",
        ],
    },
    "frontend": {
        "name": "Frontend Specialist",
        "filename": "resume_frontend.md",
        "focus": "Frontend development with React, Next.js, UI/UX, performance",
        "tags": ["react", "next.js", "typescript", "tailwindcss", "redux", "vite", "css", "javascript", "figma"],
        "summary": (
            "Senior Frontend Developer specializing in React/Next.js applications with "
            "exceptional UX and performance. 8+ years building responsive, accessible web "
            "interfaces. Expert in TypeScript, state management, design systems, and modern "
            "CSS. Passionate about developer experience and pixel-perfect implementation."
        ),
        "highlight_projects": [
            "Portfolio Website — Next.js with animations, responsive design, dark mode",
            "Dashboard UI — Real-time analytics with interactive charts",
            "Design System — Reusable component library with Storybook",
        ],
        "highlight_skills": [
            "React/Next.js", "TypeScript", "TailwindCSS", "Redux/Zustand",
            "Figma", "Responsive Design", "Accessibility", "Performance Optimization",
        ],
    },
    "backend": {
        "name": "Backend/Infrastructure Engineer",
        "filename": "resume_backend.md",
        "focus": "Backend systems, APIs, databases, cloud infrastructure",
        "tags": ["python", "node.js", "postgresql", "mongodb", "redis", "aws", "docker", "kubernetes", "api", "microservices"],
        "summary": (
            "Senior Backend Engineer with 8+ years designing and building scalable APIs, "
            "microservices, and cloud infrastructure. Expert in Python, Node.js, PostgreSQL, "
            "Redis, and AWS. Experience with high-traffic systems, event-driven architecture, "
            "and DevOps automation. Strong focus on reliability, performance, and security."
        ),
        "highlight_projects": [
            "Trading Bot — Real-time grid trading with multi-exchange support",
            "Job Pipeline — 21-step data pipeline with 14+ job board integrations",
            "API Gateway — Centralized authentication and rate limiting service",
        ],
        "highlight_skills": [
            "Python/FastAPI", "Node.js/Express", "PostgreSQL", "Redis", "MongoDB",
            "AWS", "Docker", "Microservices", "REST/GraphQL", "CI/CD",
        ],
    },
    "ai_ml": {
        "name": "AI/ML Engineer",
        "filename": "resume_ai_ml.md",
        "focus": "AI/ML engineering, LLM integration, data pipelines",
        "tags": ["python", "openai api", "langchain", "rag", "embeddings", "vector database", "machine learning", "data"],
        "summary": (
            "AI/ML-focused engineer with 8+ years in software development and 3+ years "
            "building AI-powered applications. Expert in LLM integration (OpenAI, Anthropic), "
            "RAG systems, vector databases, and data pipelines. Built AI matching systems, "
            "automated content generation, and intelligent data processing workflows."
        ),
        "highlight_projects": [
            "AI Job Matcher — OpenAI-powered matching with keyword analysis",
            "Cover Letter Generator — AI-tailored application content",
            "Skills Gap Analyzer — ML-driven skill demand analysis",
        ],
        "highlight_skills": [
            "Python", "OpenAI API", "LangChain", "RAG", "Vector Databases",
            "Embeddings", "Prompt Engineering", "Data Pipelines", "FastAPI", "PostgreSQL",
        ],
    },
    "remote": {
        "name": "Remote-Ready Full-Stack",
        "filename": "resume_remote.md",
        "focus": "Remote work emphasis, async communication, distributed teams",
        "tags": ["react", "node.js", "typescript", "python", "remote", "async", "distributed", "communication"],
        "summary": (
            "Senior Full-Stack Developer experienced in remote and distributed team environments. "
            "8+ years building production web applications with React, TypeScript, Node.js, and Python. "
            "Strong async communicator with proven track record delivering complex projects across "
            "time zones. Self-motivated, documentation-first approach."
        ),
        "highlight_projects": [
            "Automated Pipeline — Self-managing job discovery and matching system",
            "Portfolio Site — Self-hosted with CI/CD on Vercel",
            "Open Source Contributions — Active GitHub contributor",
        ],
        "highlight_skills": [
            "React/Next.js", "TypeScript", "Python", "Node.js",
            "Remote Collaboration", "Documentation", "CI/CD", "Docker", "Git",
        ],
    },
}


def load_registry():
    """Load resume registry."""
    # An unreadable file is kept aside instead of being overwritten on save.
    return load_json_for_update(REGISTRY_FILE, lambda: {"variants": {}, "created_at": None})


def save_registry(data):
    """Save resume registry."""
    data["updated_at"] = datetime.now().isoformat()
    with open(REGISTRY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)


def generate_resume_markdown(variant_key, variant):
    """Generate resume content in Markdown."""
    md = f"""# Chaowalit "Book" Greepoke
## {variant['name']}

📧 bookchaowalit.work@gmail.com | 🌐 bookchaowalit.com | 📍 Bangkok, Thailand (Open to Remote)

---

## Summary

{variant['summary']}

---

## Technical Skills

{', '.join(variant['highlight_skills'])}

---

## Key Projects

"""
    for proj in variant.get("highlight_projects", []):
        md += f"- **{proj}**\n"

    md += f"""
---

## Work Experience

### Senior Full-Stack Developer | Nexatech
*2020 — Present*

- Built and maintained production web applications serving 100K+ users
- Designed and implemented RESTful APIs and GraphQL endpoints
- Led frontend migration from legacy jQuery to React/Next.js
- Set up CI/CD pipelines with GitHub Actions and Docker
- Mentored junior developers and conducted code reviews

### Full-Stack Developer | Freelance
*2018 — 2020*

- Delivered 20+ client projects across web and mobile
- Built e-commerce platforms, SaaS dashboards, and API integrations
- Managed client relationships and project timelines independently

### Junior Developer | Tech Startup
*2016 — 2018*

- Developed responsive web applications with React and Node.js
- Implemented database schemas and optimized query performance
- Contributed to agile development processes

---

## Education

### Bachelor's Degree in Computer Science
*University*

---

## Languages

- **Thai** — Native
- **English** — Professional working proficiency

---

## Focus Area

{variant['focus']}

---

*Resume variant optimized for: {', '.join(variant.get('tags', [])[:8])}*
*Generated: {datetime.now().strftime('%Y-%m-%d')}*
"""
    return md


def init_variants():
    """Initialize all default resume variants."""
    registry = load_registry()
    created = 0

    for key, variant in DEFAULT_VARIANTS.items():
        if key not in registry["variants"]:
            # Generate resume content
            content = generate_resume_markdown(key, variant)
            filepath = RESUMES_DIR / variant["filename"]
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)

            registry["variants"][key] = {
                "name": variant["name"],
                "filename": variant["filename"],
                "filepath": str(filepath),
                "focus": variant["focus"],
                "tags": variant["tags"],
                "created_at": datetime.now().isoformat(),
                "version": 1,
            }
            created += 1
            print(f"  ✅ Created: {variant['name']} → {filepath.name}")

    if not registry["created_at"]:
        registry["created_at"] = datetime.now().isoformat()
    save_registry(registry)

    print(f"\n✅ Initialized {created} variants (total: {len(registry['variants'])})")
    return registry


def list_variants():
    """List all resume variants."""
    registry = load_registry()
    variants = registry.get("variants", {})

    if not variants:
        print("\n📄 No resume variants created yet.")
        print("   Run with --init to create default variants.")
        return

    print(f"\n📄 Resume Variants ({len(variants)})")
    print("=" * 70)
    for key, info in variants.items():
        filepath = Path(info.get("filepath", ""))
        exists = "✅" if filepath.exists() else "❌"
        print(f"  {exists} [{key}] {info['name']}")
        print(f"     Focus: {info.get('focus', 'N/A')[:60]}")
        print(f"     Tags: {', '.join(info.get('tags', [])[:6])}")
        print(f"     File: {info.get('filename', 'N/A')} (v{info.get('version', 1)})")
        print()
    print("=" * 70)


def select_best_variant(job, registry=None):
    """Auto-select best resume variant for a job."""
    if not registry:
        registry = load_registry()

    variants = registry.get("variants", {})
    if not variants:
        return None, None

    # Extract job keywords/skills
    job_text = " ".join(str(v) for v in job.values() if v).lower()
    job_title = job.get("title", "").lower()

    best_key = None
    best_score = -1

    for key, info in variants.items():
        tags = info.get("tags", [])
        score = 0

        for tag in tags:
            if tag.lower() in job_text:
                score += 1

        # Bonus for title match
        name = info.get("name", "").lower()
        if "frontend" in job_title and "frontend" in name:
            score += 3
        elif "backend" in job_title and "backend" in name:
            score += 3
        elif ("ai" in job_title or "ml" in job_title) and "ai" in name:
            score += 3
        elif "remote" in job.get("location", "").lower() and "remote" in key:
            score += 2

        if score > best_score:
            best_score = score
            best_key = key

    return best_key, variants.get(best_key)


def read_variant(key):
    """Read a specific resume variant."""
    registry = load_registry()
    variants = registry.get("variants", {})

    if key not in variants:
        print(f"❌ Variant '{key}' not found. Available: {', '.join(variants.keys())}")
        return

    info = variants[key]
    filepath = Path(info.get("filepath", ""))
    if not filepath.exists():
        print(f"❌ File not found: {filepath}")
        return

    content = filepath.read_text()
    print(f"\n{'=' * 70}")
    print(f"📄 {info['name']}")
    print(f"{'=' * 70}")
    print(content)


def match_job(job_id):
    """Find best variant for a specific job."""
    registry = load_registry()
    if not registry.get("variants"):
        print("❌ No variants. Run --init first.")
        return

    # Find job
    for fname in ["matched_jobs.csv", "job_postings.csv"]:
        csv_path = DATA_DIR / fname
        if not csv_path.exists():
            continue
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                jid = row.get("id", row.get("job_id", ""))
                if jid == job_id:
                    best_key, best_info = select_best_variant(row, registry)
                    if best_key:
                        print(f"\n🎯 Best variant for: {row.get('title', '')} @ {row.get('company', '')}")
                        print(f"   Recommended: {best_info['name']} [{best_key}]")
                        print(f"   File: {best_info.get('filename', 'N/A')}")
                        print(f"   Reason: Tag match score = {best_key}")
                    else:
                        print("❌ No suitable variant found")
                    return

    print(f"❌ Job {job_id} not found")


def stats():
    """Show resume variant statistics."""
    registry = load_registry()
    variants = registry.get("variants", {})

    print(f"\n📊 Resume Variant Stats")
    print(f"{'=' * 50}")
    print(f"  Total variants: {len(variants)}")
    print(f"  Registry: {REGISTRY_FILE.name}")
    print(f"  Last updated: {registry.get('updated_at', 'Never')}")

    for key, info in variants.items():
        filepath = Path(info.get("filepath", ""))
        size = filepath.stat().st_size if filepath.exists() else 0
        print(f"\n  [{key}] {info['name']}")
        print(f"    Size: {size:,} bytes")
        print(f"    Tags: {len(info.get('tags', []))}")

    print(f"{'=' * 50}")


def main():
    parser = argparse.ArgumentParser(description="Multi-Resume Strategy Manager")
    parser.add_argument("--init", action="store_true", help="Initialize default variants")
    parser.add_argument("--list", action="store_true", help="List all variants")
    parser.add_argument("--read", type=str, help="Read a specific variant")
    parser.add_argument("--select", type=str, help="Select best variant for job ID")
    parser.add_argument("--stats", action="store_true", help="Show statistics")
    parser.add_argument("--create", type=str, help="Create custom variant key")
    parser.add_argument("--name", type=str, help="Variant display name")
    parser.add_argument("--focus", type=str, help="Variant focus area")
    args = parser.parse_args()

    if args.init:
        init_variants()
        return

    if args.list:
        list_variants()
        return

    if args.read:
        read_variant(args.read)
        return

    if args.select:
        match_job(args.select)
        return

    if args.stats:
        stats()
        return

    if args.create:
        if not args.name:
            print("❌ --name is required")
            return
        registry = load_registry()
        key = args.create
        variant = {
            "name": args.name,
            "filename": f"resume_{key}.md",
            "focus": args.focus or "Custom focus",
            "tags": [],
            "created_at": datetime.now().isoformat(),
            "version": 1,
        }
        content = generate_resume_markdown(key, variant)
        filepath = RESUMES_DIR / variant["filename"]
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        variant["filepath"] = str(filepath)
        registry["variants"][key] = variant
        save_registry(registry)
        print(f"✅ Created custom variant: {args.name} [{key}]")
        return

    parser.print_help()


if __name__ == "__main__":
    main()
