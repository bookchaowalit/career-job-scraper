#!/usr/bin/env python3
"""
Application Follow-Up Email Generator
Generates personalized follow-up emails based on application status.
Supports: post-application, post-interview, thank-you notes. Thai + English.
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Paths
SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR.parent / "data"
OUTPUT_DIR = DATA_DIR / "followup_emails"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# User profile
USER = {
    "name": "Chaowalit 'Book' Greepoke",
    "first_name": "Book",
    "title": "Senior Full-Stack Developer",
    "email": "bookchaowalit.work@gmail.com",
    "portfolio": "bookchaowalit.com",
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

# Email templates
TEMPLATES = {
    "post_application": {
        "en": {
            "subject": "Following Up on {title} Application — {name}",
            "body": """Dear {hiring_manager},

I hope this email finds you well. I recently applied for the {title} position at {company} and wanted to follow up on my application.

I'm very enthusiastic about this opportunity because {reason}. My experience in {key_skills} aligns well with what your team is looking for, and I'm confident I can contribute meaningfully to {company_goal}.

I'd love the chance to discuss how my background could benefit your team. Please let me know if there's any additional information I can provide.

Thank you for your time and consideration.

Best regards,
{sender_name}
{sender_title}
{sender_email}
{sender_portfolio}"""
        },
        "th": {
            "subject": "ติดตามใบสมัครตำแหน่ง {title} — {name}",
            "body": """เรียน {hiring_manager},

ผมชื่อ {sender_name} ครับ ผมได้สมัครตำแหน่ง {title} ที่ {company} ไว้และอยากติดตามสถานะใบสมัคร

ผมสนใจตำแหน่งนี้มากเพราะ {reason} ประสบการณ์ด้าน {key_skills} ของผมตรงกับที่ทีมกำลังมองหา และผมมั่นใจว่าจะสามารถมีส่วนร่วมที่ {company} ได้อย่างมีคุณค่า

ผมยินดีมากหากมีโอกาสได้พูดคุยเพิ่มเติม หากต้องการข้อมูลเพิ่มเติมใดๆ สามารถแจ้งได้ทันทีครับ

ขอบคุณสำหรับเวลาและการพิจารณาครับ

ขอแสดงความนับถือ,
{sender_name}
{sender_title}
{sender_email}"""
        }
    },
    "post_interview": {
        "en": {
            "subject": "Thank You — {title} Interview at {company}",
            "body": """Dear {interviewer_name},

Thank you so much for taking the time to speak with me today about the {title} position at {company}. I truly enjoyed our conversation and learning more about {something_discussed}.

Our discussion reinforced my enthusiasm for this role. I'm particularly excited about {specific_interest}, and I believe my experience with {relevant_skill} would allow me to make an immediate impact.

I wanted to also mention {follow_up_point} — I think this could be especially valuable for your team's goals around {team_goal}.

Please don't hesitate to reach out if you need anything else from me. I look forward to hearing about next steps.

Best regards,
{sender_name}
{sender_email}
{sender_portfolio}"""
        },
        "th": {
            "subject": "ขอบคุณครับ — สัมภาษณ์ตำแหน่ง {title} ที่ {company}",
            "body": """เรียน {interviewer_name},

ขอบคุณมากครับที่สละเวลาพูดคุยกับผมเกี่ยวกับตำแหน่ง {title} ที่ {company} วันนี้ ผมมีความสุขมากที่ได้เรียนรู้เพิ่มเติมเกี่ยวกับ {something_discussed}

การสนทนาวันนี้ทำให้ผมยิ่งตื่นเต้นกับตำแหน่งนี้มากขึ้น โดยเฉพาะ {specific_interest} และผมเชื่อว่าประสบการณ์ด้าน {relevant_skill} จะช่วยให้ผมสร้างผลกระทบเชิงบวกได้ทันที

ผมอยากเพิ่มเติมเรื่อง {follow_up_point} ซึ่งน่าจะมีค่ามากสำหรับเป้าหมายของทีม

หากต้องการข้อมูลเพิ่มเติม สามารถติดต่อได้ทันทีครับ

ขอแสดงความนับถือ,
{sender_name}
{sender_email}"""
        }
    },
    "checking_in": {
        "en": {
            "subject": "Checking In — {title} at {company}",
            "body": """Hi {contact_name},

