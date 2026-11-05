#!/usr/bin/env python3
"""
Send job application emails with PDF resume attachment via Gmail API.

Uses MIME format to attach PDF files to emails.

Usage:
    python3 scripts/send_application_emails.py                    # Dry run (show what would be sent)
    python3 scripts/send_application_emails.py --send             # Actually send emails
    python3 scripts/send_application_emails.py --company "Figma"  # Send to specific company
    python3 scripts/send_application_emails.py --limit 5          # Send to first 5 companies
"""

import base64
import csv
import json
import os
import random
import re
import smtplib
import socket
import sys
import time
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

try:
    import dns.resolver  # optional; used only for MX verification
except ImportError:  # pragma: no cover
    dns = None  # type: ignore

# Add scripts to path for email_templates / safety imports
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from repo_paths import DATA_DIR, load_env
from safety import STATUS_SUBMITTED, assert_no_network_send_without_flag, is_live_send_unlocked
from job_target_policy import is_approved_for_submission

load_env()

from email_templates import generate_application_email, is_thai_company

# Paths
TRACKER_FILE = DATA_DIR / "apply_tracker.csv"
CONTACTS_FILE = DATA_DIR / "contact_emails.json"
RESUMES_DIR = DATA_DIR / "resumes"
SEND_LOG_FILE = DATA_DIR / "application_send_log.json"
FOLLOWUP_LOG = DATA_DIR / "followup_log.json"

# Default resume file
DEFAULT_RESUME = RESUMES_DIR / "Resume_Chaowalit_Greepoke.pdf"
# Gmail API sends as the account the refresh token belongs to; replies go to CONTACT_EMAIL.
CONTACT_EMAIL = os.getenv("CONTACT_EMAIL", "bookchaowalit.work@gmail.com")

# Valid email regex
EMAIL_RE = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')

# Email verification cache
VERIFY_CACHE_FILE = DATA_DIR / "email_verify_cache.json"


def verify_email_address(email: str, timeout: int = 5) -> dict:
    """
    Verify email address has valid MX records.
    
    Returns:
        dict with 'valid' (bool), 'reason' (str), 'mx_host' (str)
    """
    # Check cache first
    cache = {}
    if VERIFY_CACHE_FILE.exists():
        try:
            cache = json.loads(VERIFY_CACHE_FILE.read_text())
        except:
            pass
    
    if email.lower() in cache:
        cached = cache[email.lower()]
        # Cache valid for 7 days
        if time.time() - cached.get('checked_at', 0) < 7 * 86400:
            return cached
    
    result = {'valid': False, 'reason': 'unknown', 'mx_host': None, 'checked_at': time.time()}
    
    # Extract domain
    domain = email.split('@')[1] if '@' in email else None
    if not domain:
        result['reason'] = 'invalid format'
        return result

    if dns is None:
        result['reason'] = 'dnspython not installed (pip install -r requirements.txt)'
        return result
    
    # Get MX records
    try:
        mx_records = dns.resolver.resolve(domain, 'MX')
        mx_hosts = [(r.preference, str(r.exchange).rstrip('.')) for r in mx_records]
        mx_hosts.sort()  # Sort by preference (lower = higher priority)
    except dns.resolver.NXDOMAIN:
        result['reason'] = 'domain does not exist'
        return result
    except dns.resolver.NoAnswer:
        result['reason'] = 'no MX records'
        return result
    except Exception as e:
        result['reason'] = f'DNS error: {str(e)[:50]}'
        return result
    
    if not mx_hosts:
        result['reason'] = 'no MX records found'
        return result
    
    # MX records exist - domain can receive email
    result['valid'] = True
    result['reason'] = 'MX verified'
    result['mx_host'] = mx_hosts[0][1]
    
    # Save to cache
    cache[email.lower()] = result
    VERIFY_CACHE_FILE.write_text(json.dumps(cache, indent=2))
    
    return result


