#!/usr/bin/env python3
"""
Freelance Auto-Proposal — Generate and submit proposals for freelance jobs.

Reads from the freelance pipeline CSV, generates tailored proposals
using AI (OpenRouter), and saves drafts for review. Supports Upwork,
Fastwork, PeoplePerHour, and Fiverr-style proposals.

Usage:
    python3 freelance_proposal.py                    # Generate proposals for top leads
    python3 freelance_proposal.py --top 10           # Top 10 leads
    python3 freelance_proposal.py --min-value 50000  # Min value in THB
    python3 freelance_proposal.py --dry-run          # Preview only
    python3 freelance_proposal.py --send-telegram    # Notify via Telegram
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
PIPELINE_CSV = DATA_DIR / "pipeline.csv"
PROPOSALS_DIR = DATA_DIR / "freelance_proposals"
PROPOSAL_LOG = DATA_DIR / "freelance_proposal_log.json"

# ── API Keys ─────────────────────────────────────────────────────────────────
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
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
    "hourly_rate_usd": 45,
    "experience_years": 8,
    "key_skills": [
        "Python", "JavaScript", "TypeScript", "React", "Next.js", "Node.js",
        "Django", "FastAPI", "AWS", "Docker", "PostgreSQL", "MongoDB",
        "Redis", "GraphQL", "REST APIs", "CI/CD", "Terraform",
    ],
}


def load_pipeline_leads(min_value=0, source_filter=None):
    """Load leads from pipeline CSV."""
    if not PIPELINE_CSV.exists():
        print(f"[WARN] No pipeline.csv found at {PIPELINE_CSV}")
        return []

    leads = []
    with open(PIPELINE_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            status = row.get("status", "").lower()
            if status in ("applied", "proposed", "won", "rejected", "withdrawn"):
                continue
            try:
                value = float(row.get("value", 0) or 0)
            except (ValueError, TypeError):
                value = 0
            if value < min_value:
                continue
            if source_filter and source_filter.lower() not in row.get("source", "").lower():
                continue
            row["_value"] = value
            leads.append(row)

    leads.sort(key=lambda x: x["_value"], reverse=True)
    print(f"[INFO] {len(leads)} actionable leads loaded (value >= {min_value})")
    return leads


def get_already_proposed():
    """Get set of lead IDs already proposed."""
    proposed = set()
    if PROPOSAL_LOG.exists():
        try:
            log = json.loads(PROPOSAL_LOG.read_text())
            for entry in log.get("proposals", []):
                proposed.add(entry.get("lead_id", ""))
        except Exception:
            pass
    if PROPOSALS_DIR.exists():
        for f in PROPOSALS_DIR.glob("*.md"):
            proposed.add(f.stem)
    print(f"[INFO] {len(proposed)} leads already have proposals")
    return proposed


def generate_proposal_ai(lead):
    """Generate a proposal using OpenRouter AI."""
    if not OPENROUTER_API_KEY:
        return None

    title = lead.get("company", lead.get("contact", "Project"))
    notes = lead.get("notes", "")
    source = lead.get("source", "freelance")

    prompt = f"""Generate a professional freelance proposal for this project:

Project/Client: {title}
Source: {source}
Details: {notes}

My Profile:
- Name: {PROFILE['name']}
- Title: {PROFILE['title']}
- Experience: {PROFILE['experience_years']}+ years
- Key Skills: {', '.join(PROFILE['key_skills'][:10])}
- Hourly Rate: ${PROFILE['hourly_rate_usd']}/hr
- Location: {PROFILE['location']}

Write a concise, compelling proposal (200-300 words) that:
1. Shows understanding of their needs
2. Highlights relevant experience
3. Proposes a clear approach
4. Includes a rough timeline
5. Ends with a call to action

Format: Plain text, professional but friendly tone.
Start with "Hi" or "Hello" (not "Dear Sir/Madam")."""

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
                "max_tokens": 600,
                "temperature": 0.7,
            },
            timeout=30,
        )
        if resp.status_code == 200:
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()
        print(f"[WARN] OpenRouter returned {resp.status_code}")
        return None
    except Exception as e:
        print(f"[WARN] OpenRouter error: {e}")
        return None


def generate_proposal_template(lead):
    """Generate a proposal using template (fallback)."""
    title = lead.get("company", lead.get("contact", "your project"))
    notes = lead.get("notes", "")
    source = lead.get("source", "freelance")
    value = lead.get("_value", 0)

    # Estimate hours from value
    if value > 0:
        est_hours = int(value / PROFILE["hourly_rate_usd"])
        timeline = f"~{est_hours} hours"
    else:
        timeline = "to be discussed"

    proposal = f"""Hi there,

I came across your project on {source.title()} and I'm very interested in helping you bring it to life.

Based on what you've described{" — " + notes[:100] if notes else ""}, I believe my background makes me a great fit:

• {PROFILE['experience_years']}+ years of full-stack development experience
• Expertise in {', '.join(PROFILE['key_skills'][:5])}
• Proven track record delivering scalable web applications
• Available to start immediately

My approach would be:
1. Discovery call to align on requirements and priorities
2. Iterative development with regular check-ins
3. Thorough testing and documentation
4. Deployment and handoff with support

Estimated effort: {timeline}
Rate: ${PROFILE['hourly_rate_usd']}/hr