I hope you're doing well. I'm following up on my application for the {title} position at {company}, which I submitted on {application_date}.

I remain very interested in this opportunity and would love to know if there are any updates on the hiring timeline. Please let me know if there's anything else I can provide to support my application.

Thank you for your time!

Best regards,
{sender_name}
{sender_email}"""
        },
        "th": {
            "subject": "ติดตามสถานะ — ตำแหน่ง {title} ที่ {company}",
            "body": """สวัสดีครับ {contact_name},

ผมชื่อ {sender_name} ครับ ผมติดตามสถานะใบสมัครตำแหน่ง {title} ที่ {company} ซึ่งส่งไปเมื่อ {application_date}

ผมยังสนใจตำแหน่งนี้มากและอยากทราบว่ามีความคืบหน้าอย่างไรบ้าง หากต้องการข้อมูลเพิ่มเติม สามารถแจ้งได้ทันทีครับ

ขอบคุณครับ,
{sender_name}
{sender_email}"""
        }
    },
    "acceptance": {
        "en": {
            "subject": "Offer Acceptance — {title} at {company}",
            "body": """Dear {hiring_manager},

Thank you so much for offering me the {title} position at {company}. I'm thrilled to accept!

I'm excited to join the team and contribute to {company_goal}. As discussed, I understand the start date will be {start_date}.

Please let me know what next steps are needed for onboarding. I'm looking forward to getting started!

Best regards,
{sender_name}
{sender_email}"""
        },
        "th": {
            "subject": "ตอบรับข้อเสนอ — ตำแหน่ง {title} ที่ {company}",
            "body": """เรียน {hiring_manager},

ขอบคุณมากครับที่เสนอตำแหน่ง {title} ที่ {company} ผมยินดีตอบรับครับ!

ผมตื่นเต้นมากที่จะได้เข้าร่วมทีมและมีส่วนร่วมใน {company_goal} ตามที่พูดคุยกัน วันเริ่มงานจะเป็น {start_date}

หากมีขั้นตอนต่อไปสำหรับการเริ่มงาน แจ้งได้ทันทีครับ

ขอแสดงความนับถือ,
{sender_name}
{sender_email}"""
        }
    },
}


def generate_with_ai(email_type, context, language="en"):
    """Generate email using AI."""
    type_info = {
        "post_application": "following up after submitting a job application",
        "post_interview": "thank you email after a job interview",
        "checking_in": "checking in on application status after waiting",
        "acceptance": "accepting a job offer",
    }

    prompt = f"""Generate a {email_type.replace('_', ' ')} email.

CONTEXT:
{json.dumps(context, indent=2)}

CANDIDATE: {USER['name']}, {USER['title']}, {USER['email']}
LANGUAGE: {'Thai' if language == 'th' else 'English'}

REQUIREMENTS:
1. Professional but warm tone
2. Maximum 200 words
3. Personalized to the specific company and role
4. Include a clear call to action
5. {'Use ผม/ครับ for male speaker' if language == 'th' else ''}
6. Sign off as: {USER['first_name']} Greepoke

Output ONLY the email body text."""

    if not AI_AVAILABLE:
        return None

    try:
        response = client.chat.completions.create(
            model="openai/gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500,
            temperature=0.7,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"  ⚠️  AI error: {e}")
        return None


def generate_from_template(email_type, context, language="en"):
    """Generate email from template."""
    template = TEMPLATES.get(email_type, {}).get(language, TEMPLATES.get(email_type, {}).get("en"))
    if not template:
        return None, None

    # Fill in user info
    context.update({
        "sender_name": USER["name"],
        "sender_title": USER["title"],
        "sender_email": USER["email"],
        "sender_portfolio": USER["portfolio"],
        "name": USER["first_name"],
    })

    # Fill defaults for missing fields
    defaults = {
        "hiring_manager": "Hiring Manager",
        "interviewer_name": "Hiring Team",
        "contact_name": "Hiring Team",
        "title": "Software Engineer",
        "company": "the company",
        "reason": "the impact and technical challenges",
        "key_skills": "full-stack development, cloud infrastructure, and system design",
        "company_goal": "the team's mission",
        "something_discussed": "the team's vision and technical challenges",
        "specific_interest": "the product direction",
        "relevant_skill": "building scalable systems",
        "follow_up_point": "a relevant project I worked on",
        "team_goal": "product delivery",
        "application_date": "recently",
        "start_date": "as discussed",
    }

    for key, default in defaults.items():
        if key not in context or not context[key]:
            context[key] = default

    subject = template["subject"].format(**{k: str(v) for k, v in context.items()})
    body = template["body"].format(**{k: str(v) for k, v in context.items()})

    return subject, body


def save_email(email_type, company, subject, body, language):
    """Save email to file."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_company = "".join(c if c.isalnum() else "_" for c in company)[:20]
    filename = f"{email_type}_{safe_company}_{language}_{timestamp}.txt"
    filepath = OUTPUT_DIR / filename

    content = f"Subject: {subject}\n\n{body}"
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    return filepath