def verify_emails_batch(emails: list) -> dict:
    """
    Verify multiple email addresses.
    
    Returns:
        dict mapping email -> verification result
    """
    results = {}
    total = len(emails)
    
    print(f"\nVerifying {total} email addresses...")
    print("-" * 60)
    
    for i, email in enumerate(emails, 1):
        print(f"  [{i}/{total}] {email}...", end=' ', flush=True)
        result = verify_email_address(email)
        results[email] = result
        
        if result['valid']:
            print(f"✓ {result['reason']}")
        else:
            print(f"✗ {result['reason']}")
    
    # Summary
    valid = sum(1 for r in results.values() if r['valid'])
    invalid = total - valid
    print(f"\nVerification complete: {valid} valid, {invalid} invalid")
    
    return results

# Non-hiring email prefixes — generic inboxes and guessed addresses that bounce
NON_HIRING_PREFIXES = (
    'info@', 'support@', 'hello@', 'contact@', 'contact.',
    'careers@', 'marketing@', 'sales@', 'admin@',
    'biz@', 'ir@', 'media@', 'press@', 'pr@',
    'legal@', 'law@', 'compliance@',
    'customerservice@', 'customer@', 'service@',
    'security@', 'security-', 'abuse@', 'noreply@', 'no-reply@',
    'investor@', 'investors@', 'finance@', 'billing@',
    'feedback@', 'help@', 'webmaster@', 'postmaster@',
    'acquisitions@', 'partnerships@', 'partners@',
    'customerexperience@', 'customerservice@', 'customercare@',
    'humans@', 'hello@', 'hi@', 'team@',
)


def is_non_hiring_email(email: str) -> bool:
    """Check if email is a generic info/support/hello/contact inbox (not a hiring contact)."""
    lower = email.lower()
    # Check prefixes
    if any(lower.startswith(prefix) for prefix in NON_HIRING_PREFIXES):
        return True
    # URL-encoded emails (e.g. %20info@...)
    if '%' in email:
        return True
    # Obvious test/placeholder emails
    local = lower.split('@')[0] if '@' in lower else lower
    if local in ('johndoe', 'janedoe', 'test', 'example', 'sample', 'placeholder', 'dummy', 'fake', 'noreply', 'you', 'your', 'name', 'email', 'me', 'mail'):
        return True
    if lower.endswith('@domain.com') or lower.endswith('@example.com') or lower.endswith('@test.com') or lower.endswith('@company.com'):
        return True
    # AWS S3 URLs and other non-email domains
    if 'amazonaws.com' in lower or 's3.' in lower:
        return True
    return False


