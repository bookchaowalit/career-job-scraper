#!/usr/bin/env python3
"""
Email templates for job applications (Thai + English).

Generates personalized application emails with multiple variants
to avoid spam detection from identical content.
"""

import random
from datetime import datetime


# --- English template variants ---

_ENGLISH_OPENINGS = [
    "Hi {company} team,",
    "Hello {company} hiring team,",
    "Dear {company} Engineering Team,",
    "Hi there,",
    "Hello,",
]

_ENGLISH_INTROS = [
    "I came across the {title} role and it immediately caught my attention.",
    "I'm reaching out about the {title} position at {company}.",
    "The {title} opening at {company} caught my eye — I think I'd be a great fit.",
    "I've been following {company} for a while, so when I saw the {title} role open up, I had to apply.",
    "I'm interested in the {title} position and would love to be considered.",
]

_ENGLISH_PITCHES = [
    "I'm a full-stack developer with hands-on experience building web applications, APIs, and cloud infrastructure. I've owned features end-to-end — from database design to deployment — and I'm comfortable working across the entire stack.",
    "Over the past few years, I've built and shipped full-stack applications using Python, TypeScript, and cloud services. I enjoy tackling complex problems, writing clean code, and delivering reliable software that users actually need.",
    "My background spans full-stack development, API design, and database optimization. I've worked across the entire stack — from React frontends to backend services — and I thrive in fast-moving engineering environments where I can learn and contribute quickly.",
    "I bring hands-on experience across the full development lifecycle: architecture decisions, API design, CI/CD, and production monitoring. I've shipped features used by real users and I'm always looking to level up my skills.",
]

_ENGLISH_CLOSINGS = [
    "I've attached my resume. Happy to chat anytime — just reply to this email.",
    "My resume is attached. I'd love the chance to discuss how I can contribute to your team.",
    "Resume attached. Let me know if you'd like to set up a call — I'm flexible on timing.",
    "I've attached my resume for reference. Looking forward to hearing from you.",
]

_ENGLISH_SUBJECTS = [
    "Application for {title}",
    "{title} — Application from Chaowalit Greepoke",
    "Interested in the {title} role",
    "Full-stack developer applying for {title}",
]


def generate_english_email(company: str, title: str, source: str = '') -> dict:
    """
    Generate English/international application email.
    Uses random template variants to avoid spam detection.
    """
    subject = random.choice(_ENGLISH_SUBJECTS).format(title=title, company=company)
    
    opening = random.choice(_ENGLISH_OPENINGS).format(company=company, title=title)
    intro = random.choice(_ENGLISH_INTROS).format(company=company, title=title)
    pitch = random.choice(_ENGLISH_PITCHES).format(company=company, title=title)
    closing = random.choice(_ENGLISH_CLOSINGS).format(company=company, title=title)
    
    source_line = ""
    if source:
        source_line = f" (found via {source})"
    
    body = f"""{opening}

{intro}

{pitch}

{closing}

Best,
Chaowalit Greepoke
+66 65-416-9146
bookchaowalit.work@gmail.com
linkedin.com/in/chaowalit-greepoke
bookchaowalit.com"""
    
    return {
        'subject': subject,
        'body': body,
        'language': 'en',
    }


def generate_application_email(company: str, title: str, is_thai: bool = False, source: str = '') -> dict:
    """
    Generate application email based on company location.
    
    Args:
        company: Company name
        title: Job title
        is_thai: True for Thai companies, False for international
        source: Where the job was found (e.g., "Facebook", "LinkedIn")
    
    Returns:
        dict with subject, body, language
    """
    if is_thai:
        return generate_thai_email(company, title, source)
    else:
        return generate_english_email(company, title, source)


def is_thai_company(company_name: str) -> bool:
    """
    Detect if company is Thai based on name.
    
    Uses known Thai company list + heuristic indicators.
    """
    # Known Thai companies (lowercase for matching)
    known_thai = [
        'agoda', 'line man', 'wongnai', 'shopee', 'grab', 'lazada',
        'bitkub', 'kbtg', 'kasikorn', 'scb', 'bangkok bank', 'ttb',
        'seven peaks', 'manao', 'softnix', 'tech curve', 'nimble',
        'gosoft', 'siri soft', 'diksha', 'true digital', 'ais',
        'central group', 'minor', 'sellsuki', 'priceza', 'punspace',
        'trakool', 'radarsofthouse', 'zi-argus', 'win broadband',
        'scg', 'siam cement', 'owl development',
        # FB-sourced Thai companies
        'magnum tech', 'solvis', 'tech combine', 'infos',
        'thailand vibes', 'getlinks', 'robinhunters',
        'keen profile', 'optima search', 'boss deal',
        'rcx recruitment', 'jp tech', 'codup', 'balerion',
        # FB WebSearch round 2
        'the gang', 'crossingsoft', 'investic', 'ami tech', 'jetts', 'entronica',
        'genovation', 'codemonday', 'no-tus', 'mtel', 'anyday', 'vertis',
        # FB WebSearch round 3
        'lansing', 'synnex', 'trueblue', 'cosourcing', 'constructive engineers',
        'ottimo', 'a-star', 'nova organic', 'pulsemedia', 'toyota',
        'human intelligence',
        # FB WebSearch round 4
        'svi', 'oivan', 'buzzfreeze', 'aeon', 'tdcx',
    ]
    
    name_lower = company_name.lower()
    
    # Check known Thai companies
    if any(thai in name_lower for thai in known_thai):
        return True
    
    # Heuristic indicators
    thai_indicators = [
        '(thailand)', '(ไทย)', 'ประเทศไทย',
        'co., ltd', 'บริษัท', 'จำกัด',
    ]
    return any(indicator in name_lower for indicator in thai_indicators)