def list_emails():
    """List all generated emails."""
    files = sorted(OUTPUT_DIR.glob("*.txt"))
    if not files:
        print("\n📧 No follow-up emails generated yet.")
        return

    print(f"\n📧 Follow-Up Emails ({len(files)} files)")
    print("=" * 60)
    for f in files:
        content = f.read_text()
        subject_line = content.split("\n")[0] if content else "No subject"
        print(f"  📧 {f.name}")
        print(f"     {subject_line}")
    print("=" * 60)


def load_application_tracker():
    """Load application tracker data."""
    tracker_path = DATA_DIR / "application_tracker.json"
    if not tracker_path.exists():
        return []
    try:
        with open(tracker_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("applications", [])
    except Exception:
        return []


def main():
    parser = argparse.ArgumentParser(description="Application Follow-Up Email Generator")
    parser.add_argument("--generate", action="store_true", help="Generate an email")
    parser.add_argument("--type", type=str,
                        choices=["post_application", "post_interview", "checking_in", "acceptance"],
                        default="post_application", help="Email type")
    parser.add_argument("--company", type=str, help="Company name")
    parser.add_argument("--title", type=str, help="Job title")
    parser.add_argument("--language", type=str, default="en", choices=["en", "th"], help="Language")
    parser.add_argument("--context", type=str, help="Extra context as JSON string")
    parser.add_argument("--list", action="store_true", help="List generated emails")
    parser.add_argument("--read", type=str, help="Read a specific email")
    parser.add_argument("--templates", action="store_true", help="List available templates")
    args = parser.parse_args()

    if args.list:
        list_emails()
        return

    if args.templates:
        print(f"\n📋 Available Email Templates:")
        print("=" * 50)
        for t_type, langs in TEMPLATES.items():
            print(f"\n  📧 {t_type}")
            for lang in langs:
                print(f"     [{lang}] Subject: {langs[lang]['subject'][:60]}...")
        return

    if args.read:
        filepath = OUTPUT_DIR / args.read
        if not filepath.exists():
            matches = list(OUTPUT_DIR.glob(f"*{args.read}*"))
            if matches:
                filepath = matches[0]
            else:
                print(f"❌ Email not found: {args.read}")
                return
        print(f"\n{'=' * 60}")
        print(filepath.read_text())
        print(f"{'=' * 60}")
        return

    if args.generate:
        company = args.company or "Company"
        title = args.title or "Software Engineer"
        lang = args.language

        context = {
            "company": company,
            "title": title,
        }

        if args.context:
            try:
                extra = json.loads(args.context)
                context.update(extra)
            except json.JSONDecodeError:
                print("⚠️  Invalid JSON context, ignoring")

        print(f"\n📧 Generating {args.type} email for {company} — {title} [{lang}]")

        # Try AI first, fallback to template
        ai_body = generate_with_ai(args.type, context, lang)
        if ai_body:
            subject = f"{args.type.replace('_', ' ').title()}: {title} at {company}"
            body = ai_body
            print("  ✅ Generated with AI")
        else:
            subject, body = generate_from_template(args.type, context, lang)
            if not subject:
                print("❌ Template not found")
                return
            print("  ✅ Generated from template")

        print(f"\n{'=' * 60}")
        print(f"Subject: {subject}")
        print(f"{'=' * 60}")
        print(body)
        print(f"{'=' * 60}")

        filepath = save_email(args.type, company, subject, body, lang)
        print(f"\n💾 Saved: {filepath}")
        return

    parser.print_help()


if __name__ == "__main__":
    main()