# Bad emails to skip
BAD_EMAILS = {
    'your@friend.com', 'xxx@xxx.xxx', 'video@720p-nov2025.mp', 'support@ziphq.com',
    'support@bamboohr.com',
    # Bounced emails
    'careers@acclaim.ai', 'careers@aircapture.com', 'careers@alignerr.com', 'careers@ambrahealth.com', 'careers@andela.com',
    'careers@atlassian.com', 'careers@avax.network', 'careers@bankjoy.com', 'careers@better.com', 'careers@bhive.engineer',
    'careers@binance.com', 'careers@bjak.my', 'careers@bluelightconsulting.com', 'careers@canonical.com', 'careers@capnexus.com',
    'careers@coalitioninc.com', 'careers@commit.dev', 'careers@consensys.io', 'careers@eneba.com', 'careers@ferrumhealth.com',
    'careers@figma.com', 'careers@followupboss.com', 'careers@greenstork.com', 'careers@hatchcard.com', 'careers@hubdoc.com',
    'careers@innovecs.com', 'careers@lateral.io', 'careers@lemon.io', 'careers@mapbox.com', 'careers@matrix.org',
    'careers@meshcloud.io', 'careers@minimaxlabs.com', 'careers@myriad.com', 'careers@narmi.com', 'careers@newsrevenuehub.com',
    'careers@ngrok.com', 'careers@noom.com', 'careers@oscaro.com', 'careers@procedureflow.com', 'careers@protocol.ai',
    'careers@reviewable.io', 'careers@rollbar.com', 'careers@sagri.tokyo', 'careers@scruff.com', 'careers@songspace.com',
    'careers@sourcegraph.com', 'careers@sparetech.io', 'careers@squadapp.io', 'careers@stripe.com', 'careers@taskade.com',
    'careers@teachforall.org', 'careers@testdome.com', 'careers@touchstorm.com', 'careers@ventusrisk.com', 'careers@vetspire.com',
    'careers@vocdoni.io', 'careers@zelos.gg', 'catchall@customer.io', 'contact@twilio.com', 'email@typeform.com',
    'hello@aggrandize.io', 'hello@skelar.tech', 'integrations-styles.js@0.2.cy4147rk.mjs', 'intetics@intetics.com', 'jubao@lingying.com',
    'nome@esempio.com', 'careers@theprodigy.co.th', 'hr@novaorganic.com', 'operations@scale.software', 'careers@bssholdings.co.th', 'careers@potentiahr.com', 'careers@livplus.co.th', 'careers@cpaxtra.co.th', 'info@trakool.com', 'careers@deeple.ai', 'careers@nimblehq.co', 'careers@truedigital.com', 'careers@lazada.com', 'hr@proalpha-solutions.com', 'careers@oxygenai.com', 'careers@turnitin.com', 'careers@lmwn.com', 'careers@cytora.com', 'recruit@ais.co.th', 'hr@sprint37.com', 'careers@horizontech.dev', 'careers@sf.co.th', 'careers@skylightdigital.co.th', 'careers@skilllane.com', 'careers@sevenpeakssoftware.com', 'careers@g-able.com', 'careers@prtr.co.th', 'careers@cp.co.th', 'hr@pulsemedia.co.th', 'talent-acquisition@circle.com', 'careers.th@shopee.com', 'atjobs@proxybase.xyz', 'careers@aha.io', 'careers@ascendmoney.com', 'careers@sermsukh.com', 'hr@pradeepitconsulting.com', 'hr@psi-cro.com', 'careers@wholix.com', 'reliably@scale.build', 'careers@unqork.com', 'careers@bankx.co.th', 'careers@truecorp.co.th', 'info@threeleafclover.com', 'careers@sansiri.com', 'careers@inteltion.com', 'careers@conicle.com', 'careers@starcube.co.th', 'careers@central.co.th', 'contact@botnoi.com', 'careers@leadtech.io', 'careers@bangkokpost.co.th', 'careers@bluebik.com', 'audiences@scale.we', 'matching@scale.we', 'careers@clearwater.com', 'jason.dupree@baseten.cowe', 'up@9am.stack', 'works@dablam.co.uk', 'us@beaconai.co', 'operations@scale.looking', 'innovation@ryder.baton', 'better@night.sectigo', 'hani.benhabiles+hn@mongodb.comyou', 'data@scale.our', 'media@aircapture.com', 'job.quinn@confluenceresearch.com.au', 'careers@sellsuki.co.th', 'ryan@ycombinator.comhttps', 'ship@multiples.what', 'work@yeet.cxyou', 'possible@scale.canopi', 'offer.work@ontemper.com', 'eng.hiring@sonarmd.com.if', 'dani@pm.me',}