I'd love to hop on a quick call to discuss the details. Are you available this week?

Best regards,
{PROFILE['name']}
{PROFILE['title']}
{PROFILE['website']}
"""
    return proposal


def save_proposal(lead, proposal_content, is_ai=False):
    """Save proposal to file."""
    PROPOSALS_DIR.mkdir(parents=True, exist_ok=True)
    lead_id = lead.get("lead_id", lead.get("company", "unknown"))
    safe_id = re.sub(r"[^\w\-]", "_", str(lead_id))[:50]
    filename = f"{safe_id}_{datetime.now().strftime('%Y%m%d')}.md"
    filepath = PROPOSALS_DIR / filename

    header = f"""# Freelance Proposal
- **Lead**: {lead.get('company', 'Unknown')}
- **Contact**: {lead.get('contact', '—')}
- **Source**: {lead.get('source', '—')}
- **Value**: {lead.get('value', '—')} THB
- **Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M')}
- **Method**: {'AI-generated' if is_ai else 'Template'}

---

"""
    filepath.write_text(header + proposal_content)
    return filepath


def log_proposal(lead, filepath, is_ai=False):
    """Log proposal generation."""
    log = {}
    if PROPOSAL_LOG.exists():
        try:
            log = json.loads(PROPOSAL_LOG.read_text())
        except Exception:
            log = {}
    if "proposals" not in log:
        log["proposals"] = []
    log["proposals"].append({
        "lead_id": lead.get("lead_id", ""),
        "company": lead.get("company", ""),
        "source": lead.get("source", ""),
        "value": lead.get("_value", 0),
        "method": "ai" if is_ai else "template",
        "proposal_path": str(filepath),
        "generated_at": datetime.now().isoformat(),
    })
    log["last_run"] = datetime.now().isoformat()
    PROPOSAL_LOG.write_text(json.dumps(log, indent=2))


def build_telegram_message(proposals, total_leads):
    """Build Telegram summary message."""
    lines = [
        "<b>💼 Freelance Auto-Proposal Report</b>",
        f"Generated: {len(proposals)} / {total_leads} leads",
        f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
    ]
    for p in proposals[:10]:
        company = p.get("company", "Unknown")
        source = p.get("source", "—")
        value = p.get("_value", 0)
        method = "AI" if p.get("_ai") else "Template"
        lines.append(f"• <b>{company}</b> ({source}) — {value:,.0f} THB [{method}]")
    if len(proposals) > 10:
        lines.append(f"\n... and {len(proposals) - 10} more")
    msg = "\n".join(lines)
    if len(msg) > 4000:
        msg = msg[:3900] + "\n\n... (truncated)"
    return msg


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
    parser = argparse.ArgumentParser(description="Freelance Auto-Proposal Generator")
    parser.add_argument("--top", type=int, default=5, help="Max proposals to generate")
    parser.add_argument("--min-value", type=float, default=0, help="Minimum lead value (THB)")
    parser.add_argument("--source", type=str, default=None, help="Filter by source (upwork, fastwork, etc.)")
    parser.add_argument("--dry-run", action="store_true", help="Preview without saving")
    parser.add_argument("--send-telegram", action="store_true", help="Send Telegram summary")
    parser.add_argument("--force-template", action="store_true", help="Use template instead of AI")
    args = parser.parse_args()

    print("=" * 60)
    print("  Freelance Auto-Proposal Generator")
    print("=" * 60)

    # Load leads
    leads = load_pipeline_leads(min_value=args.min_value, source_filter=args.source)
    if not leads:
        print("[INFO] No actionable leads found. Exiting.")
        return

    # Filter out already proposed
    proposed = get_already_proposed()
    new_leads = [
        l for l in leads
        if l.get("lead_id", "") not in proposed
    ][:args.top]
    print(f"[INFO] {len(new_leads)} new leads to propose for")

    if not new_leads:
        print("[INFO] All leads already have proposals. Exiting.")
        return

    results = []
    for i, lead in enumerate(new_leads, 1):
        company = lead.get("company", lead.get("contact", "Unknown"))
        source = lead.get("source", "—")
        value = lead.get("_value", 0)
        print(f"\n[{i}/{len(new_leads)}] {company} ({source}) — {value:,.0f} THB")

        if args.dry_run:
            print(f"  [DRY-RUN] Would generate proposal for {company}")
            lead["_ai"] = False
            results.append(lead)
            continue

        # Try AI first, fall back to template
        proposal = None
        is_ai = False
        if not args.force_template:
            print("  Generating AI proposal...")
            proposal = generate_proposal_ai(lead)
            is_ai = proposal is not None

        if not proposal:
            print("  Using template proposal...")
            proposal = generate_proposal_template(lead)

        filepath = save_proposal(lead, proposal, is_ai)
        log_proposal(lead, filepath, is_ai)
        print(f"  [OK] Saved to {filepath.name}")

        lead["_ai"] = is_ai
        results.append(lead)

    # Telegram
    if args.send_telegram and results:
        msg = build_telegram_message(results, len(new_leads))
        send_telegram(msg)

    print(f"\n[DONE] Generated {len(results)} proposals")
    if not args.dry_run:
        print(f"  Proposals saved to {PROPOSALS_DIR}")


if __name__ == "__main__":
    main()
