#!/usr/bin/env python3
"""
ATS Auto-Apply Script - Submit applications via Chrome DevTools Protocol (CDP)

Uses headless Chrome to fill and submit Greenhouse/Lever job applications.
The invisible reCAPTCHA passes automatically in a real browser environment.

Prerequisites:
    Chrome running with --remote-debugging-port=9222

Usage:
    python3 ats_auto_apply.py                    # Dry run (show what would be applied)
    python3 ats_auto_apply.py --apply            # Actually submit applications
    python3 ats_auto_apply.py --limit 5          # Max 5 applications per run
    python3 ats_auto_apply.py --company "Figma"  # Apply to specific company
    python3 ats_auto_apply.py --ats greenhouse   # Filter by ATS type
"""

import argparse
import asyncio
import csv
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

# Find Chrome binary
CHROME_PATHS = [
    Path.home() / ".cache/puppeteer/chrome/linux-148.0.7778.97/chrome-linux64/chrome",
    Path("/opt/google/chrome/chrome"),
    Path("/usr/bin/google-chrome"),
    Path("/usr/bin/chromium-browser"),
    Path("/usr/bin/chromium"),
    Path(os.environ.get("PROGRAMFILES", "C:/Program Files")) / "Google/Chrome/Application/chrome.exe",
    Path(os.environ.get("PROGRAMFILES(X86)", "C:/Program Files (x86)")) / "Google/Chrome/Application/chrome.exe",
    Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe",
]

from repo_paths import REPO_ROOT as ROOT, DATA_DIR, load_env
from safety import STATUS_SUBMITTED, assert_no_network_send_without_flag, is_live_send_unlocked
from job_target_policy import is_approved_for_submission

load_env()

APPLY_TRACKER = DATA_DIR / "apply_tracker.csv"
ATS_APPLICATION_LOG = DATA_DIR / "ats_application_log.json"
RESUME_PDF = DATA_DIR / "Chaowalit_Greepoke_FullStack_Developer.pdf"

APPLICANT = {
    "first_name": "Chaowalit",
    "last_name": "Greepoke",
    "email": "bookchaowalit.work@gmail.com",
    "phone": "+66812345678",
    "country": "Thailand",
    "linkedin": "https://linkedin.com/in/bookchaowalit",
    "github": "https://github.com/bookchaowalit",
    "portfolio": "https://bookchaowalit.com",
}

CDP_PORT = 9222
CDP_HOST = "127.0.0.1"


def find_chrome() -> Path:
    for p in CHROME_PATHS:
        if p.exists():
            return p
    return None