# Previous / current employers & their clients — never send applications to these
# Only include specific, unambiguous company names to avoid false positives
PREVIOUS_EMPLOYERS = {
    # Own companies
    'nexatech', 'nexa', 'nexter', 'nextshield', 'turfmapp',
    # Land/Property (specific names only)
    'landmaps', 'landaps', 'landy',
    # Siam Commercial / SC (specific entity names)
    'sc assets', 'scasset', 'scgroup', 'sc assets management',
    'sc asset management',
    'siam commercial assets', 'siam commercial group', 'siam commercial',
    'siam commercial asset management', 'siam commercial family office',
    # Thai Life / TLA
    'thai life', 'thailand life', 'thailand life assurance', 'thai life assurance',
    'tla asset', 'tla asset management', 'thai life asset', 'thai life asset management',
    # Bangchak
    'bangchak', 'bangchak corporate', 'bangchak corp', 'bcpg', 'greenovist',
    # Bangkok Bank / BBL
    'bangkok bank', 'bbl asset', 'bbl asset management', 'bblfm', 'bbl fam',
    'bbl family office', 'bbl fm',
    # TMB / Thanachart
    'tmb thanachart', 'thanachart', 'thanachart bank', 'tmbt', 'tmb thanachart bank',
    # SCB
    'scb asset', 'scbx', 'scb family office', 'scb fm',
    # Kasikorn
    'kasikorn', 'kasikorn bank', 'kbank',
    # Other banks
    'krungsri', 'krungthai', 'ktb', 'ttb', 'bpi',
    # MRC
    'mrc',
    # GULF / JP Morgan
    'gulf jp morgan', 'jp morgan', 'jpmorgan',
    # Minor
    'minor international',
    # Central
    'central food', 'central retail', 'crc',
    # Home Pro
    'home pro', 'hmpo',
    # Thai Oil
    'thaioil', 'thaioil digital',
    # PTT
    'ptt', 'pttep', 'pttepg',
    # EGAT
    'egat',
    # Amata
    'amata',
    # CP
    'cp all', 'cp all retail', 'cpall',
    # Others
    'osotspa', 'bekind', 'wha', 'scg', 'dubai holding', 'mubadala', 'mitsui', 'bts',
}


def is_previous_employer(company: str) -> bool:
    """Check if company matches a previous employer (case-insensitive).
    
    Uses forward substring match (PE entry in company name) to catch subsidiaries.
    Reverse match (company in PE entry) only when company covers >= 50% of PE entry
    to prevent short names like 'GT' matching 'krungthai'.
    """
    c = company.lower().strip()
    for pe in PREVIOUS_EMPLOYERS:
        if pe in c:  # Forward: PE entry is substring of company name
            return True
        if c in pe and len(c) >= len(pe) * 0.5:  # Reverse with length check
            return True
    return False


def load_gmail_service():
    """Load Gmail API service using OAuth2 refresh token from .env."""
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
    except ImportError:
        print("ERROR: google packages not installed. Run:")
        print("  pip3 install --user google-api-python-client google-auth-httplib2 google-auth-oauthlib")
        sys.exit(1)
    
    refresh_token = os.getenv("GOOGLE_REFRESH_TOKEN", "")
    client_id = os.getenv("GOOGLE_CLIENT_ID", "")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "")
    
    if not (refresh_token and client_id and client_secret):
        print("ERROR: Gmail OAuth credentials not found in .env")
        print("Need: GOOGLE_REFRESH_TOKEN, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET")
        sys.exit(1)
    
    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri='https://oauth2.googleapis.com/token',
        client_id=client_id,
        client_secret=client_secret,
        scopes=['https://mail.google.com/']
    )
    creds.refresh(Request())
    return build('gmail', 'v1', credentials=creds)


def create_message_with_attachment(to, subject, body, pdf_path):
    """Create a MIME message with PDF attachment."""
    message = MIMEMultipart()
    message['to'] = to
    message['reply-to'] = CONTACT_EMAIL
    message['subject'] = subject
    
    # Email body
    msg_text = MIMEText(body, 'plain', 'utf-8')
    message.attach(msg_text)
    
    # PDF attachment
    if pdf_path and Path(pdf_path).exists():
        with open(pdf_path, 'rb') as f:
            pdf_data = f.read()
        
        attachment = MIMEApplication(pdf_data, _subtype='pdf')
        attachment.add_header(
            'Content-Disposition',
            'attachment',
            filename=Path(pdf_path).name
        )
        message.attach(attachment)
    else:
        print(f"  WARNING: PDF not found at {pdf_path}, sending without attachment")
    
    # Encode message
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')
    return {'raw': raw}


