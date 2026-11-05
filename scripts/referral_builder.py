#!/usr/bin/env python3
"""
Referral Network Builder — Find 2nd-degree LinkedIn connections at target companies.
Draft warm introduction messages for networking.

Usage:
    python referral_builder.py --search --company "Google"
    python referral_builder.py --search --company "Stripe" --keywords "engineering manager"
    python referral_builder.py --draft --contact "John Doe" --company "Google" --role "Senior Developer"
    python referral_builder.py --list
    python referral_builder.py --targets
"""

import argparse
import csv
import json
import os
import sys
from datetime import datetime
from pathlib import Path

try:
    import openai
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False

# Paths
SCRIPT_DIR = Path(__file__).parent
DATA_DIR = SCRIPT_DIR.parent / "data"
REFERRAL_DIR = DATA_DIR / "referral_network"
TARGETS_FILE = REFERRAL_DIR / "target_companies.json"
CONTACTS_FILE = REFERRAL_DIR / "contacts.json"
MESSAGES_FILE = REFERRAL_DIR / "outreach_messages.json"

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
MODEL = os.getenv("AI_MODEL", "openai/gpt-4o-mini")

# User profile for context
USER_PROFILE = {
    "name": "Chaowalit 'Book' Greepoke",
    "title": "Senior Full-Stack Developer",
    "skills": ["Python", "React", "Next.js", "TypeScript", "Node.js", "AI/ML", "AWS", "PostgreSQL"],
    "location": "Bangkok, Thailand",
    "email": "bookchaowalit.work@gmail.com",
    "linkedin": "https://www.linkedin.com/in/chaowalit",
    "portfolio": "https://bookchaowalit.com",
}


def ai_call(messages, temperature=0.7):
    """Call OpenRouter API."""
    if not OPENROUTER_API_KEY:
        return None
    try:
        client = openai.OpenAI(base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_API_KEY)
        response = client.chat.completions.create(
            model=MODEL, messages=messages, temperature=temperature, max_tokens=1000
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"  AI error: {e}")
        return None


def load_data():
    """Load referral network data."""
    REFERRAL_DIR.mkdir(parents=True, exist_ok=True)

    targets = {}
    if TARGETS_FILE.exists():
        targets = json.loads(TARGETS_FILE.read_text())

    contacts = {}
    if CONTACTS_FILE.exists():
        contacts = json.loads(CONTACTS_FILE.read_text())

    messages = {}
    if MESSAGES_FILE.exists():
        messages = json.loads(MESSAGES_FILE.read_text())

    return targets, contacts, messages


def save_data(targets, contacts, messages):
    """Save referral network data."""
    REFERRAL_DIR.mkdir(parents=True, exist_ok=True)
    TARGETS_FILE.write_text(json.dumps(targets, indent=2, default=str))
    CONTACTS_FILE.write_text(json.dumps(contacts, indent=2, default=str))
    MESSAGES_FILE.write_text(json.dumps(messages, indent=2, default=str))


def search_company_referrals(company, keywords=""):
    """Search for potential referral contacts at a company using free Google search."""
    targets, contacts, messages = load_data()

    print(f"Searching for referral contacts at {company}...\n")

    # Use free Google search to find LinkedIn profiles
    potential_contacts = []

    if HAS_HTTPX and HAS_BS4:
        try:
            # Search for people at the company via Google
            search_query = f'site:linkedin.com/in "{company}" (engineer OR developer OR manager OR director)'
            if keywords:
                search_query += f' "{keywords}"'

            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
            google_url = f"https://www.google.com/search?q={search_query}&num=10"
            resp = httpx.get(google_url, headers=headers, timeout=30, follow_redirects=True)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, 'html.parser')

            import re
            for a_tag in soup.find_all('a', href=True):
                url = a_tag['href']
                # Google wraps links in /url?q=...
                m = re.search(r'/url\?q=(https?://[^&]+)', url)
                if m:
                    url = m.group(1)
                if "linkedin.com/in/" not in url:
                    continue
                # Extract name from LinkedIn URL
                name = url.split("linkedin.com/in/")[-1].split("/")[0].split("?")[0]
                title = a_tag.get_text(strip=True) or f"{name} at {company}"
                potential_contacts.append({
                    "name": name.replace("-", " ").title(),
                    "title": title[:100],
                    "linkedin_url": url,
                    "description": "",
                    "company": company,
                    "found_at": datetime.now().isoformat(),
                })
                if len(potential_contacts) >= 10:
                    break
        except Exception as e:
            print(f"  Search error: {e}")

    # Fallback: generate placeholder suggestions
    if not potential_contacts:
        print("  [Using simulated contacts — Google search may be rate-limited]")
        potential_contacts = [
            {"name": f"[Contact at {company}]", "title": "Engineering Manager", "linkedin_url": "", "company": company, "found_at": datetime.now().isoformat()},
        ]

    # Save contacts
    for contact in potential_contacts:
        cid = contact["name"].lower().replace(" ", "_")
        contacts[cid] = contact

    # Update target company
    if company.lower() not in targets:
        targets[company.lower()] = {"company": company, "added_at": datetime.now().isoformat(), "contacts_found": 0}
    targets[company.lower()]["contacts_found"] = len([c for c in contacts.values() if c.get("company") == company])

    save_data(targets, contacts, messages)

    # Display results
    print(f"Found {len(potential_contacts)} potential contacts:\n")
    for c in potential_contacts:
        print(f"  👤 {c['name']}")
        print(f"     {c['title'][:60]}")
        if c.get("linkedin_url"):
            print(f"     {c['linkedin_url']}")
        print()

    return potential_contacts