def ensure_chrome_running():
    """Start Chrome with CDP if not already running."""
    import httpx
    try:
        resp = httpx.get(f"http://{CDP_HOST}:{CDP_PORT}/json/version", timeout=3)
        if resp.status_code == 200:
            print("  Chrome CDP already running")
            return True
    except Exception:
        pass

    chrome_path = find_chrome()
    if not chrome_path:
        print("  ERROR: Chrome not found!")
        return False

    print(f"  Starting Chrome: {chrome_path}")
    proc = subprocess.Popen([
        str(chrome_path),
        "--headless=new",
        "--no-sandbox",
        "--disable-gpu",
        f"--remote-debugging-port={CDP_PORT}",
        "--disable-dev-shm-usage",
        "--disable-extensions",
        "--no-first-run",
        "--disable-background-networking",
        "--disable-default-apps",
        "--disable-sync",
        "--window-size=1920,1080",
        "about:blank",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    time.sleep(3)
    try:
        resp = httpx.get(f"http://{CDP_HOST}:{CDP_PORT}/json/version", timeout=5)
        return resp.status_code == 200
    except Exception:
        return False


def kill_chrome():
    """Kill the Chrome process we started."""
    try:
        subprocess.run(["pkill", "-f", f"remote-debugging-port={CDP_PORT}"],
                       capture_output=True, timeout=5)
    except Exception:
        pass


# ─── CDP Helper ──────────────────────────────────────────────────────────────
# websockets is only required for live --apply (CDP). --test / dry-run must work
# with a minimal Python so safety gates are testable without the full venv.


def _require_httpx():
    try:
        import httpx
    except ImportError as exc:
        raise SystemExit(
            "Missing dependency 'httpx'. "
            "Install via project venv: pip install -r requirements.txt "
            "(scripts must not pip-install at runtime)"
        ) from exc
    return httpx


def _require_websockets():
    try:
        import websockets
    except ImportError as exc:
        raise SystemExit(
            "Missing dependency 'websockets'. "
            "Install via project venv: pip install -r requirements.txt "
            "(scripts must not pip-install at runtime)"
        ) from exc
    return websockets


async def _get_ws_url():
    httpx = _require_httpx()
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"http://{CDP_HOST}:{CDP_PORT}/json", timeout=10)
        targets = resp.json()
        for t in targets:
            if t.get("type") == "page":
                return t["webSocketDebuggerUrl"]
        resp = await client.get(f"http://{CDP_HOST}:{CDP_PORT}/json/new", timeout=10)
        return resp.json()["webSocketDebuggerUrl"]


class CDPSession:
    def __init__(self, ws_url: str):
        self.ws_url = ws_url
        self.ws = None
        self._msg_id = 0

    async def connect(self):
        websockets = _require_websockets()
        self.ws = await websockets.connect(self.ws_url, max_size=50 * 1024 * 1024)
        await self.send("Page.enable")
        await self.send("Runtime.enable")
        await self.send("DOM.enable")

    async def send(self, method: str, params: dict = None) -> dict:
        self._msg_id += 1
        msg_id = self._msg_id
        msg = {"id": msg_id, "method": method}
        if params:
            msg["params"] = params
        await self.ws.send(json.dumps(msg))
        while True:
            resp = json.loads(await self.ws.recv())
            if resp.get("id") == msg_id:
                if "error" in resp:
                    raise Exception(f"CDP error: {resp['error']}")
                return resp.get("result", {})

    async def navigate(self, url: str):
        await self.send("Page.navigate", {"url": url})
        # Wait for load
        deadline = time.time() + 20
        while time.time() < deadline:
            try:
                resp = json.loads(await asyncio.wait_for(self.ws.recv(), timeout=2))
                if resp.get("method") == "Page.loadEventFired":
                    break
            except asyncio.TimeoutError:
                continue
        await asyncio.sleep(3)  # Extra wait for React rendering

    async def evaluate(self, expression: str) -> any:
        result = await self.send("Runtime.evaluate", {
            "expression": expression,
            "returnByValue": True,
            "awaitPromise": True,
        })
        return result.get("result", {}).get("value")

    async def close(self):
        if self.ws:
            await self.ws.close()


async def cdp_click_option(session, index):
    """Click a visible [role='option'] element at given index using CDP mouse events."""
    bbox = await session.evaluate(f"""
        (function() {{
            const opts = Array.from(document.querySelectorAll('[role="option"]'))
                .filter(o => {{
                    const r = o.getBoundingClientRect();
                    return r.width > 0 && r.height > 0;
                }});
            if ({index} >= opts.length) return null;
            const rect = opts[{index}].getBoundingClientRect();
            return {{x: rect.x + rect.width / 2, y: rect.y + rect.height / 2}};
        }})()
    """)
    if not bbox:
        return False
    await session.send("Input.dispatchMouseEvent", {
        "type": "mousePressed", "x": bbox['x'], "y": bbox['y'], "button": "left", "clickCount": 1
    })
    await session.send("Input.dispatchMouseEvent", {
        "type": "mouseReleased", "x": bbox['x'], "y": bbox['y'], "button": "left", "clickCount": 1
    })
    return True


# ─── CSV / Tracker helpers ───────────────────────────────────────────────────

def load_csv(path: Path) -> list:
    if not path.exists():
        return []
    with open(path, "r") as f:
        return list(csv.DictReader(f))


def save_csv(path: Path, rows: list, fieldnames: list):
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def load_ats_log() -> dict:
    if ATS_APPLICATION_LOG.exists():
        with open(ATS_APPLICATION_LOG, "r") as f:
            return json.load(f)
    return {"applied": [], "failed": []}


def save_ats_log(log: dict):
    with open(ATS_APPLICATION_LOG, "w") as f:
        json.dump(log, f, indent=2)


def extract_ats_info(url: str) -> dict:
    parsed = urlparse(url)
    path_parts = [p for p in parsed.path.split("/") if p]
    if "greenhouse.io" in parsed.netloc:
        if len(path_parts) >= 3 and path_parts[1] == "jobs":
            company = path_parts[0]
            job_id = path_parts[2].split("?")[0]
            return {"ats": "greenhouse", "company": company, "job_id": job_id}
    if "lever.co" in parsed.netloc:
        if len(path_parts) >= 2:
            company = path_parts[0]
            job_id = path_parts[1].split("?")[0]
            return {"ats": "lever", "company": company, "job_id": job_id}
    return {"ats": "unknown", "company": None, "job_id": None}


def get_ats_candidates() -> list:
    rows = load_csv(APPLY_TRACKER)
    candidates = []
    for row in rows:
        if row.get("status") != "discovered":
            continue
        if not is_approved_for_submission(row):
            continue
        url = row.get("url", "")
        ats_info = extract_ats_info(url)
        if ats_info["ats"] in ["greenhouse", "lever"]:
            candidates.append({
                "url": url,
                "title": row.get("title", ""),
                "company": row.get("company", ""),
                "ats": ats_info["ats"],
                "ats_company": ats_info["company"],
                "job_id": ats_info["job_id"],
            })
    return candidates


def update_tracker_status(url: str, status: str, note: str):
    rows = load_csv(APPLY_TRACKER)
    preferred = ["url", "title", "company", "status", "note", "updated_at"]
    extras = sorted({key for row in rows for key in row} - set(preferred))
    fieldnames = preferred + extras
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for row in rows:
        if row.get("url") == url:
            row["status"] = status
            row["note"] = note
            row["updated_at"] = now
    save_csv(APPLY_TRACKER, rows, fieldnames)


# ─── Greenhouse Application ─────────────────────────────────────────────────

async def apply_greenhouse_cdp(session: CDPSession, job: dict) -> dict:
    """Fill and submit a Greenhouse job application via CDP."""
    url = job["url"]
    resume_path = str(RESUME_PDF.resolve())

    # 1. Navigate to job page
    await session.navigate(url)

    # 2. Click Apply button to open the form
    clicked = await session.evaluate("""
        (function() {
            const btn = Array.from(document.querySelectorAll('button'))
                .find(b => b.textContent.trim() === 'Apply' || b.getAttribute('aria-label') === 'Apply');
            if (btn) { btn.click(); return true; }
            return false;
        })()
    """)
    if not clicked:
        return {"success": False, "error": "Apply button not found"}
    await asyncio.sleep(4)

    # 3. Check form exists
    form_exists = await session.evaluate("!!document.querySelector('form')")
    if not form_exists:
        return {"success": False, "error": "Application form not found after clicking Apply"}

    # 4. Fill standard fields
    fill_results = {}

    # First name
    fill_results["first_name"] = await session.evaluate(f"""
        (function() {{
            const el = document.getElementById('first_name');
            if (!el) return 'not found';
            el.focus();
            const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
            setter.call(el, '{APPLICANT["first_name"]}');
            el.dispatchEvent(new Event('input', {{bubbles: true}}));
            el.dispatchEvent(new Event('change', {{bubbles: true}}));
            el.dispatchEvent(new Event('blur', {{bubbles: true}}));
            return 'ok';
        }})()
    """)

    # Last name
    fill_results["last_name"] = await session.evaluate(f"""
        (function() {{
            const el = document.getElementById('last_name');
            if (!el) return 'not found';
            el.focus();
            const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
            setter.call(el, '{APPLICANT["last_name"]}');
            el.dispatchEvent(new Event('input', {{bubbles: true}}));
            el.dispatchEvent(new Event('change', {{bubbles: true}}));
            el.dispatchEvent(new Event('blur', {{bubbles: true}}));
            return 'ok';
        }})()
    """)

    # Email
    fill_results["email"] = await session.evaluate(f"""
        (function() {{
            const el = document.getElementById('email');
            if (!el) return 'not found';
            el.focus();
            const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
            setter.call(el, '{APPLICANT["email"]}');
            el.dispatchEvent(new Event('input', {{bubbles: true}}));
            el.dispatchEvent(new Event('change', {{bubbles: true}}));
            el.dispatchEvent(new Event('blur', {{bubbles: true}}));
            return 'ok';
        }})()
    """)

    # Phone
    fill_results["phone"] = await session.evaluate(f"""
        (function() {{
            const el = document.getElementById('phone');
            if (!el) return 'not found';
            el.focus();
            const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
            setter.call(el, '{APPLICANT["phone"]}');
            el.dispatchEvent(new Event('input', {{bubbles: true}}));
            el.dispatchEvent(new Event('change', {{bubbles: true}}));
            el.dispatchEvent(new Event('blur', {{bubbles: true}}));
            return 'ok';
        }})()
    """)

    # 5. Phone country code (intl-tel-input)
    iti_search = await session.evaluate("!!document.querySelector('.iti-0__search-input')")
    if iti_search:
        # Click the flag dropdown button to open country list
        await session.evaluate("""
            (function() {
                const btn = document.querySelector('.iti-0__dropdown-button') || document.querySelector('[class*="iti"] button');
                if (btn) btn.click();
            })()
        """)
        await asyncio.sleep(0.5)
        # Type Thailand in the search
        iti_input = await session.evaluate("document.querySelector('.iti-0__search-input')")
        if iti_input:
            await session.evaluate("""
                (function() {
                    const input = document.querySelector('.iti-0__search-input');
                    if (input) { input.focus(); input.value = ''; }
                })()
            """)
            await session.send("Input.insertText", {"text": "Thailand"})
            await asyncio.sleep(1)
            # Click the Thailand option
            iti_result = await session.evaluate("""
                (function() {
                    const items = document.querySelectorAll('.iti-0__country');
                    for (const item of items) {
                        if (item.textContent.includes('Thailand')) {
                            item.click();
                            return 'selected: Thailand';
                        }
                    }
                    // Try generic selector
                    const allItems = document.querySelectorAll('[class*="country"]');
                    for (const item of allItems) {
                        if (item.textContent.includes('Thailand') && item.offsetParent !== null) {
                            item.click();
                            return 'selected (generic): Thailand';
                        }
                    }
                    return 'not found';
                })()
            """)
            fill_results["phone_country"] = iti_result
        await asyncio.sleep(0.5)

    # 5b. Country combobox (React Select)
    fill_results["country"] = await session.evaluate(f"""
        (function() {{
            // React Select uses a combobox input
            const input = document.querySelector('.select__control input[role="combobox"]');
            if (!input) return 'combobox not found';
            input.focus();
            const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
            setter.call(input, '{APPLICANT["country"]}');
            input.dispatchEvent(new Event('input', {{bubbles: true}}));
            return 'typed';
        }})()
    """)
    await asyncio.sleep(1)

    # Select the country from dropdown using CDP mouse click (React Select needs real mouse events)
    country_opts = await session.evaluate("""
        (function() {
            const opts = Array.from(document.querySelectorAll('[role="option"]'))
                .filter(o => o.offsetParent !== null);
            return opts.map(o => o.textContent.trim());
        })()
    """)
    print(f"    Country options ({len(country_opts) if country_opts else 0}): {(country_opts or [])[:5]}")
    if country_opts:
        target_idx = 0
        for i, t in enumerate(country_opts):
            if APPLICANT['country'] in t:
                target_idx = i
                break
        await cdp_click_option(session, target_idx)
        fill_results["country_select"] = f'selected: {country_opts[target_idx]}'
    else:
        fill_results["country_select"] = 'no options'
    await asyncio.sleep(0.5)

    # 6. Upload resume via CDP DOM.setFileInputFiles
    fill_results["resume"] = await session.evaluate("""
        (function() {
            const input = document.getElementById('resume');
            if (!input) return 'not found';
            return 'found';
        })()
    """)
    if fill_results["resume"] == "found":
        root = await session.send("DOM.getDocument", {"depth": -1})
        root_id = root["root"]["nodeId"]
        qresult = await session.send("DOM.querySelector", {
            "nodeId": root_id,
            "selector": '#resume',
        })
        file_node_id = qresult.get("nodeId", 0)
        if file_node_id:
            await session.send("DOM.setFileInputFiles", {
                "nodeId": file_node_id,
                "files": [resume_path],
            })
            # Trigger change events for React to detect the file
            await session.evaluate("""
                (function() {
                    const input = document.getElementById('resume');
                    if (!input) return;
                    input.dispatchEvent(new Event('change', {bubbles: true}));
                    input.dispatchEvent(new Event('input', {bubbles: true}));
                    // Also trigger blur to ensure validation runs
                    input.dispatchEvent(new Event('blur', {bubbles: true}));
                })()
            """)
            fill_results["resume"] = "uploaded"
        else:
            fill_results["resume"] = "node not found"

    print(f"    Fill results: {fill_results}")

    # 7. Fill education fields (school, degree, discipline) - React Select comboboxes
    edu_fields = [
        {"id": "school--0", "value": "Chulalongkorn", "label": "School"},
        {"id": "degree--0", "value": "Bachelor", "label": "Degree"},
        {"id": "discipline--0", "value": "Computer Science", "label": "Discipline"},
    ]
    edu_results = []
    for edu in edu_fields:
        edu_id = edu["id"]
        edu_value = edu["value"]
        edu_label = edu["label"]
        
        # Check if field exists
        exists = await session.evaluate(f"!!document.getElementById('{edu_id}')")
        if not exists:
            edu_results.append(f"{edu_label}: field not found")
            continue
        
        # Scroll into view
        await session.evaluate(f"""
            (function() {{
                const el = document.getElementById('{edu_id}');
                if (el) el.scrollIntoView({{behavior: 'instant', block: 'center'}});
            }})()
        """)
        await asyncio.sleep(0.5)
        
        # Get bounding box
        bbox = await session.evaluate(f"""
            (function() {{
                const el = document.getElementById('{edu_id}');
                if (!el) return null;
                const control = el.closest('.select__control') || el.closest('[class*="select"]') || el.parentElement;
                if (!control) return null;
                const rect = control.getBoundingClientRect();
                return {{x: rect.x, y: rect.y, width: rect.width, height: rect.height}};
            }})()
        """)
        if not bbox:
            edu_results.append(f"{edu_label}: no bbox")
            continue
        
        print(f"    Education {edu_label}: bbox={bbox}")
        
        # CDP click to open dropdown (with retry)
        cx = bbox['x'] + bbox['width'] / 2
        cy = bbox['y'] + bbox['height'] / 2
        dropdown_opened = False
        for attempt in range(3):
            await session.send("Input.dispatchMouseEvent", {
                "type": "mousePressed", "x": cx, "y": cy, "button": "left", "clickCount": 1
            })
            await session.send("Input.dispatchMouseEvent", {
                "type": "mouseReleased", "x": cx, "y": cy, "button": "left", "clickCount": 1
            })
            await asyncio.sleep(0.5)
            
            # Check if dropdown opened
            opt_count = await session.evaluate("""
                (function() {
                    const opts = Array.from(document.querySelectorAll('[role="option"]'))
                        .filter(o => o.offsetParent !== null);
                    return opts.length;
                })()
            """)
            if opt_count and opt_count > 0:
                dropdown_opened = True
                break
        
        if not dropdown_opened:
            edu_results.append(f"{edu_label}: dropdown didn't open")
            continue
        
        # Type to filter
        await session.send("Input.insertText", {"text": edu_value})
        await asyncio.sleep(1)
        
        # Select matching option using CDP mouse click (React Select needs real mouse events)
        edu_opts = await session.evaluate("""
            (function() {
                const opts = Array.from(document.querySelectorAll('[role="option"]'))
                    .filter(o => o.offsetParent !== null);
                return opts.map(o => o.textContent.trim());
            })()
        """)
        val_lower = edu_value.lower()
        target_idx = 0
        if edu_opts:
            for i, t in enumerate(edu_opts):
                if val_lower in t.lower() or t.lower() in val_lower:
                    target_idx = i
                    break
            await cdp_click_option(session, target_idx)
            option_result = f'selected: {edu_opts[target_idx]}' if edu_opts else 'no options'
        else:
            option_result = 'no options'
        edu_results.append(f"{edu_label}: {option_result}")
        await asyncio.sleep(0.5)
    
    fill_results["education"] = "; ".join(edu_results) if edu_results else "no education fields"
    print(f"    Education results: {fill_results['education']}")
    await asyncio.sleep(0.5)
    
    # 8. Fill custom questions with smart defaults (label-based, works across jobs)
    # 8a. Identify all question fields and classify them (combobox vs plain text)
    # Include all combobox fields and all question_ fields
    # First, debug what's on the page
    page_debug = await session.evaluate("""
        (function() {
            const info = [];
            info.push('question_ inputs: ' + document.querySelectorAll('input[id^="question_"]').length);
            info.push('question_ text: ' + document.querySelectorAll('input[id^="question_"][type="text"]').length);
            info.push('question_ textareas: ' + document.querySelectorAll('textarea[id^="question_"]').length);
            info.push('all comboboxes: ' + document.querySelectorAll('input[role="combobox"]').length);
            info.push('all inputs: ' + document.querySelectorAll('input').length);
            info.push('all textareas: ' + document.querySelectorAll('textarea').length);
            info.push('forms: ' + document.querySelectorAll('form').length);
            // List first 5 question_ input IDs
            const qids = [];
            document.querySelectorAll('input[id^="question_"]').forEach(el => qids.push(el.id + '[' + el.type + ']'));
            info.push('qids: ' + qids.slice(0, 10).join(', '));
            return info;
        })()
    """)
    print(f"    Page debug: {page_debug}")
    
    question_info = await session.evaluate("""
        (function() {
            const results = [];
            // Get all question_ fields
            const questionInputs = document.querySelectorAll('input[id^="question_"][type="text"], textarea[id^="question_"]');
            // Also get all combobox fields (including education, country, etc.)
            const allComboboxes = document.querySelectorAll('input[role="combobox"]');
            
            const allElements = new Set();
            questionInputs.forEach(el => allElements.add(el));
            allComboboxes.forEach(el => allElements.add(el));
            
            allElements.forEach(el => {
                const id = el.id;
                const isCombobox = el.getAttribute('role') === 'combobox' || !!el.closest('.select__control');
                
                // Find label text
                let label = '';
                const labelEl = document.querySelector('label[for="' + id + '"]');
                if (labelEl) {
                    label = labelEl.textContent.trim();
                } else {
                    label = el.getAttribute('aria-label') || '';
                    if (!label) {
                        const parent = el.closest('.question-field, .field-group, [class*="field"]');
                        if (parent) {
                            const lbl = parent.querySelector('label, .field-label, [class*="label"]');
                            if (lbl) label = lbl.textContent.trim();
                        }
                    }
                }
                
                // Determine smart value based on label keywords
                const labelLower = label.toLowerCase();
                let value = '';
                let isLongText = false;
                
                // DEBUG: Log full label for question_55258764
                if (id === 'question_55258764') {
                    console.log('DEBUG question_55258764 full label:', JSON.stringify(label));
                    console.log('DEBUG question_55258764 labelLower:', JSON.stringify(labelLower));
                    console.log('DEBUG includes in the past ten years:', labelLower.includes('in the past ten years'));
                    console.log('DEBUG includes look back:', labelLower.includes('look back'));
                    console.log('DEBUG includes countries have you worked:', labelLower.includes('countries have you worked'));
                }
                
                if (labelLower.includes('eu based') || labelLower.includes('eu-based') || labelLower.includes('based in the eu')) {
                    value = 'No';
                } else if (labelLower.includes('eligible to work') || labelLower.includes('right to work') || labelLower.includes('authorized to work') || labelLower.includes('legally authorized') || labelLower.includes('work authorization')) {
                    value = 'Yes';
                } else if (labelLower.includes('visa sponsorship') || labelLower.includes('require visa') || labelLower.includes('need visa') || labelLower.includes('visa support')) {
                    value = 'No';
                } else if (labelLower.includes('referred') || labelLower.includes('referral') || labelLower.includes('referred by')) {
                    value = 'No';
                } else if (labelLower.includes('worked at') || labelLower.includes('previous employee') || (labelLower.includes('worked for') && !labelLower.includes('how many')) || labelLower.includes('worked at')) {
                    value = 'No';
                } else if (labelLower.includes('agree') || labelLower.includes('consent') || labelLower.includes('confirm that you') || labelLower.includes('acknowledge')) {
                    value = 'Yes';
                } else if (labelLower.includes('in which country') || labelLower.includes('country do you currently') || labelLower.includes('country are you based') || labelLower.includes('current country')) {
                    value = 'Thailand';
                } else if (labelLower.includes('nationality') || labelLower.includes('citizen of') || labelLower.includes('country of citizenship')) {
                    value = 'Thai';
                } else if (labelLower.includes('gender') || labelLower.includes('sex ')) {
                    value = 'Male';
                } else if (labelLower.includes('race') || labelLower.includes('ethnicity') || labelLower.includes('ethnic')) {
                    value = 'Asian';
                } else if (labelLower.includes('how did you perform') || labelLower.includes('high school grade')) {
                    value = 'Top 10% at school';
                } else if (labelLower.includes('in the past ten years') || labelLower.includes('look back') || labelLower.includes('countries have you worked')) {
                    value = '3';
                } else if (labelLower.includes('location') || labelLower.includes('city') || labelLower.includes('where are you') || (labelLower.includes('based') && !labelLower.includes('based in'))) {
                    value = 'Bangkok, Thailand';
                } else if (labelLower.includes('salary') || labelLower.includes('compensation') || labelLower.includes('expected')) {
                    value = '$40-50/hour';
                } else if (labelLower.includes('experience presenting') || labelLower.includes('presenting data')) {
                    value = 'Yes, I have experience presenting technical information to stakeholders and team members through documentation, code reviews, and technical meetings.';
                    isLongText = true;
                } else if (labelLower.includes('python')) {
                    value = 'Yes';
                } else if (labelLower.includes('angular')) {
                    value = 'Yes';
                } else if (labelLower.includes('aws certification')) {
                    value = 'In progress';
                } else if (labelLower.includes('aws') && (labelLower.includes('experience') || labelLower.includes('services'))) {
                    value = 'I have hands-on experience with AWS services including EC2, S3, Lambda, RDS, DynamoDB, API Gateway, and CloudFormation for deploying and managing cloud-native applications.';
                    isLongText = true;
                } else if (labelLower.includes('b2b') || labelLower.includes('contract')) {
                    value = 'Yes';
                } else if (labelLower.includes('linkedin')) {
                    value = 'https://linkedin.com/in/bookchaowalit';
                } else if (labelLower.includes('github')) {
                    value = 'https://github.com/bookchaowalit';
                } else if (labelLower.includes('portfolio') || labelLower.includes('website')) {
                    value = 'https://bookchaowalit.com';
                } else if (labelLower.includes('disability') || labelLower.includes('disabled')) {
                    value = 'No, I do not have a disability';
                } else if (labelLower.includes('hispanic') || labelLower.includes('latino')) {
                    value = 'Decline To Self Identify';
                } else if (labelLower.includes('veteran') || labelLower.includes('protected veteran')) {
                    value = 'I am not a protected veteran';
                } else if (labelLower.includes('experience') && labelLower.includes('experience with')) {
                    value = 'Yes, I have relevant experience.';
                } else if (labelLower.includes('experience') || labelLower.includes('do you have')) {
                    value = 'Yes';
                } else if (labelLower.includes('authorized') || labelLower.includes('work authorization') || labelLower.includes('right to work')) {
                    value = 'Yes';
                } else if (labelLower.includes('relocate') || labelLower.includes('relocation')) {
                    value = 'Yes';
                } else if (labelLower.includes('notice') || labelLower.includes('start date') || labelLower.includes('when can')) {
                    value = '2 weeks';
                } else if (labelLower.includes('how did you hear') || labelLower.includes('source')) {
                    value = 'LinkedIn';
                } else if (labelLower.includes('meet in person') || labelLower.includes('in-person') || labelLower.includes('office')) {
                    value = 'Yes';
                } else if (labelLower.includes('require') || labelLower.includes('must')) {
                    value = 'Yes';
                } else {
                    value = 'N/A';
                }
                
                // Skip fields already handled (country, education, phone country code)
                if (id === 'country' || id.startsWith('school--') || id.startsWith('degree--') || id.startsWith('discipline--') || id.startsWith('iti-')) {
                    return;
                }
                
                results.push({
                    id: id,
                    isCombobox: isCombobox,
                    isLongText: isLongText || el.tagName === 'TEXTAREA',
                    label: label.substring(0, 60),
                    fullLabel: id === 'question_55258764' ? label : undefined,
                    value: value,
                });
            });
            return results;
        })()
    """)
    
    print(f"    Found {len(question_info) if isinstance(question_info, list) else 0} question fields")
    if isinstance(question_info, list):
        for qi in question_info:
            if qi.get('isCombobox'):
                print(f"      DBG combobox: id={qi['id']} label='{qi['label']}' value='{qi['value']}'")
                if qi.get('fullLabel'):
                    print(f"      FULL LABEL: {qi['fullLabel']}")
    
    # 7b. Fill plain text/textarea questions (non-combobox)
    plain_questions = [q for q in (question_info if isinstance(question_info, list) else []) if not q.get('isCombobox')]
    if plain_questions:
        import json as _json
        pq_data = _json.dumps(plain_questions)
        custom_results = await session.evaluate(f"""
            (function() {{
                const results = {{}};
                const questions = {pq_data};
                const setter_input = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
                const setter_textarea = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set;
                
                questions.forEach(q => {{
                    const el = document.getElementById(q.id);
                    if (!el) {{ results[q.id] = 'not found'; return; }}
                    el.focus();
                    const setter = el.tagName === 'TEXTAREA' ? setter_textarea : setter_input;
                    setter.call(el, q.value);
                    el.dispatchEvent(new Event('input', {{bubbles: true}}));
                    el.dispatchEvent(new Event('change', {{bubbles: true}}));
                    el.dispatchEvent(new Event('blur', {{bubbles: true}}));
                    results[q.id] = q.label.substring(0, 30) + ': ' + q.value.substring(0, 40);
                }});
                return results;
            }})()
        """)
        print(f"    Plain text questions filled: {len(custom_results) if isinstance(custom_results, dict) else 0}")
    else:
        custom_results = {}
    
    # 7c. Fill combobox questions (React Select - type then click option)
    combobox_questions = [q for q in (question_info if isinstance(question_info, list) else []) if q.get('isCombobox')]
    combobox_results = {}
    if combobox_questions:
        import json as _json
        print(f"    Combobox questions to fill: {len(combobox_questions)}")
        for cq in combobox_questions:
            cq_id = cq['id']
            cq_value = cq['value']
            cq_label = cq['label']
            print(f"      Combobox: {cq_label[:40]} → {cq_value}")
            
            # Step 1: Scroll the combobox into view (critical - element may be off-screen)
            scroll_result = await session.evaluate(f"""
                (function() {{
                    const el = document.getElementById('{cq_id}');
                    if (!el) return 'not found';
                    el.scrollIntoView({{behavior: 'instant', block: 'center'}});
                    return 'scrolled';
                }})()
            """)
            await asyncio.sleep(0.3)
            
            # Step 2: Get bounding box of the control for CDP mouse click
            bbox = await session.evaluate(f"""
                (function() {{
                    const el = document.getElementById('{cq_id}');
                    if (!el) return null;
                    const control = el.closest('.select__control') || el.closest('[class*="select"]') || el.parentElement;
                    if (!control) return null;
                    const rect = control.getBoundingClientRect();
                    return {{x: rect.x, y: rect.y, width: rect.width, height: rect.height}};
                }})()
            """)
            if not bbox:
                combobox_results[cq_id] = f"{cq_label[:30]}: no bounding box"
                continue
            
            # Step 3: Real CDP mouse click to open the dropdown (with retry)
            cx = bbox['x'] + bbox['width'] / 2
            cy = bbox['y'] + bbox['height'] / 2
            
            dropdown_opened = False
            for attempt in range(3):
                await session.send("Input.dispatchMouseEvent", {
                    "type": "mousePressed", "x": cx, "y": cy, "button": "left", "clickCount": 1
                })
                await session.send("Input.dispatchMouseEvent", {
                    "type": "mouseReleased", "x": cx, "y": cy, "button": "left", "clickCount": 1
                })
                await asyncio.sleep(0.5)
                
                # Check if dropdown opened (check both visible options AND aria-expanded)
                opt_check = await session.evaluate(f"""
                    (function() {{
                        // Check aria-expanded on the input
                        const el = document.getElementById('{cq_id}');
                        if (el && el.getAttribute('aria-expanded') === 'true') return -1; // special: expanded but options may be in portal
                        // Check visible options
                        const opts = Array.from(document.querySelectorAll('[role="option"]'))
                            .filter(o => o.offsetParent !== null);
                        return opts.length;
                    }})()
                """)
                if opt_check and (opt_check > 0 or opt_check == -1):
                    dropdown_opened = True
                    break
            
            if not dropdown_opened:
                # Debug: inspect DOM structure of this combobox
                dom_debug = await session.evaluate(f"""
                    (function() {{
                        const el = document.getElementById('{cq_id}');
                        if (!el) return 'not found';
                        const parent = el.parentElement;
                        const grandparent = parent ? parent.parentElement : null;
                        const control = el.closest('.select__control') || el.closest('[class*="select"]');
                        // Check for datalist
                        const listAttr = el.getAttribute('list');
                        // Check for any aria-controls
                        const ariaControls = el.getAttribute('aria-controls');
                        // Check all sibling/parent elements for listbox
                        const container = el.closest('.field-container') || el.closest('[class*="field"]') || el.closest('[class*="question"]');
                        const listbox = container ? container.querySelector('[role="listbox"]') : null;
                        const options = container ? container.querySelectorAll('[role="option"]') : [];
                        return {{
                            tagName: el.tagName,
                            type: el.type,
                            role: el.getAttribute('role'),
                            ariaAutocomplete: el.getAttribute('aria-autocomplete'),
                            ariaExpanded: el.getAttribute('aria-expanded'),
                            ariaControls: ariaControls,
                            listAttr: listAttr,
                            parentClass: parent ? parent.className : '',
                            grandparentClass: grandparent ? grandparent.className : '',
                            hasSelectControl: !!control,
                            controlClass: control ? control.className : '',
                            hasListbox: !!listbox,
                            optionCount: options.length,
                            containerClass: container ? container.className : '',
                            // Check if there's a menu/listbox elsewhere on page
                            allListboxes: document.querySelectorAll('[role="listbox"]').length,
                            allOptions: document.querySelectorAll('[role="option"]').length,
                            inputId: el.id,
                            inputName: el.name
                        }};
                    }})()
                """)
                print(f"        DOM debug for {cq_id}: {dom_debug}")
                
                # Fallback: try keyboard navigation (ArrowDown + Enter)
                print(f"        → dropdown didn't open, trying keyboard nav")
                await session.evaluate(f"""
                    (function() {{
                        const el = document.getElementById('{cq_id}');
                        if (el) el.focus();
                    }})()
                """)
                await asyncio.sleep(0.3)
                # Press ArrowDown to open dropdown
                await session.send("Input.dispatchKeyEvent", {
                    "type": "keyDown", "key": "ArrowDown", "code": "ArrowDown", "windowsVirtualKeyCode": 40
                })
                await session.send("Input.dispatchKeyEvent", {
                    "type": "keyUp", "key": "ArrowDown", "code": "ArrowDown", "windowsVirtualKeyCode": 40
                })
                await asyncio.sleep(0.5)
                
                opt_check2 = await session.evaluate(f"""
                    (function() {{
                        const el = document.getElementById('{cq_id}');
                        if (el && el.getAttribute('aria-expanded') === 'true') return -1;
                        const opts = Array.from(document.querySelectorAll('[role="option"]'))
                            .filter(o => {{
                                const r = o.getBoundingClientRect();
                                return r.width > 0 && r.height > 0;
                            }});
                        return opts.length;
                    }})()
                """)
                if not opt_check2 or opt_check2 == 0:
                    combobox_results[cq_id] = f"{cq_label[:30]}: dropdown never opened"
                    print(f"        → dropdown never opened after keyboard fallback")
                    continue
                dropdown_opened = True
            
            # Step 4: Check available options BEFORE typing (check both regular and portal-rendered options)
            pre_type_options = await session.evaluate(f"""
                (function() {{
                    // First try: find options via aria-controls listbox
                    const el = document.getElementById('{cq_id}');
                    const controlsId = el ? el.getAttribute('aria-controls') : null;
                    let opts;
                    if (controlsId) {{
                        const listbox = document.getElementById(controlsId);
                        if (listbox) {{
                            opts = Array.from(listbox.querySelectorAll('[role="option"]'));
                        }}
                    }}
                    if (!opts || opts.length === 0) {{
                        // Fallback: all options with non-zero size
                        opts = Array.from(document.querySelectorAll('[role="option"]'))
                            .filter(o => {{
                                const r = o.getBoundingClientRect();
                                return r.width > 0 && r.height > 0;
                            }});
                    }}
                    return opts.map(o => o.textContent.trim());
                }})()
            """)
            print(f"        Pre-type options ({len(pre_type_options) if pre_type_options else 0}): {(pre_type_options or [])[:10]}")
            
            # Step 5: Select matching option using CDP mouse click (React Select needs real mouse events)
            val_lower = cq_value.lower()
            target_idx = None
            
            # For large option lists (>20), type to filter first
            if pre_type_options and len(pre_type_options) > 20 and val_lower and len(val_lower) >= 2:
                print(f"        Large list ({len(pre_type_options)} options), typing to filter: '{cq_value}'")
                await session.send("Input.insertText", {"text": cq_value})
                await asyncio.sleep(1)
                # Get filtered options (check portal-rendered too)
                filtered_options = await session.evaluate(f"""
                    (function() {{
                        const el = document.getElementById('{cq_id}');
                        const controlsId = el ? el.getAttribute('aria-controls') : null;
                        let opts;
                        if (controlsId) {{
                            const listbox = document.getElementById(controlsId);
                            if (listbox) {{
                                opts = Array.from(listbox.querySelectorAll('[role="option"]'));
                            }}
                        }}
                        if (!opts || opts.length === 0) {{
                            opts = Array.from(document.querySelectorAll('[role="option"]'))
                                .filter(o => {{
                                    const r = o.getBoundingClientRect();
                                    return r.width > 0 && r.height > 0;
                                }});
                        }}
                        return opts.map(o => o.textContent.trim());
                    }})()
                """)
                print(f"        Filtered options ({len(filtered_options) if filtered_options else 0}): {(filtered_options or [])[:10]}")
                # Try exact match first
                for i, t in enumerate(filtered_options or []):
                    if t.lower() == val_lower:
                        target_idx = i
                        break
                # Partial match
                if target_idx is None:
                    for i, t in enumerate(filtered_options or []):
                        if val_lower in t.lower() or t.lower() in val_lower:
                            target_idx = i
                            break
                # Click the option
                if target_idx is not None:
                    await cdp_click_option(session, target_idx)
                    select_result = f'selected (filtered): {(filtered_options or [])[target_idx]}'
                elif filtered_options and len(filtered_options) > 0:
                    await cdp_click_option(session, 0)
                    select_result = f'fallback (first filtered): {filtered_options[0]}'
                else:
                    select_result = 'no filtered options'
            else:
                # Small list or no pre-type options
                if not pre_type_options or len(pre_type_options) == 0:
                    # Async select: no options until you type. Type value to trigger loading.
                    print(f"        No options (async select?), typing '{cq_value}' to trigger loading...")
                    await session.send("Input.insertText", {"text": cq_value})
                    await asyncio.sleep(1.5)
                    # Check for options now
                    async_opts = await session.evaluate(f"""
                        (function() {{
                            const el = document.getElementById('{cq_id}');
                            const controlsId = el ? el.getAttribute('aria-controls') : null;
                            let opts;
                            if (controlsId) {{
                                const listbox = document.getElementById(controlsId);
                                if (listbox) {{
                                    opts = Array.from(listbox.querySelectorAll('[role="option"]'));
                                }}
                            }}
                            if (!opts || opts.length === 0) {{
                                opts = Array.from(document.querySelectorAll('[role="option"]'))
                                    .filter(o => {{
                                        const r = o.getBoundingClientRect();
                                        return r.width > 0 && r.height > 0;
                                    }});
                            }}
                            return opts.map(o => o.textContent.trim());
                        }})()
                    """)
                    print(f"        Async options ({len(async_opts) if async_opts else 0}): {(async_opts or [])[:10]}")
                    if async_opts and len(async_opts) > 0:
                        # Find match
                        for i, t in enumerate(async_opts):
                            if t.lower() == val_lower:
                                target_idx = i
                                break
                        if target_idx is None:
                            for i, t in enumerate(async_opts):
                                if val_lower in t.lower() or t.lower() in val_lower:
                                    target_idx = i
                                    break
                        if target_idx is not None:
                            await cdp_click_option(session, target_idx)
                            select_result = f'selected (async): {async_opts[target_idx]}'
                        else:
                            await cdp_click_option(session, 0)
                            select_result = f'fallback (first async): {async_opts[0]}'
                    else:
                        # Still no options - try typing shorter text
                        print(f"        Still no options, trying shorter text...")
                        # Clear and try typing just first word
                        await session.send("Input.dispatchKeyEvent", {"type": "keyDown", "key": "a", "code": "KeyA", "modifiers": 2})  # Ctrl+A
                        await session.send("Input.dispatchKeyEvent", {"type": "keyUp", "key": "a", "code": "KeyA", "modifiers": 2})
                        await session.send("Input.dispatchKeyEvent", {"type": "keyDown", "key": "Backspace", "code": "Backspace"})
                        await session.send("Input.dispatchKeyEvent", {"type": "keyUp", "key": "Backspace", "code": "Backspace"})
                        short_text = cq_value.split(',')[0].strip() if ',' in cq_value else cq_value.split(' ')[0]
                        if len(short_text) >= 2:
                            await session.send("Input.insertText", {"text": short_text})
                            await asyncio.sleep(1.5)
                            retry_opts2 = await session.evaluate(f"""
                                (function() {{
                                    const el = document.getElementById('{cq_id}');
                                    const controlsId = el ? el.getAttribute('aria-controls') : null;
                                    let opts;
                                    if (controlsId) {{
                                        const listbox = document.getElementById(controlsId);
                                        if (listbox) opts = Array.from(listbox.querySelectorAll('[role="option"]'));
                                    }}
                                    if (!opts || opts.length === 0) {{
                                        opts = Array.from(document.querySelectorAll('[role="option"]'))
                                            .filter(o => {{ const r = o.getBoundingClientRect(); return r.width > 0 && r.height > 0; }});
                                    }}
                                    return opts.map(o => o.textContent.trim());
                                }})()
                            """)
                            print(f"        Short text options ({len(retry_opts2) if retry_opts2 else 0}): {(retry_opts2 or [])[:10]}")
                            if retry_opts2 and len(retry_opts2) > 0:
                                for i, t in enumerate(retry_opts2):
                                    if val_lower in t.lower() or t.lower() in val_lower:
                                        target_idx = i
                                        break
                                if target_idx is not None:
                                    await cdp_click_option(session, target_idx)
                                    select_result = f'selected (short text): {retry_opts2[target_idx]}'
                                else:
                                    await cdp_click_option(session, 0)
                                    select_result = f'fallback (first short): {retry_opts2[0]}'
                            else:
                                select_result = 'no async options after retry'
                        else:
                            select_result = 'no async options'
                else:
                    # Small list: try direct match
                    # Exact match first
                    for i, t in enumerate(pre_type_options or []):
                        if t.lower() == val_lower:
                            target_idx = i
                            break
                    # Partial match (require min 3 chars)
                    if target_idx is None and val_lower and len(val_lower) >= 3:
                        for i, t in enumerate(pre_type_options or []):
                            if val_lower in t.lower() or t.lower() in val_lower:
                                target_idx = i
                                break
                    
                    if target_idx is not None:
                        await cdp_click_option(session, target_idx)
                        select_result = f'selected: {(pre_type_options or [])[target_idx]}'
                    elif pre_type_options and len(pre_type_options) > 0:
                        # Fallback: click first option
                        await cdp_click_option(session, 0)
                        select_result = f'fallback (first): {pre_type_options[0]}'
                    else:
                        # Skip comboboxes that aren't question fields
                        if not cq_id.startswith('question_'):
                            continue
                        # No options visible - try clicking indicator to force open
                        print(f"        No options visible, trying indicator click...")
                        await session.evaluate(f"""
                            (function() {{
                                const el = document.getElementById('{cq_id}');
                                if (!el) return;
                                const control = el.closest('.select__control') || el.closest('[class*="select"]');
                                if (control) {{
                                    const indicator = control.querySelector('.select__indicator') || control.querySelector('[class*="indicator"]');
                                    if (indicator) indicator.click();
                                    else control.click();
                                }}
                            }})()
                        """)
                        await asyncio.sleep(0.5)
                        # Check options again (including portal-rendered)
                        retry_opts = await session.evaluate(f"""
                            (function() {{
                                const el = document.getElementById('{cq_id}');
                                const controlsId = el ? el.getAttribute('aria-controls') : null;
                                let opts;
                                if (controlsId) {{
                                    const listbox = document.getElementById(controlsId);
                                    if (listbox) {{
                                        opts = Array.from(listbox.querySelectorAll('[role="option"]'));
                                    }}
                                }}
                                if (!opts || opts.length === 0) {{
                                    opts = Array.from(document.querySelectorAll('[role="option"]'))
                                        .filter(o => {{
                                            const r = o.getBoundingClientRect();
                                            return r.width > 0 && r.height > 0;
                                        }});
                                }}
                                return opts.map(o => o.textContent.trim());
                            }})()
                        """)
                        if retry_opts and len(retry_opts) > 0:
                            retry_idx = 0
                            for i, t in enumerate(retry_opts):
                                if val_lower in t.lower() or t.lower() in val_lower:
                                    retry_idx = i
                                    break
                            await cdp_click_option(session, retry_idx)
                            select_result = f'selected (retry): {retry_opts[retry_idx]}'
                        else:
                            select_result = 'no options available'
            
            combobox_results[cq_id] = f"{cq_label[:30]}: {select_result}"
            print(f"        → {select_result}")
            await asyncio.sleep(0.5)
        
        print(f"    Combobox questions filled: {len(combobox_results)}")
    
    # Merge results
    if isinstance(custom_results, dict):
        custom_results.update(combobox_results)
    else:
        custom_results = combobox_results
    
    # 8. Check the first experience checkbox (3-5 years)
    checkbox_result = await session.evaluate("""
        (function() {
            const checkboxes = document.querySelectorAll('input[name^="question_"][type="checkbox"]');
            if (checkboxes.length === 0) return 'no checkboxes';
            // Click the "3-5 years" option (second checkbox) or first if only one
            let target = checkboxes[1] || checkboxes[0]; // 3-5 years
            target.click();
            target.dispatchEvent(new Event('change', {bubbles: true}));
            return 'checked: ' + (target.id || target.value);
        })()
    """)

    await asyncio.sleep(1)

    # 9. Debug: Check all form fields before submit (including React Select value elements)
    field_debug = await session.evaluate("""
        (function() {
            const results = [];
            // Check visible inputs
            document.querySelectorAll('input:not([type="hidden"]), textarea, select').forEach(el => {
                const id = el.id || el.name || 'unknown';
                const type = el.type || el.tagName.toLowerCase();
                const role = el.getAttribute('role') || '';
                if (id === 'unknown' && type !== 'file' && role !== 'combobox') return;
                let value = el.value || '';
                // For combobox inputs, check React Select's single-value display element
                if (role === 'combobox') {
                    const fieldContainer = el.closest('.field-container') || el.closest('.question-field') || el.closest('[class*="field"]') || el.parentElement?.parentElement?.parentElement;
                    if (fieldContainer) {
                        // Check .select__single-value (React Select displays selected value here)
                        const sv = fieldContainer.querySelector('.select__single-value, [class*="singleValue"], [class*="single-value"]');
                        if (sv && sv.textContent.trim()) value = sv.textContent.trim();
                        // Also check hidden inputs more broadly
                        if (!value) {
                            const hidden = fieldContainer.querySelector('input[type="hidden"]');
                            if (hidden && hidden.value) value = hidden.value;
                        }
                    }
                }
                const required = el.required ? ' (required)' : '';
                results.push(`${id}[${type}${role ? ':' + role : ''}]${required}: ${value.substring(0, 40) || '(empty)'}`);
            });
            // Check all hidden inputs with values
            document.querySelectorAll('input[type="hidden"]').forEach(el => {
                if (el.value && el.value.trim()) {
                    const id = el.id || el.name || '';
                    if (id) results.push(`${id}[hidden]: ${el.value.substring(0, 40)}`);
                }
            });
            // Check all .select__single-value elements
            document.querySelectorAll('.select__single-value, [class*="singleValue"]').forEach(el => {
                const text = el.textContent.trim();
                if (text) {
                    const parent = el.closest('[class*="field"]') || el.closest('.field-container');
                    const label = parent ? (parent.querySelector('label')?.textContent?.trim() || '') : '';
                    results.push(`reactValue: ${text.substring(0, 40)} (label: ${label.substring(0, 30)})`);
                }
            });
            return results;
        })()
    """)
    if field_debug:
        print(f"    Form fields ({len(field_debug)}):")
        for f in field_debug[:20]:
            print(f"      {f}")
    
    # Debug: Check for required fields that are empty
    empty_required = await session.evaluate("""
        (function() {
            const empty = [];
            document.querySelectorAll('input[required], textarea[required], select[required]').forEach(el => {
                const id = el.id || el.name || 'unknown';
                let value = el.value || '';
                // For combobox, check React Select value
                if (el.getAttribute('role') === 'combobox') {
                    const container = el.closest('.select__control') || el.closest('[class*="select"]');
                    if (container) {
                        const sv = container.querySelector('.select__single-value');
                        if (sv && sv.textContent.trim()) value = sv.textContent.trim();
                    }
                }
                if (!value || value === '(empty)') {
                    empty.push(id);
                }
            });
            return empty;
        })()
    """)
    if empty_required:
        print(f"    WARNING: Empty required fields: {empty_required}")
    
    # 10. Submit the form - scroll into view and use CDP click for reliability
    submit_info = await session.evaluate("""
        (function() {
            const btn = document.querySelector('button[type="submit"]');
            if (!btn) return null;
            btn.scrollIntoView({behavior: 'instant', block: 'center'});
            const rect = btn.getBoundingClientRect();
            const disabled = btn.disabled || btn.classList.contains('disabled');
            // Check for reCAPTCHA iframe
            const recaptcha = document.querySelector('iframe[src*="recaptcha"], iframe[src*="captcha"]');
            return {
                x: rect.x, 
                y: rect.y, 
                width: rect.width, 
                height: rect.height, 
                text: btn.textContent.trim(),
                disabled: disabled,
                hasRecaptcha: !!recaptcha,
                recaptchaSrc: recaptcha ? recaptcha.src : null
            };
        })()
    """)
    print(f"    Submit button info: {submit_info}")
    
    if submit_info:
        sx = submit_info['x'] + submit_info['width'] / 2
        sy = submit_info['y'] + submit_info['height'] / 2
        await session.send("Input.dispatchMouseEvent", {
            "type": "mousePressed", "x": sx, "y": sy, "button": "left", "clickCount": 1
        })
        await session.send("Input.dispatchMouseEvent", {
            "type": "mouseReleased", "x": sx, "y": sy, "button": "left", "clickCount": 1
        })
        submit_result = f"CDP clicked ({submit_info.get('text', 'submit')})"
        
        # If there's a reCAPTCHA, wait for it to validate then try submitting again
        if submit_info.get('hasRecaptcha'):
            await asyncio.sleep(3)
            # Try clicking the submit button via JS (not CDP) after reCAPTCHA validates
            js_submit = await session.evaluate("""
                (function() {
                    const btn = document.querySelector('button[type="submit"]');
                    if (btn) {
                        btn.click();
                        return 'button clicked via JS';
                    }
                    return 'no submit button';
                })()
            """)
            submit_result += f" + JS: {js_submit}"
    else:
        # Fallback to JS click
        submit_result = await session.evaluate("""
            (function() {
                const btn = document.querySelector('button[type="submit"]');
                if (!btn) return 'submit button not found';
                btn.click();
                return 'clicked submit (JS fallback)';
            })()
        """)
    print(f"    Submit: {submit_result}")

    # 10. Wait for response
    await asyncio.sleep(8)  # Wait longer for reCAPTCHA to resolve
    
    # Debug: Check if reCAPTCHA token was generated
    recaptcha_token = await session.evaluate("""
        (function() {
            // Check for reCAPTCHA response token
            const textarea = document.querySelector('textarea[name="g-recaptcha-response"]');
            if (textarea && textarea.value) {
                return 'token present: ' + textarea.value.substring(0, 50) + '...';
            }
            // Check if reCAPTCHA iframe is still present
            const iframe = document.querySelector('iframe[src*="recaptcha"]');
            if (iframe) {
                return 'reCAPTCHA iframe still present';
            }
            return 'no reCAPTCHA elements found';
        })()
    """)
    print(f"    reCAPTCHA status: {recaptcha_token}")

    # 10b. Check for validation errors on form fields (with field identification)
    validation_errors = await session.evaluate("""
        (function() {
            const errs = [];
            // Check for error messages near form fields
            document.querySelectorAll('[class*="error"], [class*="invalid"]').forEach(el => {
                const t = el.textContent.trim();
                if (!t || t.length > 150) return;
                // Try to find the associated field
                const field = el.closest('[class*="field"]') || el.closest('.field-container');
                let fieldId = '';
                if (field) {
                    const input = field.querySelector('input, textarea, select');
                    if (input) fieldId = input.id || input.name || '';
                    const label = field.querySelector('label');
                    if (label && !fieldId) fieldId = label.textContent.trim().substring(0, 50);
                }
                errs.push(fieldId ? `${fieldId}: ${t}` : t);
            });
            return errs;
        })()
    """)
    if validation_errors:
        print(f"    Validation errors ({len(validation_errors)}):")
        for e in validation_errors[:10]:
            print(f"      - {e}")

    # 11. Check result
    page_content = await session.evaluate("document.body.innerText.substring(0, 2000)")
    print(f"    Page after submit (first 200): {(page_content or '')[:200]}")
    
    # Debug: Check if form is still present
    form_still_present = await session.evaluate("!!document.querySelector('form')")
    print(f"    Form still present: {form_still_present}")
    
    # Debug: Check for any error messages on page
    page_errors = await session.evaluate("""
        (function() {
            const errs = [];
            document.querySelectorAll('[class*="error"], [class*="invalid"], [class*="required"]').forEach(el => {
                const t = el.textContent.trim();
                if (t && t.length < 100 && t.length > 2) errs.push(t);
            });
            return errs.slice(0, 10);
        })()
    """)
    if page_errors:
        print(f"    Page errors after submit: {page_errors}")
    
    # Check for success indicators
    success_indicators = [
        "thank you", "application has been", "successfully", "confirmation",
        "received your application", "thanks for applying", "back to jobs",
        "application submitted", "we've received"
    ]
    error_indicators = [
        "captcha", "please fix", "required field",
        "something went wrong", "unable to submit"
    ]

    content_lower = page_content.lower() if page_content else ""
    
    is_success = any(ind in content_lower for ind in success_indicators)
    
    # Also check if form is gone (Greenhouse shows confirmation page after submit)
    if not is_success:
        form_gone = await session.evaluate("!document.querySelector('form')")
        if form_gone:
            is_success = True
            print("    Form no longer present after submit → treating as success")
    has_error = any(ind in content_lower for ind in error_indicators)

    # Find specific error messages on page
    error_detail = ''
    if has_error:
        error_msgs = await session.evaluate("""
            (function() {
                const errs = [];
                document.querySelectorAll('[class*="error"], [class*="required"], .field-error, .form-error').forEach(el => {
                    const t = el.textContent.trim();
                    if (t && t.length < 100) errs.push(t);
                });
                return errs.slice(0, 5);
            })()
        """)
        if error_msgs:
            error_detail = '; '.join(error_msgs)

    error_msg = ''
    if not is_success:
        error_msg = 'No success indicators on page. '
    if has_error:
        error_msg += f'Page has errors: {error_detail or "error indicators found"}. '
    if submit_result == 'submit button not found':
        error_msg += 'Submit button not found. '

    return {
        "success": is_success and not has_error,
        "error": error_msg.strip() if error_msg else None,
        "fill_results": fill_results,
        "custom_results": custom_results,
        "checkbox_result": checkbox_result,
        "submit_result": submit_result,
        "page_content_preview": page_content[:300] if page_content else "empty",
        "is_success": is_success,
        "has_error": has_error,
    }


# ─── Lever Application ───────────────────────────────────────────────────────

async def apply_lever_cdp(session: CDPSession, job: dict) -> dict:
    """Fill and submit a Lever job application via CDP."""
    url = job["url"]
    resume_path = str(RESUME_PDF.resolve())

    await session.navigate(url)
    await asyncio.sleep(3)

    # Lever pages typically have an "Apply" button or direct form
    # Check if there's an apply button
    has_apply = await session.evaluate("""
        (function() {
            const btn = Array.from(document.querySelectorAll('a, button'))
                .find(b => b.textContent.toLowerCase().includes('apply'));
            if (btn) { btn.click(); return true; }
            return false;
        })()
    """)
    await asyncio.sleep(3)

    # Get form fields
    fields = await session.evaluate("""
        (function() {
            const form = document.querySelector('form') || document;
            const result = [];
            form.querySelectorAll('input, textarea, select').forEach(el => {
                result.push({
                    name: el.name || el.id || '',
                    type: el.type || '',
                    tag: el.tagName.toLowerCase(),
                    label: el.getAttribute('aria-label') || '',
                });
            });
            return result;
        })()
    """)

    # TODO: Implement Lever-specific form filling
    return {
        "success": False,
        "error": "Lever form filling not yet implemented",
        "fields_found": len(fields) if isinstance(fields, list) else 0,
    }


# ─── Main ────────────────────────────────────────────────────────────────────

async def async_main():
    parser = argparse.ArgumentParser(
        description="ATS Auto-Apply via CDP browser automation (live send gated)"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually submit applications (also requires env unlock — see safety.py)",
    )
    parser.add_argument("--limit", type=int, default=10, help="Max applications per run")
    parser.add_argument("--company", type=str, help="Apply to specific company only")
    parser.add_argument("--ats", type=str, choices=["greenhouse", "lever"], help="Filter by ATS type")
    parser.add_argument(
        "--test",
        action="store_true",
        help="Preview first matching job only (NEVER submits; dry-run)",
    )
    args = parser.parse_args()

    # --test is always dry-run. Live submit requires --apply + safety unlock.
    live_submit = bool(args.apply) and not args.test

    print(f"\n{'='*70}")
    print(f"  ATS AUTO-APPLY (CDP Browser Automation)")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  DATA_DIR: {DATA_DIR}")
    if args.test:
        mode = "TEST (preview only — no submit)"
    elif live_submit:
        mode = "LIVE SUBMIT"
    else:
        mode = "DRY RUN"
    print(f"  Mode: {mode}")
    print(f"  Unlock active: {is_live_send_unlocked()}")
    print(f"{'='*70}\n")

    if not RESUME_PDF.exists():
        print(f"✗ Resume PDF not found: {RESUME_PDF}")
        print("  (dry-run/test may continue without resume for candidate listing)")

    # Get candidates
    candidates = get_ats_candidates()
    if args.company:
        candidates = [c for c in candidates if args.company.lower() in c["company"].lower()]
    if args.ats:
        candidates = [c for c in candidates if c["ats"] == args.ats]

    print(f"Found {len(candidates)} ATS jobs:\n")
    by_ats = {}
    for c in candidates:
        by_ats.setdefault(c["ats"], []).append(c)
    for ats, jobs in by_ats.items():
        print(f"  {ats.upper()}: {len(jobs)} jobs")

    # Dry-run / --test: list only, never open browser or click submit
    if not live_submit:
        sample = candidates[:1] if args.test else candidates[:5]
        label = "TEST sample" if args.test else "DRY RUN sample"
        print(f"\n  {label} — no browser, no submit.")
        if not args.apply:
            print("  To submit later: --apply + BOOK_JOB_LIVE_SEND_ENABLED=1")
            print("  + BOOK_JOB_SEND_UNLOCK=I_UNDERSTAND_LIVE_SEND")
        elif args.test:
            print("  Note: --test forces preview-only even if --apply is set.")
        for c in sample:
            print(f"    • {c['title'][:50]} @ {c['company'][:30]}")
            print(f"      {c['url'][:80]}")
        return

    # Live path — hard safety gate
    assert_no_network_send_without_flag(want_send=True, action="ATS apply")

    if not RESUME_PDF.exists():
        print(f"✗ Resume PDF not found: {RESUME_PDF}")
        return

    # Ensure Chrome is running
    print(f"\nStarting Chrome CDP...")
    if not ensure_chrome_running():
        print("✗ Failed to start Chrome")
        return

    # Load log
    log = load_ats_log()
    applied_urls = {entry["url"] for entry in log.get("applied", [])}

    to_process = [c for c in candidates if c["url"] not in applied_urls]
    to_process = to_process[: args.limit]

    print(f"\nSubmitting {len(to_process)} applications...\n")

    success_count = 0
    fail_count = 0

    for i, job in enumerate(to_process, 1):
        print(f"[{i}/{len(to_process)}] {job['title'][:50]} @ {job['company'][:30]}")
        print(f"  ATS: {job['ats']} | Job ID: {job['job_id']}")

        try:
            ws_url = await _get_ws_url()
            session = CDPSession(ws_url)
            await session.connect()

            if job["ats"] == "greenhouse":
                result = await apply_greenhouse_cdp(session, job)
            elif job["ats"] == "lever":
                result = await apply_lever_cdp(session, job)
            else:
                result = {"success": False, "error": "Unknown ATS type"}

            await session.close()

        except Exception as e:
            import traceback
            traceback.print_exc()
            result = {"success": False, "error": str(e)}

        if result.get("success"):
            print(f"  ✓ Application submitted!")
            log["applied"].append({
                "url": job["url"],
                "title": job["title"],
                "company": job["company"],
                "ats": job["ats"],
                "job_id": job["job_id"],
                "applied_at": datetime.now().isoformat(),
            })
            update_tracker_status(
                job["url"],
                STATUS_SUBMITTED,
                f"Submitted via {job['ats']} CDP",
            )
            success_count += 1
        else:
            print(f"  ✗ Failed: {result.get('error', 'Unknown error')}")
            if result.get("page_content_preview"):
                print(f"    Page: {result['page_content_preview'][:150]}")
            log["failed"].append({
                "url": job["url"],
                "title": job["title"],
                "company": job["company"],
                "ats": job["ats"],
                "error": result.get("error"),
                "detail": {k: v for k, v in result.items() if k not in ("success", "error")},
                "failed_at": datetime.now().isoformat(),
            })
            fail_count += 1

        if i < len(to_process):
            time.sleep(3)
        print()

    save_ats_log(log)

    print(f"{'='*70}")
    print(f"  SUMMARY")
    print(f"{'='*70}")
    print(f"  Successful: {success_count}")
    print(f"  Failed: {fail_count}")
    print(f"  Total: {len(to_process)}")
    print(f"{'='*70}\n")


def main():
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