def find_resume_for_job(company: str, title: str) -> Path:
    """Find the best resume PDF for a job."""
    # Check for tailored resume
    company_clean = re.sub(r'[^\w\s]', '', company).replace(' ', '_')
    tailored = RESUMES_DIR / f"{company_clean}_resume.pdf"
    if tailored.exists():
        return tailored
    
    # Check for default resume
    if DEFAULT_RESUME.exists():
        return DEFAULT_RESUME
    
    # Check for any PDF in resumes dir
    pdfs = list(RESUMES_DIR.glob('*.pdf'))
    if pdfs:
        return pdfs[0]
    
    return None


def _build_domain_index(contacts: dict) -> dict:
    """Build domain → {company_names, all_emails} index from contacts.
    
    This merges contact entries that share the same domain (e.g. 'GetLinks Thailand'
    and 'GetLinks' both have domain 'getlinks.com') so we can deduplicate properly
    and send to multiple recruiters at the same company.
    """
    domain_index = {}
    for name, info in contacts.items():
        domain = (info.get('domain') or '').lower().strip()
        if not domain:
            # Extract domain from best email as fallback
            best = info.get('best') or ''
            if '@' in best:
                domain = best.split('@')[1].lower()
        if not domain:
            continue
        
        if domain not in domain_index:
            domain_index[domain] = {'company_names': set(), 'emails': set()}
        
        domain_index[domain]['company_names'].add(name)
        
        # Collect all recruiter emails (not just 'best')
        for email in info.get('emails', []):
            if EMAIL_RE.match(email) and email not in BAD_EMAILS and not is_non_hiring_email(email):
                domain_index[domain]['emails'].add(email.lower())
        
        # Also include 'best' if valid
        best = info.get('best') or ''
        if best and EMAIL_RE.match(best) and best not in BAD_EMAILS and not is_non_hiring_email(best):
            domain_index[domain]['emails'].add(best.lower())
    
    return domain_index


def _find_company_domain(company: str, domain_index: dict) -> str:
    """Find the domain for a company name using fuzzy matching."""
    company_lower = company.lower()
    
    # Direct domain match from contact name
    for domain, info in domain_index.items():
        for name in info['company_names']:
            if name.lower() == company_lower:
                return domain
    
    # Fuzzy match: contact name in company or company in contact name
    for domain, info in domain_index.items():
        for name in info['company_names']:
            if name.lower() in company_lower or company_lower in name.lower():
                return domain
    
    # Domain extraction from company name
    for domain in domain_index:
        domain_base = domain.replace('.co.th', '').replace('.com', '').replace('.th', '')
        if domain_base in company_lower or company_lower in domain_base:
            return domain
    
    return None