def draft_message(contact_name, company, role="", relationship=""):
    """Draft a warm outreach message for a potential referral."""
    targets, contacts, messages = load_data()

    msg_type = "referral" if not relationship else "networking"

    prompt = f"""Draft a concise, warm LinkedIn connection request message (under 300 chars) for the following scenario:

Sender: {USER_PROFILE['name']}, {USER_PROFILE['title']} from {USER_PROFILE['location']}
Recipient: {contact_name} at {company}
Role applying for: {role or 'Software Engineer'}
Relationship: {relationship or 'No mutual connection — cold outreach'}

The message should:
1. Be personal and genuine (not generic)
2. Mention something specific about {company} or the role
3. Not directly ask for a referral in the first message
4. Show value (what I bring) without being boastful
5. End with a soft call to action

Return ONLY the message text."""

    if OPENROUTER_API_KEY:
        result = ai_call([
            {"role": "system", "content": "You are an expert at professional networking messages. Write naturally and concisely."},
            {"role": "user", "content": prompt}
        ], temperature=0.8)
        if result:
            message_text = result.strip()
        else:
            message_text = _fallback_message(contact_name, company, role)
    else:
        message_text = _fallback_message(contact_name, company, role)

    # Save message
    msg_id = f"{contact_name.lower().replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}"
    messages[msg_id] = {
        "contact": contact_name,
        "company": company,
        "role": role,
        "message": message_text,
        "type": msg_type,
        "created_at": datetime.now().isoformat(),
        "status": "draft",
    }
    save_data(targets, contacts, messages)

    print(f"\n📝 Draft message for {contact_name} at {company}:\n")
    print(f"  {message_text}\n")
    print(f"  Length: {len(message_text)} chars")
    print(f"  Status: draft (use --send to mark as sent)")

    return message_text


def _fallback_message(contact_name, company, role):
    """Generate a fallback message without AI."""
    return (
        f"Hi {contact_name.split()[0]}, I'm a Senior Full-Stack Developer (Python/React/TypeScript) "
        f"based in Bangkok. I've been following {company}'s work and am really impressed by "
        f"what the team is building. I'd love to connect and learn more about the engineering "
        f"culture there. I'm currently exploring {role or 'new opportunities'} and would "
        f"appreciate any insights you could share. Thanks!"
    )


def list_contacts():
    """List all contacts in the referral network."""
    _, contacts, messages = load_data()

    if not contacts:
        print("No contacts yet. Use --search --company <name> to find contacts.")
        return

    print(f"\n👥 REFERRAL NETWORK — {len(contacts)} contacts\n")
    print(f"  {'Name':<25} {'Company':<15} {'Title':<30} Status")
    print(f"  {'-'*80}")

    for cid, contact in sorted(contacts.items(), key=lambda x: x[1].get("company", "")):
        # Check if message sent
        msg_status = "draft"
        for msg in messages.values():
            if msg.get("contact", "").lower() == contact.get("name", "").lower():
                msg_status = msg.get("status", "draft")
                break
        print(f"  {contact['name']:<25} {contact.get('company', ''):<15} {contact.get('title', '')[:30]:<30} {msg_status}")


def list_targets():
    """List target companies."""
    targets, contacts, _ = load_data()

    if not targets:
        print("No target companies yet.")
        return

    print(f"\n🎯 TARGET COMPANIES — {len(targets)} companies\n")
    print(f"  {'Company':<25} {'Contacts':<10} {'Added'}")
    print(f"  {'-'*50}")

    for tid, target in sorted(targets.items(), key=lambda x: x[1].get("contacts_found", 0), reverse=True):
        print(f"  {target['company']:<25} {target.get('contacts_found', 0):<10} {target.get('added_at', '')[:10]}")


def main():
    parser = argparse.ArgumentParser(description="Referral Network Builder")
    parser.add_argument("--search", action="store_true", help="Search for contacts")
    parser.add_argument("--company", help="Target company")
    parser.add_argument("--keywords", default="", help="Additional search keywords")
    parser.add_argument("--draft", action="store_true", help="Draft outreach message")
    parser.add_argument("--contact", help="Contact name")
    parser.add_argument("--role", default="", help="Role applying for")
    parser.add_argument("--relationship", default="", help="Relationship context")
    parser.add_argument("--list", action="store_true", help="List contacts")
    parser.add_argument("--targets", action="store_true", help="List target companies")
    args = parser.parse_args()

    if args.search:
        if not args.company:
            print("Error: --company required")
            return
        search_company_referrals(args.company, args.keywords)
    elif args.draft:
        if not args.contact or not args.company:
            print("Error: --contact and --company required")
            return
        draft_message(args.contact, args.company, args.role, args.relationship)
    elif args.list:
        list_contacts()
    elif args.targets:
        list_targets()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