# --- Thai template variants ---

_THAI_OPENINGS = [
    "เรียน ทีมงาน {company},",
    "สวัสดีครับ ทีม {company},",
    "เรียนฝ่ายบุคคล {company},",
]

_THAI_INTROS = [
    "ผมสนใจตำแหน่ง {title} ที่เห็นจาก {source}",
    "ผมเห็นประกาศตำแหน่ง {title} และคิดว่าน่าจะเหมาะกับทีม",
    "ขอสมัครตำแหน่ง {title} ที่ {company} ครับ",
]

_THAI_PITCHES = [
    "ผมเป็น full-stack developer มีประสบการณ์ทำเว็บแอปและ API มาหลายปี ทำงานได้ทั้ง frontend และ backend รวมถึง database และ deployment ครับ",
    "ผมมีประสบการณ์ทำ full-stack มา 3-4 ปี ใช้ Python, TypeScript, และ cloud services เป็นหลัก ชอบแก้ปัญหาและเขียนโค้ดที่ใช้งานได้จริง",
    "ผมทำงาน across the stack ได้เลยครับ ตั้งแต่ React frontend ยัน backend services และ database optimization พร้อมเรียนรู้สิ่งใหม่เสมอ",
]

_THAI_CLOSINGS = [
    "แนบ resume มาด้วยครับ ยินดีพูดคุยเพิ่มเติม anytime ครับ",
    "ส่ง resume มาให้ดูครับ ถ้าสนใจนัดคุยบอกได้เลยครับ",
    "แนบ resume มาให้พิจารณาครับ ขอบคุณครับ",
]

_THAI_SUBJECTS = [
    "สมัครตำแหน่ง {title}",
    "สมัครงาน {title} - เชาวลิต กรีโภค",
    "สนใจตำแหน่ง {title} ครับ",
]


def generate_thai_email(company: str, title: str, source: str = '') -> dict:
    """
    Generate Thai application email.
    Uses random template variants to avoid spam detection.
    """
    subject = random.choice(_THAI_SUBJECTS).format(title=title, company=company)
    
    opening = random.choice(_THAI_OPENINGS).format(company=company, title=title)
    intro = random.choice(_THAI_INTROS).format(company=company, title=title, source=source or "ประกาศงาน")
    pitch = random.choice(_THAI_PITCHES).format(company=company, title=title)
    closing = random.choice(_THAI_CLOSINGS).format(company=company, title=title)
    
    body = f"""{opening}

{intro}

{pitch}

{closing}

ขอบคุณครับ
เชาวลิต กรีโภค
+66 65-416-9146
bookchaowalit.work@gmail.com
bookchaowalit.com"""
    
    return {
        'subject': subject,
        'body': body,
        'language': 'th',
    }


if __name__ == "__main__":
    # Test
    print("=" * 60)
    print("THAI EMAIL TEMPLATE")
    print("=" * 60)
    thai = generate_thai_email("OWL Development and Resourcing (Thailand)", "AI Engineer", "Facebook")
    print(f"Subject: {thai['subject']}")
    print(thai['body'])
    
    print("\n" + "=" * 60)
    print("ENGLISH EMAIL TEMPLATE")
    print("=" * 60)
    eng = generate_english_email("Canonical", "Senior Python Engineer", "LinkedIn")
    print(f"Subject: {eng['subject']}")
    print(eng['body'])
    
    print("\n" + "=" * 60)
    print("COMPANY DETECTION TEST")
    print("=" * 60)
    test_companies = [
        "OWL Development and Resourcing (Thailand)",
        "Canonical",
        "บริษัท ABC จำกัด",
        "Reddit",
        "Siam Steel Co., Ltd",
    ]
    for company in test_companies:
        is_thai = is_thai_company(company)
        print(f"{company:45s} → {'THAI' if is_thai else 'INTL'}")