def get_jobs_with_emails(filters: dict = None) -> list:
    """Get list of jobs with valid contact emails.
    
    Uses domain-level deduplication to prevent sending duplicate emails to the
    same company/domain. Supports multiple recruiters per company — each unique
    recruiter email gets a separate application email.
    
    Args:
        filters: Optional dict with keys: work_type, visa_sponsor, country, job_type, experience
    """
    if not TRACKER_FILE.exists() or not CONTACTS_FILE.exists():
        return []
    
    tracker = list(csv.DictReader(open(TRACKER_FILE)))
    contacts = json.loads(CONTACTS_FILE.read_text())
    
    # Build domain index for dedup and multi-recruiter support
    domain_index = _build_domain_index(contacts)
    
    # Load send log — track sent emails at DOMAIN level
    sent_log = load_send_log()
    # Set of email addresses already sent to (domain-level dedup)
    sent_emails_global = {e.get('to', '').lower() for e in sent_log if e.get('status') in ('sent', 'bounced')}
    # Track (domain, email) pairs seen in this run
    seen_domain_emails = set()
    
    matching = []
    # Track which domains we've already processed to avoid duplicate tracker entries
    processed_domains = set()
    
    for row in tracker:
        company = row.get('company', '').strip()
        title = row.get('title', '').strip()
        
        if not company or not title or row.get('status') not in ('discovered', 'notified', 'new'):
            continue
        if not is_approved_for_submission(row):
            continue
        
        # Apply filters
        if filters:
            if filters.get('work_type') and row.get('work_type', '') != filters['work_type']:
                continue
            if filters.get('visa_sponsor') and row.get('visa_sponsor', '') != 'Yes':
                continue
            if filters.get('country') and row.get('country', '') != filters['country']:
                continue
            if filters.get('job_type') and row.get('job_type', '') != filters['job_type']:
                continue
            if filters.get('experience') and row.get('experience_level', '') != filters['experience']:
                continue
        
        # Skip previous employers
        if is_previous_employer(company):
            continue
        
        # Find domain for this company
        domain = _find_company_domain(company, domain_index)
        if not domain:
            continue
        
        # Get all recruiter emails for this domain
        all_emails = domain_index[domain]['emails']
        if not all_emails:
            continue
        
        # Canonical company name (use the first matching contact name)
        canonical_name = sorted(domain_index[domain]['company_names'], key=len)[0]
        
        # Send to each unique recruiter email at this domain
        for email in sorted(all_emails):
            domain_email_key = (domain, email)
            
            # Skip if already sent in a previous run (domain-level dedup)
            if email in sent_emails_global:
                continue
            
            # Skip if already queued in this run
            if domain_email_key in seen_domain_emails:
                continue
            
            seen_domain_emails.add(domain_email_key)
            
            # Generate email
            is_thai = is_thai_company(company)
            tmpl = generate_application_email(canonical_name, title, is_thai=is_thai)
            
            # Find resume
            resume_path = find_resume_for_job(company, title)
            
            matching.append({
                'company': canonical_name,
                'title': title,
                'url': row.get('url', ''),
                'contact_email': email,
                'email_subject': tmpl['subject'],
                'email_body': tmpl['body'],
                'email_language': tmpl['language'],
                'resume_path': str(resume_path) if resume_path else None,
            })
    
    return matching


def send_email(service, to, subject, body, pdf_path) -> dict:
    """Send an email via Gmail API."""
    try:
        message = create_message_with_attachment(to, subject, body, pdf_path)
        result = service.users().messages().send(userId='me', body=message).execute()
        return {
            'success': True,
            'message_id': result.get('id'),
            'to': to,
            'subject': subject,
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'to': to,
            'subject': subject,
        }


def load_send_log() -> list:
    """Load send log."""
    if SEND_LOG_FILE.exists():
        return json.loads(SEND_LOG_FILE.read_text())
    return []


def save_send_log(log: list):
    """Save send log."""
    with open(SEND_LOG_FILE, 'w') as f:
        json.dump(log, f, indent=2, ensure_ascii=False)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Send job application emails with PDF attachment")
    parser.add_argument("--send", action="store_true", help="Actually send emails (default is dry run)")
    parser.add_argument("--company", type=str, help="Send to specific company")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of emails to send")
    parser.add_argument("--resume", type=str, help="Path to resume PDF")
    parser.add_argument("--verify", action="store_true", help="Verify email addresses before sending")
    parser.add_argument("--verify-only", action="store_true", help="Only verify emails, don't send")
    # New filtering options
    parser.add_argument("--work-type", type=str, help="Filter by work type: WFA, WFH, Hybrid, WFO")
    parser.add_argument("--visa-sponsor", action="store_true", help="Only jobs with visa sponsorship")
    parser.add_argument("--country", type=str, help="Filter by country code: TH, US, UK, etc.")
    parser.add_argument("--job-type", type=str, help="Filter by job type: Full-time, Contract, Freelance")
    parser.add_argument("--experience", type=str, help="Filter by experience level: Junior, Mid, Senior")
    parser.add_argument("--summary", action="store_true", help="Show pipeline summary and exit")
    args = parser.parse_args()
    
    # Summary mode — show pipeline state and exit
    if args.summary:
        _print_pipeline_summary()
        sys.exit(0)

    # Block live send before any side effects (resume checks, Gmail, etc.)
    if args.send:
        print(f"Unlock active: {is_live_send_unlocked()}")
        assert_no_network_send_without_flag(want_send=True, action="application email send")
    
    # Check resume
    resume_path = Path(args.resume) if args.resume else DEFAULT_RESUME
    if not resume_path.exists():
        print(f"ERROR: Resume PDF not found at {resume_path}")
        print(f"Please place your resume PDF at: {DEFAULT_RESUME}")
        print(f"Or specify with --resume /path/to/resume.pdf")
        sys.exit(1)
    
    print(f"Using resume: {resume_path}")
    print(f"Resume size: {resume_path.stat().st_size / 1024:.1f} KB")
    
    # Build filters
    filters = {}
    if args.work_type:
        filters['work_type'] = args.work_type
    if args.visa_sponsor:
        filters['visa_sponsor'] = True
    if args.country:
        filters['country'] = args.country
    if args.job_type:
        filters['job_type'] = args.job_type
    if args.experience:
        filters['experience'] = args.experience
    
    if filters:
        print(f"Applying filters: {filters}")
    
    # Get jobs
    jobs = get_jobs_with_emails(filters=filters if filters else None)
    print(f"\nFound {len(jobs)} jobs with valid contact emails")
    
    # Filter
    if args.company:
        jobs = [j for j in jobs if args.company.lower() in j['company'].lower()]
        print(f"Filtered to {len(jobs)} jobs matching '{args.company}'")
    
    if args.limit > 0:
        jobs = jobs[:args.limit]
        print(f"Limited to {len(jobs)} jobs")
    
    if not jobs:
        print("No jobs to process")
        return
    
    # Display
    print(f"\n{'='*70}")
    print(f"  {'DRY RUN' if not args.send else 'SENDING'} EMAIL APPLICATIONS")
    print(f"  DATA_DIR: {DATA_DIR}")
    print(f"{'='*70}\n")
    
    for i, job in enumerate(jobs, 1):
        has_resume = '✓' if job['resume_path'] else '✗'
        print(f"{i:3d}. {job['company'][:25]:25s} | {job['title'][:40]:40s} | {has_resume}")
        print(f"     To: {job['contact_email']}")
        print(f"     Subject: {job['email_subject']}")
        print()
    
    # Verify emails if requested
    if args.verify or args.verify_only:
        unique_emails = list(set(j['contact_email'] for j in jobs))
        verify_results = verify_emails_batch(unique_emails)
        
        # Filter out invalid emails
        valid_jobs = []
        for job in jobs:
            email = job['contact_email']
            if verify_results.get(email, {}).get('valid', False):
                valid_jobs.append(job)
            else:
                reason = verify_results.get(email, {}).get('reason', 'unknown')
                print(f"  Skipping {job['company']}: {email} is invalid ({reason})")
        
        if args.verify_only:
            print("\n--verify-only mode: not sending emails")
            return
        
        jobs = valid_jobs
        print(f"\nFiltered to {len(jobs)} jobs with verified emails")
        
        if not jobs:
            print("No jobs with verified emails")
            return
    
    # Send (only after safety gate above)
    if args.send:
        print("\nSending emails...")
        service = load_gmail_service()
        log = load_send_log()
        
        sent = 0
        failed = 0
        
        for i, job in enumerate(jobs):
            print(f"  [{i+1}/{len(jobs)}] Sending to {job['company']}...", end=' ', flush=True)
            result = send_email(
                service,
                job['contact_email'],
                job['email_subject'],
                job['email_body'],
                job['resume_path']
            )
            
            if result['success']:
                print(f"✓ (ID: {result['message_id']})")
                log.append({
                    'company': job['company'],
                    'title': job['title'],
                    'to': job['contact_email'],
                    'subject': job['email_subject'],
                    'message_id': result['message_id'],
                    'status': STATUS_SUBMITTED,
                    'sent_at': __import__('datetime').datetime.now().isoformat(),
                })
                sent += 1
            else:
                print(f"✗ ({result['error']})")
                log.append({
                    'company': job['company'],
                    'to': job['contact_email'],
                    'subject': job['email_subject'],
                    'status': 'failed',
                    'error': result['error'],
                    'sent_at': __import__('datetime').datetime.now().isoformat(),
                })
                failed += 1
            
            # Save log after each email (so we don't lose progress)
            save_send_log(log)
            
            # Delay between sends to avoid spam filters (15-45 seconds)
            if i < len(jobs) - 1:
                delay = random.randint(15, 45)
                print(f"    Waiting {delay}s before next email...")
                time.sleep(delay)
        
        print(f"\n✓ Sent: {sent}, Failed: {failed}")
        print(f"  Log saved to: {SEND_LOG_FILE}")
    else:
        print("\n" + "="*70)
        print("  DRY RUN - No emails sent")
        print("  Live send requires --send + BOOK_JOB_LIVE_SEND_ENABLED=1")
        print("  + BOOK_JOB_SEND_UNLOCK=I_UNDERSTAND_LIVE_SEND")
        print("="*70)


def _print_pipeline_summary():
    """Print comprehensive pipeline state summary."""
    from collections import Counter
    
    # Load data
    contacts = json.loads(CONTACTS_FILE.read_text()) if CONTACTS_FILE.exists() else {}
    tracker = list(csv.DictReader(open(TRACKER_FILE))) if TRACKER_FILE.exists() else []
    sent_log = load_send_log()
    
    # Follow-up log
    followup_log = []
    if FOLLOWUP_LOG.exists():
        followup_log = json.loads(FOLLOWUP_LOG.read_text())
    
    # Contact stats
    total_contacts = len(contacts)
    with_email = sum(1 for v in contacts.values() if v.get('best'))
    multi_recruiter = sum(1 for v in contacts.values() if len(v.get('emails', [])) > 1)
    
    # Tracker stats
    status_counts = Counter(r.get('status') for r in tracker)
    country_counts = Counter(r.get('country', '') or 'N/A' for r in tracker)
    
    # Send log stats
    sent = [e for e in sent_log if e.get('status') == 'sent']
    bounced = [e for e in sent_log if e.get('status') == 'bounced']
    
    # Follow-up stats
    fu_sent = len(followup_log)
    
    # Ready to send (jobs with valid unsent emails)
    ready_jobs = get_jobs_with_emails()
    
    # Unmatched companies
    domain_index = _build_domain_index(contacts)
    unmatched = set()
    for row in tracker:
        if row.get('status') in ('discovered', 'notified', 'new'):
            company = row.get('company', '').strip()
            if not _find_company_domain(company, domain_index):
                unmatched.add(company)
    
    # Print summary
    print("="*70)
    print("  EMAIL PIPELINE SUMMARY")
    print("="*70)
    print()
    print(f"CONTACTS: {total_contacts}")
    print(f"  With valid email: {with_email}")
    print(f"  Multiple recruiters: {multi_recruiter}")
    print()
    print(f"TRACKER: {len(tracker)} jobs")
    for status, count in sorted(status_counts.items(), key=lambda x: -x[1]):
        print(f"  {status}: {count}")
    print()
    print("TOP COUNTRIES:")
    for country, count in country_counts.most_common(8):
        print(f"  {country}: {count}")
    print()
    print(f"DELIVERY:")
    print(f"  Sent: {len(sent)}")
    print(f"  Bounced: {len(bounced)}")
    print(f"  Net delivered: {len(sent) - len(bounced)}")
    print(f"  Follow-ups sent: {fu_sent}")
    print(f"  Total outreach: {len(sent) + fu_sent}")
    print()
    print(f"PENDING:")
    print(f"  Ready to send now: {len(ready_jobs)}")
    print(f"  Unmatched companies (no email): {len(unmatched)}")
    print()
    print("="*70)


if __name__ == "__main__":
    main()
